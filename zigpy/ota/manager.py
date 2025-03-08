"""OTA manager for Zigpy. initial implementation from: https://github.com/zigpy/zigpy/pull/1102"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import zigpy.datastructures
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import Ota

if TYPE_CHECKING:
    from typing_extensions import Self

    from zigpy.device import Device
    from zigpy.ota.providers import OtaImageWithMetadata


# Devices often ask for bigger blocks than radios can send
MAXIMUM_IMAGE_BLOCK_SIZE = 40
MAX_TIME_WITHOUT_PROGRESS = 30


def find_ota_cluster(device: Device) -> Ota:
    """Finds the first OTA cluster available on the device."""
    for ep in device.non_zdo_endpoints:
        if Ota.cluster_id in ep.out_clusters:
            return ep.out_clusters[Ota.cluster_id]
    raise ValueError("Device has no OTA cluster")


class OTAManager:
    """Class to manage OTA updates for a device."""

    def __init__(
        self,
        device: Device,
        image: OtaImageWithMetadata,
        progress_callback=None,
        force: bool = False,
    ) -> None:
        self.device = device
        self.ota_cluster = find_ota_cluster(device)

        self.image = image
        self._image_data = image.firmware.serialize()
        self.progress_callback = progress_callback
        self.force = force

        self._upgrade_end_future = asyncio.get_running_loop().create_future()
        self._stall_timer = zigpy.datastructures.ReschedulableTimeout(
            self._stall_callback
        )

        self.stack = contextlib.ExitStack()

    def __enter__(self) -> Self:
        self.stack.enter_context(
            self.device._application.callback_for_response(
                src=self.device,
                filters=[
                    Ota.ServerCommandDefs.query_next_image.schema(),
                ],
                callback=self._image_query_req,
            )
        )

        self.stack.enter_context(
            self.device._application.callback_for_response(
                src=self.device,
                filters=[
                    Ota.ServerCommandDefs.image_block.schema(),
                ],
                callback=self._image_block_req,
            )
        )

        self.stack.enter_context(
            self.device._application.callback_for_response(
                src=self.device,
                filters=[
                    Ota.ServerCommandDefs.image_page.schema(),
                ],
                callback=self._image_page_req,
            )
        )

        self.stack.enter_context(
            self.device._application.callback_for_response(
                src=self.device,
                filters=[
                    Ota.ServerCommandDefs.upgrade_end.schema(),
                ],
                callback=self._upgrade_end,
            )
        )

        return self

    def __exit__(self, *exc_details) -> None:
        self.stack.close()

    def _stall_callback(self) -> None:
        """Handle the stall timer expiring."""
        self._finish(foundation.Status.TIMEOUT)

    def _finish(self, status: foundation.Status) -> None:
        """Finish the OTA process."""
        self._stall_timer.cancel()

        if not self._upgrade_end_future.done():
            self._upgrade_end_future.set_result(status)

    async def _image_query_req(
        self, hdr: foundation.ZCLHeader, command: Ota.QueryNextImageCommand
    ) -> None:
        """Handle image query request."""

        # If we try to send a device an old image (e.g. cache issue), don't bother
        if not self.force and (
            not self.image.check_compatibility(self.device, command)
            or not self.image.check_version(command.current_file_version)
        ):
            status = foundation.Status.NO_IMAGE_AVAILABLE
        else:
            status = foundation.Status.SUCCESS

        try:
            await self.ota_cluster.query_next_image_response(
                status=status,
                manufacturer_code=self.image.firmware.header.manufacturer_id,
                image_type=self.image.firmware.header.image_type,
                file_version=self.image.firmware.header.file_version,
                image_size=self.image.firmware.header.image_size,
                tsn=hdr.tsn,
            )
        except Exception as ex:  # noqa: BLE001
            self.device.debug("OTA query_next_image handler exception", exc_info=ex)
            status = foundation.Status.FAILURE

        if status != foundation.Status.SUCCESS:
            self._finish(status)

    async def _finish_malformed_image_block_response(self, handler: str, tsn: int):
        """Create an image block response failure."""
        try:
            await self.ota_cluster.image_block_response(
                status=foundation.Status.MALFORMED_COMMAND, tsn=tsn
            )
        except Exception as ex:  # noqa: BLE001
            self.device.debug(
                "OTA %s handler[MALFORMED_COMMAND] exception", handler, exc_info=ex
            )

        self._finish(foundation.Status.MALFORMED_COMMAND)

    async def _image_block_req(
        self, hdr: foundation.ZCLHeader, command: Ota.ImageBlockCommand
    ) -> None:
        """Handle image block request."""
        if command.manufacturer_code == 4129:
            # Legrand devices (manufacturer_code == 4129) require up to 64 bytes.
            default_image_block_size = 255
        else:
            default_image_block_size = MAXIMUM_IMAGE_BLOCK_SIZE
        block = self._image_data[
            command.file_offset : command.file_offset
            + min(default_image_block_size, command.maximum_data_size)
        ]

        if not block:
            await self._finish_malformed_image_block_response(
                "image_block", tsn=hdr.tsn
            )
            return

        try:
            await self.ota_cluster.image_block_response(
                status=foundation.Status.SUCCESS,
                manufacturer_code=self.image.firmware.header.manufacturer_id,
                image_type=self.image.firmware.header.image_type,
                file_version=self.image.firmware.header.file_version,
                file_offset=command.file_offset,
                image_data=block,
                tsn=hdr.tsn,
            )

            self._stall_timer.reschedule(MAX_TIME_WITHOUT_PROGRESS)

            # Image block requests can sometimes succeed after the device aborts the
            # update. We should not allow the progress callback to be called.
            if (
                self.progress_callback is not None
                and not self._upgrade_end_future.done()
            ):
                self.progress_callback(
                    command.file_offset + len(block), len(self._image_data)
                )
        except Exception as ex:  # noqa: BLE001
            self.device.debug("OTA image_block handler exception", exc_info=ex)

    async def _image_page_req(
        self, hdr: foundation.ZCLHeader, command: Ota.ImagePageCommand
    ) -> None:
        """Handle image page request."""
        offset = command.file_offset
        bytes_remaining = min(
            command.page_size, len(self._image_data) - command.file_offset
        )

        if bytes_remaining <= 0:
            await self._finish_malformed_image_block_response(
                "image_page_req",
                tsn=hdr.tsn,
            )
            return

        while bytes_remaining > 0:
            block_size = min(
                MAXIMUM_IMAGE_BLOCK_SIZE,
                command.maximum_data_size,
                bytes_remaining,
            )
            block = self._image_data[offset : offset + block_size]
            offset += block_size
            bytes_remaining -= block_size

            try:
                # Once we have a way to send requests without waiting for replies,
                # this can be converted to just `self.ota_cluster.image_block_response`
                await self.ota_cluster.request(
                    general=False,
                    command_id=Ota.ClientCommandDefs.image_block_response.id,
                    schema=Ota.ClientCommandDefs.image_block_response.schema,
                    expect_reply=False,
                    # kwargs
                    status=foundation.Status.SUCCESS,
                    manufacturer_code=self.image.firmware.header.manufacturer_id,
                    image_type=self.image.firmware.header.image_type,
                    file_version=self.image.firmware.header.file_version,
                    file_offset=offset - block_size,
                    image_data=block,
                )

                self._stall_timer.reschedule(MAX_TIME_WITHOUT_PROGRESS)

                if (
                    self.progress_callback is not None
                    and not self._upgrade_end_future.done()
                ):
                    self.progress_callback(
                        offset - block_size + len(block), len(self._image_data)
                    )
            except Exception as ex:  # noqa: BLE001
                self.device.debug("OTA image_page handler exception", exc_info=ex)
                return

            # Delay according to what the device asks
            await asyncio.sleep(command.response_spacing / 1000)

    async def _upgrade_end(
        self, hdr: foundation.ZCLHeader, command: foundation.CommandSchema
    ) -> None:
        """Handle upgrade end request."""
        try:
            await self.ota_cluster.upgrade_end_response(
                manufacturer_code=self.image.firmware.header.manufacturer_id,
                image_type=self.image.firmware.header.image_type,
                file_version=self.image.firmware.header.file_version,
                current_time=0x00000000,
                upgrade_time=0x00000000,
                tsn=hdr.tsn,
            )

            self._finish(command.status)
        except Exception as ex:  # noqa: BLE001
            self.device.debug("OTA upgrade_end handler exception", exc_info=ex)
            self._finish(foundation.Status.FAILURE)

    async def notify(self) -> None:
        """Notify device of new image."""
        try:
            await self.ota_cluster.image_notify(
                payload_type=(
                    self.ota_cluster.ImageNotifyCommand.PayloadType.QueryJitter
                ),
                query_jitter=100,
            )
        except Exception as ex:  # noqa: BLE001
            self.device.debug("OTA image_notify handler exception", exc_info=ex)
            self._finish(foundation.Status.FAILURE)
        else:
            self._stall_timer.reschedule(MAX_TIME_WITHOUT_PROGRESS)

    async def wait(self) -> foundation.Status:
        """Wait for upgrade end response."""
        return await self._upgrade_end_future


async def update_firmware(
    device: Device,
    image: OtaImageWithMetadata,
    progress_callback: callable | None = None,
    force: bool = False,
) -> foundation.Status:
    """Update the firmware on a Zigbee device."""
    if force:
        # Force it to send the image even if it's the same version
        image = image.replace(
            metadata=image.metadata.replace(file_version=0xFFFFFFFF - 1),
            firmware=image.firmware.replace(
                header=image.firmware.header.replace(file_version=0xFFFFFFFF - 1)
            ),
        )

    def progress(current: int, total: int):
        progress = (100 * current) / total
        device.info(
            "OTA upgrade progress: (%d / %d): %0.4f%%",
            current,
            total,
            progress,
        )
        if progress_callback is not None:
            progress_callback(current, total, progress)

    with OTAManager(device, image, progress_callback=progress, force=force) as ota:
        await ota.notify()
        return await ota.wait()
