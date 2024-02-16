"""OTA support for Zigbee devices."""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import sys
import typing

from zigpy.config import (
    CONF_OTA_ADVANCED_DIR,
    CONF_OTA_ALLOW_ADVANCED_DIR,
    CONF_OTA_ENABLED,
    CONF_OTA_IKEA,
    CONF_OTA_INOVELLI,
    CONF_OTA_LEDVANCE,
    CONF_OTA_PROVIDER_MANUF_IDS,
    CONF_OTA_PROVIDER_URL,
    CONF_OTA_REMOTE_PROVIDERS,
    CONF_OTA_SALUS,
    CONF_OTA_SONOFF,
    CONF_OTA_THIRDREALITY,
    CONF_OTA_Z2M_LOCAL_INDEX,
    CONF_OTA_Z2M_REMOTE_INDEX,
)
from zigpy.ota.image import BaseOTAImage
import zigpy.ota.providers
import zigpy.types as t
import zigpy.util
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import Ota

if sys.version_info[:2] < (3, 11):
    from async_timeout import timeout as asyncio_timeout  # pragma: no cover
else:
    from asyncio import timeout as asyncio_timeout  # pragma: no cover

if typing.TYPE_CHECKING:
    import zigpy.application

    query_next_image = Ota.ServerCommandDefs.query_next_image.schema

_LOGGER = logging.getLogger(__name__)

OTA_FETCH_TIMEOUT = 20
MAX_DEVICES_CHECKING_IN_PER_BROADCAST = 15


@dataclasses.dataclass(frozen=True)
class OtaImageWithMetadata(t.BaseDataclassMixin):
    metadata: zigpy.ota.providers.BaseOtaImageMetadata
    firmware: BaseOTAImage | None

    @property
    def version(self) -> int:
        return self.metadata.file_version

    @property
    def _min_hardware_version(self) -> int | None:
        if self.metadata.min_hardware_version is not None:
            return self.metadata.min_hardware_version
        elif (
            self.firmware is not None
            and self.firmware.header.minimum_hardware_version is not None
        ):
            return self.firmware.header.minimum_hardware_version
        else:
            return None

    @property
    def _max_hardware_version(self) -> int | None:
        if self.metadata.max_hardware_version is not None:
            return self.metadata.max_hardware_version
        elif (
            self.firmware is not None
            and self.firmware.header.maximum_hardware_version is not None
        ):
            return self.firmware.header.maximum_hardware_version
        else:
            return None

    @property
    def _manufacturer_id(self) -> int | None:
        if self.metadata.manufacturer_id is not None:
            return self.metadata.manufacturer_id
        elif self.firmware is not None:
            return self.firmware.header.manufacturer_id
        else:
            return None

    @property
    def _image_type(self) -> int | None:
        if self.metadata.image_type is not None:
            return self.metadata.image_type
        elif self.firmware is not None:
            return self.firmware.header.image_type
        else:
            return None

    @property
    def specificity(self) -> int:
        """Return a numerical representation of the metadata specificity.
        Higher specificity is preferred to lower when picking a final OTA image.
        """

        total = 0

        if self.metadata.manufacturer_names:
            total += 1000

        if self.metadata.model_names:
            total += 1000

        if self._image_type is not None:
            total += 100

        if self._manufacturer_id is not None:
            total += 100

        if self.metadata.min_current_file_version is not None:
            total += 10

        if self.metadata.max_current_file_version is not None:
            total += 10

        if self._min_hardware_version is not None:
            total += 1

        if self._max_hardware_version is not None:
            total += 1

        # Boost the specificity
        if self.metadata.specificity is not None:
            total += self.metadata.specificity

        return total

    def check_compatibility(
        self,
        device: zigpy.device.Device,
        query_cmd: query_next_image,
    ) -> bool:
        """Check if an OTA image and its metadata is compatible with a device."""
        if self.metadata.file_version <= query_cmd.current_file_version:
            return False

        if (
            self._manufacturer_id is not None
            and self._manufacturer_id != query_cmd.manufacturer_code
        ):
            return False

        if self._image_type is not None and self._image_type != query_cmd.image_type:
            return False

        if self.metadata.model_names and device.model not in self.metadata.model_names:
            return False

        if (
            self.metadata.manufacturer_names
            and device.manufacturer not in self.metadata.manufacturer_names
        ):
            return False

        if (
            self.metadata.min_current_file_version is not None
            and query_cmd.current_file_version < self.metadata.min_current_file_version
        ):
            return False

        if (
            self.metadata.max_current_file_version is not None
            and query_cmd.current_file_version > self.metadata.max_current_file_version
        ):
            return False

        if self._min_hardware_version is not None and (
            query_cmd.hardware_version is None
            or query_cmd.hardware_version < self._min_hardware_version
        ):
            return False

        if self._max_hardware_version is not None and (
            query_cmd.hardware_version is None
            or query_cmd.hardware_version > self._max_hardware_version
        ):
            return False

        return True

    async def fetch(self) -> OtaImageWithMetadata:
        firmware = await self.metadata.fetch()

        return self.replace(
            metadata=self.metadata,
            firmware=firmware,
        )


class OTA:
    """OTA Manager."""

    def __init__(
        self,
        config: dict[str, typing.Any],
        application: zigpy.application.ControllerApplication,
    ) -> None:
        self._config = config
        self._application = application

        self._providers: list[zigpy.ota.providers.BaseOtaProvider] = []
        self._image_cache: dict[
            zigpy.ota.providers.BaseOtaImageMetadata, OtaImageWithMetadata
        ] = {}

        self._broadcast_loop_task = None

        if config[CONF_OTA_ENABLED]:
            self._register_providers(self._config)

    async def broadcast_loop(
        self, initial_delay: int | float, interval: int | float
    ) -> None:
        """Periodically broadcast an image notification to get devices to check in."""

        await asyncio.sleep(initial_delay)

        while True:
            _LOGGER.debug("Broadcasting OTA notification")

            try:
                await self.broadcast_notify()
            except Exception:
                _LOGGER.debug("OTA broadcast failed", exc_info=True)

            await asyncio.sleep(interval)

    def start_periodic_broadcasts(
        self, initial_delay: int | float, interval: int | float
    ) -> None:
        """Start the periodic OTA broadcasts."""
        self._broadcast_loop_task = asyncio.create_task(
            self.broadcast_loop(
                initial_delay=initial_delay,
                interval=interval,
            )
        )

    def stop_periodic_broadcasts(self) -> None:
        """Stop the periodic OTA broadcasts."""
        if self._broadcast_loop_task is not None:
            self._broadcast_loop_task.cancel()
            self._broadcast_loop_task = None

    def _register_providers(self, config: dict[str, typing.Any]) -> None:
        if config[CONF_OTA_ALLOW_ADVANCED_DIR]:
            self.register_provider(
                zigpy.ota.providers.AdvancedFileProvider(config[CONF_OTA_ADVANCED_DIR])
            )

        if config[CONF_OTA_IKEA]:
            self.register_provider(zigpy.ota.providers.Trådfri())

        if config[CONF_OTA_INOVELLI]:
            self.register_provider(zigpy.ota.providers.Inovelli())

        if config[CONF_OTA_LEDVANCE]:
            self.register_provider(zigpy.ota.providers.Ledvance())

        if config[CONF_OTA_SALUS]:
            self.register_provider(zigpy.ota.providers.Salus())

        if config[CONF_OTA_SONOFF]:
            self.register_provider(zigpy.ota.providers.Sonoff())

        if config[CONF_OTA_THIRDREALITY]:
            self.register_provider(zigpy.ota.providers.ThirdReality())

        for provider_config in config[CONF_OTA_REMOTE_PROVIDERS]:
            self.register_provider(
                zigpy.ota.providers.RemoteProvider(
                    url=provider_config[CONF_OTA_PROVIDER_URL],
                    manufacturer_ids=provider_config[CONF_OTA_PROVIDER_MANUF_IDS],
                )
            )

        if config[CONF_OTA_Z2M_LOCAL_INDEX]:
            self.register_provider(
                zigpy.ota.providers.LocalZ2MProvider(config[CONF_OTA_Z2M_LOCAL_INDEX])
            )

        if config[CONF_OTA_Z2M_REMOTE_INDEX]:
            self.register_provider(
                zigpy.ota.providers.RemoteZ2MProvider(config[CONF_OTA_Z2M_REMOTE_INDEX])
            )

    def register_provider(self, provider: zigpy.ota.providers.BaseOtaProvider) -> None:
        """Register a new OTA provider."""
        _LOGGER.debug("Registering new OTA provider: %s", provider)
        self._providers.append(provider)

    @zigpy.util.combine_concurrent_calls
    async def _load_provider_index(
        self, provider: zigpy.ota.providers.BaseOtaProvider
    ) -> list[zigpy.ota.providers.BaseOtaImageMetadata]:
        """Load the index of a provider."""

        async with asyncio_timeout(OTA_FETCH_TIMEOUT):
            return await provider.load_index()

    @zigpy.util.combine_concurrent_calls
    async def _fetch_image(
        self, image: OtaImageWithMetadata
    ) -> list[OtaImageWithMetadata]:
        """Load the index of a provider."""

        async with asyncio_timeout(OTA_FETCH_TIMEOUT):
            return await image.fetch()

    async def get_ota_image(
        self,
        device: zigpy.device.Device,
        query_cmd: query_next_image,
    ) -> OtaImageWithMetadata | None:
        # Only consider providers that are compatible with the device
        compatible_providers = [
            p for p in self._providers if p.compatible_with_device(device)
        ]

        # Load the index of every provider
        for provider in compatible_providers:
            try:
                index = await self._load_provider_index(provider)
            except Exception as exc:
                _LOGGER.debug("Failed to load provider %s", provider, exc_info=exc)
                continue

            if index is None:
                _LOGGER.debug(
                    "Provider %s was recently contacted, using cached response",
                    provider,
                )
                continue

            _LOGGER.debug("Loaded %d images from provider: %s", len(index), provider)

            # Cache its images. If the concurrent call's result was shared, the first
            # caller will cache these images
            for meta in index:
                if meta not in self._image_cache:
                    self._image_cache[meta] = OtaImageWithMetadata(
                        metadata=meta, firmware=None
                    )

        # Find all superficially compatible images. Note that if an image's contents
        # are unknown and its metadata does not describe hardware compatibility, we will
        # still download in the next step to double check, in case the file itself does.
        pre_candidates = {
            img.metadata: img
            for img in self._image_cache.values()
            if img.check_compatibility(device, query_cmd)
        }

        undownloaded_images = [
            img for img in pre_candidates.values() if img.firmware is None
        ]

        # Fetch all the candidates that are missing from the cache
        results = await asyncio.gather(
            *(self._fetch_image(img) for img in undownloaded_images),
            return_exceptions=True,
        )

        for img, result in zip(undownloaded_images, results):
            if isinstance(result, BaseException):
                _LOGGER.debug(
                    "Failed to download image, ignoring: %s", img, exc_info=result
                )
                pre_candidates.pop(img.metadata, None)
                continue

            # `img` is the metadata without downloaded firmware: `result` is the same
            # image with downloaded firmware
            img = result

            # Cache the image if it isn't already cached
            if self._image_cache[img.metadata].firmware is None:
                _LOGGER.debug("Caching image %s", img)
                self._image_cache[img.metadata] = img

            pre_candidates[img.metadata] = img

        # Now we have all of the necessary metadata to fully vet the candidates and
        # pick the best image
        highest_version = (-1, -1)
        highest_version_images: list[OtaImageWithMetadata] = []

        for img in pre_candidates.values():
            if img.check_compatibility(device, query_cmd):
                assert img.firmware is not None
                key = (img.firmware.header.file_version, img.specificity)

                if key < highest_version:
                    continue
                elif key > highest_version:
                    highest_version_images = []
                    highest_version = key

                highest_version_images.append(img)

        if not highest_version_images:
            # If no image is actually compatible with the device (i.e. the metadata is
            # incomplete and after an image download we exclude the file), we are done
            _LOGGER.debug(
                "No new firmware is compatible with the device or the device is already"
                " fully up-to-date"
            )
            return None

        # If there are multiple candidates with the same specificity and version but
        # having different contents, bail out
        first_fw = highest_version_images[0].firmware

        if any(img.firmware != first_fw for img in highest_version_images[1:]):
            _LOGGER.warning(
                "Multiple compatible OTA images for device %s exist, not picking",
                device,
            )
            return None

        _LOGGER.debug("Picking firmware %s", highest_version_images[0])

        return highest_version_images[0]

    async def broadcast_notify(
        self,
        broadcast_address: t.BroadcastAddress = t.BroadcastAddress.ALL_DEVICES,
        jitter: int | None = None,
    ) -> None:
        tsn = self._application.get_sequence()

        command = Ota.ClientCommandDefs.image_notify

        # To avoid flooding huge networks, set the jitter such that we will probably
        # have a fixed number of devices checking in at once. All devices should
        # eventually check in, just not every time.
        if jitter is None:
            num_devices = len(self._application.devices)
            jitter = 100 * min(
                max(0, MAX_DEVICES_CHECKING_IN_PER_BROADCAST / max(1, num_devices)), 1
            )

        hdr, request = Ota._create_request(
            self=None,
            general=False,
            command_id=command.id,
            schema=command.schema,
            tsn=tsn,
            disable_default_response=True,
            direction=foundation.Direction.Server_to_Client,
            args=(),
            kwargs={
                "payload_type": Ota.ImageNotifyCommand.PayloadType.QueryJitter,
                "query_jitter": jitter,
            },
        )

        # Broadcast
        await self._application.send_packet(
            t.ZigbeePacket(
                src=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK,
                    address=self._application.state.node_info.nwk,
                ),
                src_ep=1,
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.Broadcast,
                    address=broadcast_address,
                ),
                dst_ep=0xFF,
                tsn=tsn,
                profile_id=zigpy.profiles.zha.PROFILE_ID,
                cluster_id=Ota.cluster_id,
                data=t.SerializableBytes(hdr.serialize() + request.serialize()),
                tx_options=t.TransmitOptions.NONE,
                radius=30,
            )
        )
