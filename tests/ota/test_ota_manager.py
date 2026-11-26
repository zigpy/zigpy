import asyncio
from collections.abc import Awaitable, Callable
import itertools
import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import aiohttp
import pytest

from tests.conftest import (
    add_initialized_device,
    make_app,
    make_node_desc,
    mock_attribute_reads,
)
import zigpy.application
import zigpy.device
import zigpy.exceptions
from zigpy.exceptions import DeliveryError
from zigpy.ota import OtaImageWithMetadata
import zigpy.ota.image
from zigpy.ota.manager import _image_block_size_for_manufacturer, update_firmware
import zigpy.state
import zigpy.types as t
import zigpy.util
from zigpy.zcl import foundation
from zigpy.zcl.clusters import Cluster
from zigpy.zcl.clusters.general import Ota
import zigpy.zdo.types as zdo_t


def lcg(*, x: int = 0, a: int, c: int, m: int):
    while True:
        x = (a * x + c) % m
        yield x


FW_IMAGE = zigpy.ota.OtaImageWithMetadata(
    metadata=zigpy.ota.providers.BaseOtaImageMetadata(
        file_version=0x12345678,
        manufacturer_id=0x1234,
        image_type=0x90,
    ),
    firmware=zigpy.ota.image.OTAImage(
        header=zigpy.ota.image.OTAImageHeader(
            upgrade_file_id=zigpy.ota.image.OTAImageHeader.MAGIC_VALUE,
            file_version=0x12345678,
            image_type=0x90,
            manufacturer_id=0x1234,
            header_version=256,
            header_length=56,
            field_control=0,
            stack_version=2,
            header_string="This is a test header!",
            image_size=2048 + 56 + 2 + 4,
        ),
        subelements=[
            zigpy.ota.image.SubElement(
                tag_id=0x0000,
                data=bytes(
                    [
                        x & 0xFF
                        for x in itertools.islice(
                            lcg(x=1, a=16807, c=0, m=7**5),
                            2048,
                        )
                    ]
                ),
            )
        ],
    ),
)


def make_packet(
    dev: zigpy.device.Device,
    cluster: Cluster,
    cmd_name: str,
    *,
    disable_default_response: bool = False,
    **kwargs,
):
    req_hdr, req_cmd = cluster._create_request(
        general=False,
        command_id=cluster.commands_by_name[cmd_name].id,
        schema=cluster.commands_by_name[cmd_name].schema,
        disable_default_response=disable_default_response,
        direction=foundation.Direction.Client_to_Server,
        args=(),
        kwargs=kwargs,
    )

    return t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=dev.nwk),
        src_ep=1,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        dst_ep=1,
        tsn=req_hdr.tsn,
        profile_id=260,
        cluster_id=cluster.cluster_id,
        data=t.SerializableBytes(req_hdr.serialize() + req_cmd.serialize()),
        lqi=255,
        rssi=-30,
    )


@pytest.mark.parametrize(
    ("manufacturer_code", "requested_size", "expected_size"),
    [
        (4474, 64, 40),  # Insta
        (4405, 64, 40),  # Dresden Elektronik
        (4129, 64, 64),  # Legrand
        (4742, 64, 50),  # Sonoff/default behavior
        (4742, 48, 48),  # Sonoff requested 48-byte chunks
        (0x1234, 64, 50),  # Generic/default behavior
    ],
)
def test_image_block_size_for_manufacturer(
    manufacturer_code: int, requested_size: int, expected_size: int
) -> None:
    assert (
        _image_block_size_for_manufacturer(manufacturer_code, requested_size)
        == expected_size
    )


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.1)
async def test_ota_manger_stall(image_with_metadata: OtaImageWithMetadata) -> None:
    img = image_with_metadata

    app = make_app({})
    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)
    dev.model = "model1"
    dev.manufacturer = "manufacturer1"

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = zigpy.profiles.zha.DeviceType.PUMP

    ota = ep.add_output_cluster(Ota.cluster_id)

    async def send_packet(packet: t.ZigbeePacket):
        assert img.firmware is not None

        if packet.cluster_id == Ota.cluster_id:
            hdr, cmd = ota.deserialize(packet.data.serialize())
            if isinstance(cmd, Ota.ImageNotifyCommand):
                dev.application.packet_received(
                    make_packet(
                        dev,
                        ota,
                        "query_next_image",
                        field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                        manufacturer_code=img.firmware.header.manufacturer_id,
                        image_type=img.firmware.header.image_type,
                        current_file_version=img.firmware.header.file_version - 10,
                        hardware_version=1,
                    )
                )
            elif isinstance(
                cmd, Ota.ClientCommandDefs.query_next_image_response.schema
            ):
                # Do nothing, just let it time out
                pass

    dev.application.send_packet = AsyncMock(side_effect=send_packet)

    status = await dev.update_firmware(img)
    assert status == foundation.Status.TIMEOUT


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.2)
async def test_ota_manager_stall_timer_counts_device_requests() -> None:
    """Test that a device still requesting blocks keeps the OTA alive.

    Our answer to one block request is delayed for longer than the stall timeout,
    e.g. because the coordinator does not confirm the previous send. The device keeps
    asking for the same block in the meantime.
    """
    assert FW_IMAGE.firmware is not None
    header = FW_IMAGE.firmware.header
    image_data = FW_IMAGE.firmware.serialize()

    app = make_app({})
    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = zigpy.profiles.zha.DeviceType.PUMP
    ota = ep.add_output_cluster(Ota.cluster_id)

    loop = asyncio.get_running_loop()
    expected_offset = 0
    delayed = False
    received = bytearray()

    def request_block(offset: int) -> None:
        app.packet_received(
            make_packet(
                dev,
                ota,
                "image_block",
                field_control=Ota.ImageBlockCommand.FieldControl(0),
                manufacturer_code=header.manufacturer_id,
                image_type=header.image_type,
                file_version=header.file_version,
                file_offset=offset,
                maximum_data_size=50,
            )
        )

    async def send_packet(packet: t.ZigbeePacket) -> None:
        nonlocal expected_offset, delayed

        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = ota.deserialize(packet.data.serialize())

        if isinstance(cmd, Ota.ImageNotifyCommand):
            app.packet_received(
                make_packet(
                    dev,
                    ota,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl(0),
                    manufacturer_code=header.manufacturer_id,
                    image_type=header.image_type,
                    current_file_version=header.file_version - 10,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            assert cmd.status == foundation.Status.SUCCESS
            loop.call_soon(request_block, 0)
        elif isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema):
            assert cmd.status == foundation.Status.SUCCESS

            if cmd.file_offset == 500 and not delayed:
                delayed = True

                # The device re-requests the block while our answer is stuck
                for i in range(1, 5):
                    loop.call_later(0.1 * i, request_block, 500)

                await asyncio.sleep(0.5)

            if cmd.file_offset != expected_offset:
                # Answers to repeated requests are ignored by the device
                return

            received.extend(cmd.image_data)
            expected_offset += len(cmd.image_data)

            if expected_offset < len(image_data):
                loop.call_soon(request_block, expected_offset)
            else:
                loop.call_soon(
                    app.packet_received,
                    make_packet(
                        dev,
                        ota,
                        "upgrade_end",
                        status=foundation.Status.SUCCESS,
                        manufacturer_code=header.manufacturer_id,
                        image_type=header.image_type,
                        file_version=header.file_version,
                    ),
                )

    app.send_packet = AsyncMock(side_effect=send_packet)

    # Stop the general cluster handler from interfering
    dev.ota_in_progress = True
    status = await update_firmware(dev, FW_IMAGE)

    assert delayed
    assert status == foundation.Status.SUCCESS
    assert received == image_data


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.1)
@patch("zigpy.ota.manager.FINAL_BLOCK_TIMEOUT", 10)
async def test_ota_manager_stall_after_downloading_again() -> None:
    """Test that the final-block timeout only applies while the last block is wanted."""
    assert FW_IMAGE.firmware is not None
    header = FW_IMAGE.firmware.header
    image_data = FW_IMAGE.firmware.serialize()

    app = make_app({})
    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = zigpy.profiles.zha.DeviceType.PUMP
    ota = ep.add_output_cluster(Ota.cluster_id)

    loop = asyncio.get_running_loop()
    offsets: list[int] = []

    def request_block(offset: int) -> None:
        app.packet_received(
            make_packet(
                dev,
                ota,
                "image_block",
                field_control=Ota.ImageBlockCommand.FieldControl(0),
                manufacturer_code=header.manufacturer_id,
                image_type=header.image_type,
                file_version=header.file_version,
                file_offset=offset,
                maximum_data_size=50,
            )
        )

    async def send_packet(packet: t.ZigbeePacket) -> None:
        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = ota.deserialize(packet.data.serialize())

        if isinstance(cmd, Ota.ImageNotifyCommand):
            # The device asks for the last block, then starts over and goes silent
            loop.call_soon(request_block, len(image_data) - 10)
        elif isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema):
            offsets.append(cmd.file_offset)

            if cmd.file_offset != 0:
                loop.call_soon(request_block, 0)

    app.send_packet = AsyncMock(side_effect=send_packet)

    # Stop the general cluster handler from interfering
    dev.ota_in_progress = True

    async with asyncio.timeout(2):
        status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.TIMEOUT
    assert offsets == [len(image_data) - 10, 0]


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.1)
async def test_ota_manger_device_reject(
    image_with_metadata: OtaImageWithMetadata,
) -> None:
    img = image_with_metadata

    app = make_app({})
    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)
    dev.model = "model1"
    dev.manufacturer = "manufacturer1"

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = zigpy.profiles.zha.DeviceType.PUMP

    ota = ep.add_output_cluster(Ota.cluster_id)

    async def send_packet(packet: t.ZigbeePacket):
        assert img.firmware is not None

        if packet.cluster_id == Ota.cluster_id:
            hdr, cmd = ota.deserialize(packet.data.serialize())
            if isinstance(cmd, Ota.ImageNotifyCommand):
                dev.application.packet_received(
                    make_packet(
                        dev,
                        ota,
                        "query_next_image",
                        field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                        manufacturer_code=img.firmware.header.manufacturer_id,
                        image_type=img.firmware.header.image_type,
                        # We claim our current version is higher than the file version
                        current_file_version=img.firmware.header.file_version + 10,
                        hardware_version=1,
                    )
                )

    dev.application.send_packet = AsyncMock(side_effect=send_packet)

    status = await dev.update_firmware(img)
    assert status == foundation.Status.NO_IMAGE_AVAILABLE


async def test_ota_manager():
    """Test that device firmware updates execute the expected calls."""

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)

    with mock_attribute_reads(
        cluster, {"current_file_version": FW_IMAGE.firmware.header.file_version - 10}
    ):
        await dev.initialize()

    # Stop the general cluster handler from interfering
    dev.ota_in_progress = True

    reconstructed_firmware = bytearray()

    async def send_packet(packet: t.ZigbeePacket):
        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = cluster.deserialize(packet.data.serialize())
        assert FW_IMAGE.firmware is not None

        if isinstance(cmd, Ota.ImageNotifyCommand):
            assert cmd.query_jitter == 100

            # Ask for the next image
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    current_file_version=FW_IMAGE.firmware.header.file_version - 10,
                    hardware_version=1,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            assert cmd.status == foundation.Status.SUCCESS
            assert cmd.manufacturer_code == FW_IMAGE.firmware.header.manufacturer_id
            assert cmd.image_type == FW_IMAGE.firmware.header.image_type
            assert cmd.file_version == FW_IMAGE.firmware.header.file_version
            assert cmd.image_size == FW_IMAGE.firmware.header.image_size

            # Ask for the first block to get things started
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "image_block",
                    field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    file_version=FW_IMAGE.firmware.header.file_version,
                    file_offset=0,
                    maximum_data_size=40,
                    request_node_addr=dev.ieee,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema):
            assert cmd.status == foundation.Status.SUCCESS
            assert cmd.manufacturer_code == FW_IMAGE.firmware.header.manufacturer_id
            assert cmd.image_type == FW_IMAGE.firmware.header.image_type
            assert cmd.file_version == FW_IMAGE.firmware.header.file_version
            assert len(cmd.image_data) > 0

            reconstructed_firmware[
                cmd.file_offset : cmd.file_offset + len(cmd.image_data)
            ] = cmd.image_data

            if cmd.file_offset + len(cmd.image_data) == len(
                FW_IMAGE.firmware.serialize()
            ):
                # End the upgrade
                dev.application.packet_received(
                    make_packet(
                        dev,
                        cluster,
                        "upgrade_end",
                        status=foundation.Status.SUCCESS,
                        manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                        image_type=FW_IMAGE.firmware.header.image_type,
                        file_version=FW_IMAGE.firmware.header.file_version,
                    )
                )
            else:
                # Keep going
                dev.application.packet_received(
                    make_packet(
                        dev,
                        cluster,
                        "image_block",
                        field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                        manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                        image_type=FW_IMAGE.firmware.header.image_type,
                        file_version=FW_IMAGE.firmware.header.file_version,
                        file_offset=cmd.file_offset + 40,
                        maximum_data_size=40,
                        request_node_addr=dev.ieee,
                    )
                )

        elif isinstance(cmd, Ota.ClientCommandDefs.upgrade_end_response.schema):
            assert cmd.manufacturer_code == FW_IMAGE.firmware.header.manufacturer_id
            assert cmd.image_type == FW_IMAGE.firmware.header.image_type
            assert cmd.file_version == FW_IMAGE.firmware.header.file_version
            assert cmd.current_time == 0
            assert cmd.upgrade_time == 0
        elif isinstance(
            cmd,
            foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Read_Attributes
            ].schema,
        ):
            assert cmd.attribute_ids == [Ota.AttributeDefs.current_file_version.id]

            req_hdr, req_cmd = cluster._create_request(
                general=True,
                command_id=foundation.GeneralCommand.Read_Attributes_rsp,
                schema=foundation.GENERAL_COMMANDS[
                    foundation.GeneralCommand.Read_Attributes_rsp
                ].schema,
                tsn=hdr.tsn,
                disable_default_response=True,
                direction=foundation.Direction.Server_to_Client,
                args=(),
                kwargs={
                    "status_records": [
                        foundation.ReadAttributeRecord(
                            attrid=Ota.AttributeDefs.current_file_version.id,
                            status=foundation.Status.SUCCESS,
                            value=foundation.TypeValue(
                                type=foundation.DATA_TYPES.pytype_to_datatype_id(
                                    t.uint32_t
                                ),
                                value=FW_IMAGE.firmware.header.file_version,
                            ),
                        )
                    ]
                },
            )

            dev.application.packet_received(
                t.ZigbeePacket(
                    src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=dev.nwk),
                    src_ep=1,
                    dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
                    dst_ep=1,
                    tsn=hdr.tsn,
                    profile_id=260,
                    cluster_id=cluster.cluster_id,
                    data=t.SerializableBytes(req_hdr.serialize() + req_cmd.serialize()),
                    lqi=255,
                    rssi=-30,
                )
            )

    dev.application.send_packet = AsyncMock(side_effect=send_packet)
    progress_callback = MagicMock()
    result = await update_firmware(dev, FW_IMAGE, progress_callback)

    image_size = FW_IMAGE.firmware.header.image_size
    assert progress_callback.mock_calls == [
        call(i, image_size, pytest.approx(i * 100 / image_size))
        for i in range(40, image_size + 1, 40)
    ] + [call(image_size, image_size, 100.0)]
    assert result == foundation.Status.SUCCESS

    assert bytes(reconstructed_firmware) == FW_IMAGE.firmware.serialize()


async def test_ota_manager_image_page():
    """Test that device firmware updates execute the expected calls."""

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)

    with mock_attribute_reads(
        cluster, {"current_file_version": FW_IMAGE.firmware.header.file_version - 10}
    ):
        await dev.initialize()

    # Stop the general cluster handler from interfering
    dev.ota_in_progress = True

    reconstructed_firmware = bytearray()

    async def send_packet(packet: t.ZigbeePacket):
        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = cluster.deserialize(packet.data.serialize())
        assert FW_IMAGE.firmware is not None

        if isinstance(cmd, Ota.ImageNotifyCommand):
            assert cmd.query_jitter == 100

            # Ask for the next image
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    current_file_version=FW_IMAGE.firmware.header.file_version - 10,
                    hardware_version=1,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            assert cmd.status == foundation.Status.SUCCESS
            assert cmd.manufacturer_code == FW_IMAGE.firmware.header.manufacturer_id
            assert cmd.image_type == FW_IMAGE.firmware.header.image_type
            assert cmd.file_version == FW_IMAGE.firmware.header.file_version
            assert cmd.image_size == FW_IMAGE.firmware.header.image_size

            # Ask for the first page to get things started
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "image_page",
                    field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    file_version=FW_IMAGE.firmware.header.file_version,
                    file_offset=0,
                    maximum_data_size=5,
                    page_size=40,
                    response_spacing=0,
                    request_node_addr=dev.ieee,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema):
            assert cmd.status == foundation.Status.SUCCESS
            assert cmd.manufacturer_code == FW_IMAGE.firmware.header.manufacturer_id
            assert cmd.image_type == FW_IMAGE.firmware.header.image_type
            assert cmd.file_version == FW_IMAGE.firmware.header.file_version
            assert len(cmd.image_data) > 0

            if cmd.file_offset + len(cmd.image_data) > len(reconstructed_firmware):
                reconstructed_firmware.extend(
                    b"\x00"
                    * (
                        cmd.file_offset
                        + len(cmd.image_data)
                        - len(reconstructed_firmware)
                    )
                )

            reconstructed_firmware[
                cmd.file_offset : cmd.file_offset + len(cmd.image_data)
            ] = cmd.image_data

            if cmd.file_offset + len(cmd.image_data) == len(
                FW_IMAGE.firmware.serialize()
            ):
                # End the upgrade
                dev.application.packet_received(
                    make_packet(
                        dev,
                        cluster,
                        "upgrade_end",
                        status=foundation.Status.SUCCESS,
                        manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                        image_type=FW_IMAGE.firmware.header.image_type,
                        file_version=FW_IMAGE.firmware.header.file_version,
                    )
                )
            else:
                current_page_start = (cmd.file_offset // 40) * 40
                current_page = reconstructed_firmware[
                    current_page_start : current_page_start + 40
                ]

                # Only ask for another page if the current one has been filled
                if (
                    current_page_start + 40 >= len(FW_IMAGE.firmware.serialize())
                    and len(current_page)
                    == len(FW_IMAGE.firmware.serialize()) - current_page_start
                ) or len(current_page) == 40:
                    # Keep going
                    dev.application.packet_received(
                        make_packet(
                            dev,
                            cluster,
                            "image_page",
                            field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                            manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                            image_type=FW_IMAGE.firmware.header.image_type,
                            file_version=FW_IMAGE.firmware.header.file_version,
                            file_offset=cmd.file_offset + 5,
                            maximum_data_size=5,
                            page_size=40,
                            response_spacing=0,
                            request_node_addr=dev.ieee,
                        )
                    )

        elif isinstance(cmd, Ota.ClientCommandDefs.upgrade_end_response.schema):
            assert cmd.manufacturer_code == FW_IMAGE.firmware.header.manufacturer_id
            assert cmd.image_type == FW_IMAGE.firmware.header.image_type
            assert cmd.file_version == FW_IMAGE.firmware.header.file_version
            assert cmd.current_time == 0
            assert cmd.upgrade_time == 0
        elif isinstance(
            cmd,
            foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Read_Attributes
            ].schema,
        ):
            assert cmd.attribute_ids == [Ota.AttributeDefs.current_file_version.id]

            req_hdr, req_cmd = cluster._create_request(
                general=True,
                command_id=foundation.GeneralCommand.Read_Attributes_rsp,
                schema=foundation.GENERAL_COMMANDS[
                    foundation.GeneralCommand.Read_Attributes_rsp
                ].schema,
                tsn=hdr.tsn,
                disable_default_response=True,
                direction=foundation.Direction.Server_to_Client,
                args=(),
                kwargs={
                    "status_records": [
                        foundation.ReadAttributeRecord(
                            attrid=Ota.AttributeDefs.current_file_version.id,
                            status=foundation.Status.SUCCESS,
                            value=foundation.TypeValue(
                                type=foundation.DATA_TYPES.pytype_to_datatype_id(
                                    t.uint32_t
                                ),
                                value=FW_IMAGE.firmware.header.file_version,
                            ),
                        )
                    ]
                },
            )

            dev.application.packet_received(
                t.ZigbeePacket(
                    src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=dev.nwk),
                    src_ep=1,
                    dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
                    dst_ep=1,
                    tsn=hdr.tsn,
                    profile_id=260,
                    cluster_id=cluster.cluster_id,
                    data=t.SerializableBytes(req_hdr.serialize() + req_cmd.serialize()),
                    lqi=255,
                    rssi=-30,
                )
            )

    dev.application.send_packet = AsyncMock(side_effect=send_packet)
    progress_callback = MagicMock()
    result = await update_firmware(dev, FW_IMAGE, progress_callback)

    assert result == foundation.Status.SUCCESS

    image_size = FW_IMAGE.firmware.header.image_size
    assert progress_callback.mock_calls == [
        call(i, image_size, pytest.approx(i / image_size * 100))
        for i in range(5, image_size + 1, 5)
    ]


async def test_ota_manager_image_page_invalid_size():
    """Test that the OTA manager fails properly with invalid image page requests."""

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)

    with mock_attribute_reads(
        cluster, {"current_file_version": FW_IMAGE.firmware.header.file_version - 10}
    ):
        await dev.initialize()

    # Stop the general cluster handler from interfering
    dev.ota_in_progress = True

    async def send_packet(packet: t.ZigbeePacket):
        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = cluster.deserialize(packet.data.serialize())
        assert FW_IMAGE.firmware is not None

        if isinstance(cmd, Ota.ImageNotifyCommand):
            assert cmd.query_jitter == 100

            # Ask for the next image
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    current_file_version=FW_IMAGE.firmware.header.file_version - 10,
                    hardware_version=1,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            assert cmd.status == foundation.Status.SUCCESS
            assert cmd.manufacturer_code == FW_IMAGE.firmware.header.manufacturer_id
            assert cmd.image_type == FW_IMAGE.firmware.header.image_type
            assert cmd.file_version == FW_IMAGE.firmware.header.file_version
            assert cmd.image_size == FW_IMAGE.firmware.header.image_size

            # Ask for the first page to get things started
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "image_page",
                    field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    file_version=FW_IMAGE.firmware.header.file_version,
                    file_offset=FW_IMAGE.firmware.header.image_size,
                    maximum_data_size=5,
                    page_size=40,
                    response_spacing=0,
                    request_node_addr=dev.ieee,
                )
            )

    dev.application.send_packet = AsyncMock(side_effect=send_packet)
    progress_callback = MagicMock()
    result = await update_firmware(dev, FW_IMAGE, progress_callback)

    assert result == foundation.Status.MALFORMED_COMMAND


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.1)
async def test_ota_manager_image_page_failure():
    """Test that the OTA manager fails properly with invalid image page requests."""

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)

    with mock_attribute_reads(
        cluster, {"current_file_version": FW_IMAGE.firmware.header.file_version - 10}
    ):
        await dev.initialize()

    # Stop the general cluster handler from interfering
    dev.ota_in_progress = True

    start_failing = False

    async def send_packet(packet: t.ZigbeePacket):
        nonlocal start_failing

        if start_failing:
            raise DeliveryError("Broken")

        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = cluster.deserialize(packet.data.serialize())
        assert FW_IMAGE.firmware is not None

        if isinstance(cmd, Ota.ImageNotifyCommand):
            assert cmd.query_jitter == 100

            # Ask for the next image
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    current_file_version=FW_IMAGE.firmware.header.file_version - 10,
                    hardware_version=1,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            assert cmd.status == foundation.Status.SUCCESS
            assert cmd.manufacturer_code == FW_IMAGE.firmware.header.manufacturer_id
            assert cmd.image_type == FW_IMAGE.firmware.header.image_type
            assert cmd.file_version == FW_IMAGE.firmware.header.file_version
            assert cmd.image_size == FW_IMAGE.firmware.header.image_size

            # Ask for the first page to get things started
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "image_page",
                    field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    file_version=FW_IMAGE.firmware.header.file_version,
                    file_offset=0,
                    maximum_data_size=5,
                    page_size=40,
                    response_spacing=0,
                    request_node_addr=dev.ieee,
                )
            )

            start_failing = True

    dev.application.send_packet = AsyncMock(side_effect=send_packet)
    progress_callback = MagicMock()
    result = await update_firmware(dev, FW_IMAGE, progress_callback)

    assert result != foundation.Status.SUCCESS


@pytest.mark.parametrize("use_pages", [False, True])
@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.1)
@patch("zigpy.ota.manager.FINAL_BLOCK_TIMEOUT", 0.5)
async def test_ota_manager_final_block_timeout(use_pages: bool) -> None:
    """Test that the final image block is given a longer timeout for verification."""

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)

    with mock_attribute_reads(
        cluster, {"current_file_version": FW_IMAGE.firmware.header.file_version - 10}
    ):
        await dev.initialize()

    # Stop the general cluster handler from interfering
    dev.ota_in_progress = True

    page_size = 40
    # Pages must hold more than one block, otherwise the final block of the image is
    # also the first block of its page and offset bugs cannot be observed
    max_data_size = 20 if use_pages else page_size
    image_size = len(FW_IMAGE.firmware.serialize())

    def request_block(offset: int) -> None:
        if use_pages:
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "image_page",
                    field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    file_version=FW_IMAGE.firmware.header.file_version,
                    file_offset=offset,
                    maximum_data_size=max_data_size,
                    page_size=page_size,
                    response_spacing=0,
                    request_node_addr=dev.ieee,
                )
            )
        else:
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "image_block",
                    field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    file_version=FW_IMAGE.firmware.header.file_version,
                    file_offset=offset,
                    maximum_data_size=max_data_size,
                    request_node_addr=dev.ieee,
                )
            )

    final_block_sent_at = None

    async def send_packet(packet: t.ZigbeePacket):
        nonlocal final_block_sent_at

        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = cluster.deserialize(packet.data.serialize())

        if isinstance(cmd, Ota.ImageNotifyCommand):
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    current_file_version=FW_IMAGE.firmware.header.file_version - 10,
                    hardware_version=1,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            request_block(0)
        elif isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema):
            next_offset = cmd.file_offset + len(cmd.image_data)

            # The device never sends `upgrade_end`, it just goes silent
            if next_offset >= image_size:
                final_block_sent_at = time.monotonic()
                return

            # The manager sends the rest of the current page on its own
            if use_pages and next_offset % page_size != 0:
                return

            request_block(next_offset)

    dev.application.send_packet = AsyncMock(side_effect=send_packet)

    result = await update_firmware(dev, FW_IMAGE)

    assert final_block_sent_at is not None
    elapsed = time.monotonic() - final_block_sent_at

    assert result == foundation.Status.TIMEOUT
    assert 0.5 <= elapsed < 1.5


async def test_ota_manager_deferred_download():
    """Test that firmware is fetched at install time for trusted providers."""

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)

    with mock_attribute_reads(
        cluster, {"current_file_version": FW_IMAGE.firmware.header.file_version - 10}
    ):
        await dev.initialize()

    # Create an image without firmware (simulating deferred download)
    deferred_image = zigpy.ota.OtaImageWithMetadata(
        metadata=FW_IMAGE.metadata.replace(trusted=True),
        firmware=None,
    )

    # Stop the general cluster handler from interfering
    dev.ota_in_progress = True

    async def send_packet(packet: t.ZigbeePacket):
        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = cluster.deserialize(packet.data.serialize())
        assert FW_IMAGE.firmware is not None

        if isinstance(cmd, Ota.ImageNotifyCommand):
            # Device rejects the update to end the test quickly
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    # Claim current version is higher than file version
                    current_file_version=FW_IMAGE.firmware.header.file_version + 10,
                    hardware_version=1,
                )
            )

    dev.application.send_packet = AsyncMock(side_effect=send_packet)

    # Mock fetch() to return the complete image
    mock_fetch = AsyncMock(return_value=FW_IMAGE)
    with patch.object(OtaImageWithMetadata, "fetch", mock_fetch):
        # Run firmware update with the deferred image
        result = await update_firmware(dev, deferred_image)

        # fetch() should have been called exactly once
        mock_fetch.assert_awaited_once_with()

    # The update itself returns NO_IMAGE_AVAILABLE because the device rejected it
    assert result == foundation.Status.NO_IMAGE_AVAILABLE


async def test_ota_manager_deferred_download_failure():
    """Test that a fetch failure during deferred download propagates correctly."""

    deferred_image = zigpy.ota.OtaImageWithMetadata(
        metadata=FW_IMAGE.metadata.replace(trusted=True),
        firmware=None,
    )

    mock_fetch = AsyncMock(side_effect=aiohttp.ClientError("Download failed"))
    with (
        patch.object(OtaImageWithMetadata, "fetch", mock_fetch),
        pytest.raises(
            zigpy.exceptions.OtaImageDownloadError,
            match="^Failed to download the firmware image: Download failed$",
        ) as exc_info,
    ):
        await update_firmware(MagicMock(), deferred_image)

    assert isinstance(exc_info.value.__cause__, aiohttp.ClientError)


async def test_ota_manager_deferred_download_failure_empty_message():
    """Test that a fetch failure without a message names the exception type."""

    deferred_image = zigpy.ota.OtaImageWithMetadata(
        metadata=FW_IMAGE.metadata.replace(trusted=True),
        firmware=None,
    )

    mock_fetch = AsyncMock(side_effect=ValueError())
    with (
        patch.object(OtaImageWithMetadata, "fetch", mock_fetch),
        pytest.raises(
            zigpy.exceptions.OtaImageDownloadError,
            match=r"^Failed to download the firmware image: ValueError\(\)$",
        ),
    ):
        await update_firmware(MagicMock(), deferred_image)


async def test_ota_manager_deferred_download_timeout():
    """Test that a download timeout is not reported as a bare `TimeoutError`."""

    deferred_image = zigpy.ota.OtaImageWithMetadata(
        metadata=FW_IMAGE.metadata.replace(trusted=True),
        firmware=None,
    )

    async def slow_fetch(*args, **kwargs):
        await asyncio.sleep(10)

    with (
        patch.object(zigpy.ota, "OTA_FETCH_TIMEOUT", 0.01),
        patch.object(OtaImageWithMetadata, "fetch", slow_fetch),
        pytest.raises(
            zigpy.exceptions.OtaImageDownloadError,
            match="^Timed out downloading the firmware image$",
        ) as exc_info,
    ):
        await update_firmware(MagicMock(), deferred_image)

    assert isinstance(exc_info.value.__cause__, TimeoutError)
    # Callers telling an unresponsive device apart from a failed download rely on this
    assert not isinstance(exc_info.value, TimeoutError)


async def test_ota_manager_deferred_download_cancelled():
    """Test that cancelling the update during the download is not wrapped."""

    deferred_image = zigpy.ota.OtaImageWithMetadata(
        metadata=FW_IMAGE.metadata.replace(trusted=True),
        firmware=None,
    )

    mock_fetch = AsyncMock(side_effect=asyncio.CancelledError())
    with (
        patch.object(OtaImageWithMetadata, "fetch", mock_fetch),
        pytest.raises(asyncio.CancelledError),
    ):
        await update_firmware(MagicMock(), deferred_image)


def _make_sleepy_device(
    image_notify: Callable[[], Awaitable[None]],
    first_block_delay: float = 0,
    block_response_error: Exception | None = None,
    upgrade_end_response_delay: float = 0,
    logical_type: zdo_t.LogicalType = zdo_t.LogicalType.EndDevice,
    wake_up_with_block: bool = False,
) -> tuple[zigpy.device.Device, Cluster, list[str], Callable[[], None]]:
    """Create a sleepy end device that only talks to us when it wants to.

    Returns the device, its OTA cluster, a log of OTA commands, and a callback that
    makes the device query for the next image (i.e. it was woken up). With
    `wake_up_with_block`, the device instead starts by requesting the first block.
    """
    assert FW_IMAGE.firmware is not None
    header = FW_IMAGE.firmware.header
    image_data = FW_IMAGE.firmware.serialize()

    app = make_app({})
    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77"))
    dev.node_desc = make_node_desc(logical_type=logical_type)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = zigpy.profiles.zha.DeviceType.REMOTE_CONTROL
    ota = ep.add_output_cluster(Ota.cluster_id)

    log: list[str] = []
    loop = asyncio.get_running_loop()

    def query_next_image() -> None:
        log.append("query_next_image")
        app.packet_received(
            make_packet(
                dev,
                ota,
                "query_next_image",
                field_control=Ota.QueryNextImageCommand.FieldControl(0),
                manufacturer_code=header.manufacturer_id,
                image_type=header.image_type,
                current_file_version=header.file_version - 10,
            )
        )

    def image_block(offset: int) -> None:
        app.packet_received(
            make_packet(
                dev,
                ota,
                "image_block",
                field_control=Ota.ImageBlockCommand.FieldControl(0),
                manufacturer_code=header.manufacturer_id,
                image_type=header.image_type,
                file_version=header.file_version,
                file_offset=offset,
                maximum_data_size=50,
            )
        )

    def upgrade_end() -> None:
        log.append("upgrade_end")
        app.packet_received(
            make_packet(
                dev,
                ota,
                "upgrade_end",
                status=foundation.Status.SUCCESS,
                manufacturer_code=header.manufacturer_id,
                image_type=header.image_type,
                file_version=header.file_version,
            )
        )

    async def send_packet(packet: t.ZigbeePacket) -> None:
        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = ota.deserialize(packet.data.serialize())

        if isinstance(cmd, Ota.ImageNotifyCommand):
            log.append("image_notify")
            await image_notify()
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            log.append(f"query_next_image_response:{cmd.status.name}")

            if cmd.status == foundation.Status.SUCCESS:
                loop.call_later(first_block_delay, image_block, 0)
        elif isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema):
            if block_response_error is not None:
                # The device never receives the block and goes back to sleep
                log.append("image_block_response:error")
                raise block_response_error

            if cmd.status != foundation.Status.SUCCESS:
                log.append(f"image_block_response:{cmd.status.name}")
                return

            next_offset = cmd.file_offset + len(cmd.image_data)

            if next_offset < len(image_data):
                loop.call_soon(image_block, next_offset)
            else:
                log.append("image_block_response:last")
                loop.call_soon(upgrade_end)
        elif isinstance(cmd, Ota.ClientCommandDefs.upgrade_end_response.schema):
            # Delivering the response can take a while, e.g. if it needs to be retried
            await asyncio.sleep(upgrade_end_response_delay)
            log.append("upgrade_end_response")

    app.send_packet = AsyncMock(side_effect=send_packet)

    def request_first_block() -> None:
        log.append("image_block")
        image_block(0)

    return (
        dev,
        ota,
        log,
        request_first_block if wake_up_with_block else query_next_image,
    )


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.3)
async def test_ota_manager_notify_failure_device_requests_later() -> None:
    """Test that a failed image notify does not abort the OTA."""
    loop = asyncio.get_running_loop()
    attempts = 0

    async def image_notify() -> None:
        nonlocal attempts
        attempts += 1

        if attempts == 3:
            # The device is woken up near the end of the waiting period
            loop.call_later(0.2, wake_up)

        raise DeliveryError("Failed to send request: APS_NO_ACK")

    # The first block request comes after the original waiting period has passed, it
    # is only served because the query restarted the stall timer
    dev, _ota, log, wake_up = _make_sleepy_device(image_notify, first_block_delay=0.2)

    dev.ota_in_progress = True
    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.SUCCESS
    assert log == [
        # All three attempts fail
        "image_notify",
        "image_notify",
        "image_notify",
        "query_next_image",
        "query_next_image_response:SUCCESS",
        "image_block_response:last",
        "upgrade_end",
        "upgrade_end_response",
    ]


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.3)
async def test_ota_manager_notify_failure_timeout() -> None:
    """Test that the OTA times out if the device never requests the image."""

    async def image_notify() -> None:
        raise DeliveryError("Failed to send request: APS_NO_ACK")

    dev, _ota, log, _wake_up = _make_sleepy_device(image_notify)

    dev.ota_in_progress = True
    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.TIMEOUT
    assert log == ["image_notify", "image_notify", "image_notify"]


@pytest.mark.parametrize(
    "exc", [TimeoutError(), DeliveryError("Failed to send request: MAC_NO_ACK")]
)
async def test_ota_manager_fast_poll_failure(exc: Exception) -> None:
    """Test that the OTA continues if the device cannot be asked to poll faster."""

    async def image_notify() -> None:
        wake_up()

    dev, _ota, log, wake_up = _make_sleepy_device(image_notify)

    # Binding the Poll Control cluster of a sleeping device fails
    dev.begin_fast_polling = AsyncMock(side_effect=exc)

    dev.ota_in_progress = True
    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.SUCCESS
    assert len(dev.begin_fast_polling.mock_calls) == 1
    assert log == [
        "image_notify",
        "query_next_image",
        "query_next_image_response:SUCCESS",
        "image_block_response:last",
        "upgrade_end",
        "upgrade_end_response",
    ]


async def test_ota_manager_request_during_fast_poll_setup() -> None:
    """Test that OTA requests are answered while the device is asked to poll faster."""

    async def image_notify() -> None:
        pytest.fail("The device already requested the image")

    dev, _ota, log, wake_up = _make_sleepy_device(image_notify)

    async def begin_fast_polling(*args, **kwargs) -> None:
        # The device is woken up to start the update and queries for the image while
        # the Poll Control cluster is being bound
        wake_up()
        await asyncio.sleep(0.1)
        raise TimeoutError

    dev.begin_fast_polling = AsyncMock(side_effect=begin_fast_polling)

    dev.ota_in_progress = True
    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.SUCCESS
    assert log == [
        "query_next_image",
        "query_next_image_response:SUCCESS",
        "image_block_response:last",
        "upgrade_end",
        "upgrade_end_response",
    ]


@pytest.mark.parametrize(
    "logical_type", [zdo_t.LogicalType.EndDevice, zdo_t.LogicalType.Router]
)
@pytest.mark.parametrize("wake_up_with_block", [False, True])
@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.3)
async def test_ota_manager_device_request_cancels_pending_notify(
    logical_type: zdo_t.LogicalType,
    wake_up_with_block: bool,
) -> None:
    """Test that a device request while the image notify is pending cancels it."""

    notify_cancelled = asyncio.Event()

    async def image_notify() -> None:
        # The radio takes a long time to report delivery failure for end devices
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            notify_cancelled.set()
            raise

    dev, _ota, log, wake_up = _make_sleepy_device(
        image_notify, logical_type=logical_type, wake_up_with_block=wake_up_with_block
    )
    asyncio.get_running_loop().call_later(0.1, wake_up)

    dev.ota_in_progress = True

    async with asyncio.timeout(2):
        status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.SUCCESS
    assert notify_cancelled.is_set()
    assert dev._concurrent_requests_semaphore.active_requests == 0

    # The notify is not retried once the device has sent its first request
    first_request = (
        ["image_block"]
        if wake_up_with_block
        else ["query_next_image", "query_next_image_response:SUCCESS"]
    )
    assert log == [
        "image_notify",
        *first_request,
        "image_block_response:last",
        "upgrade_end",
        "upgrade_end_response",
    ]


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.3)
async def test_ota_manager_device_goes_silent_during_notify() -> None:
    """Test that the OTA times out if the device stops responding mid-transfer."""

    async def image_notify() -> None:
        await asyncio.sleep(10)

    dev, _ota, log, wake_up = _make_sleepy_device(
        image_notify,
        block_response_error=DeliveryError("Failed to send request: MAC_NO_ACK"),
    )
    asyncio.get_running_loop().call_later(0.1, wake_up)

    dev.ota_in_progress = True

    async with asyncio.timeout(2):
        status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.TIMEOUT
    assert log == [
        "image_notify",
        "query_next_image",
        "query_next_image_response:SUCCESS",
        # All three attempts fail
        "image_block_response:error",
        "image_block_response:error",
        "image_block_response:error",
    ]


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.3)
@patch("zigpy.ota.manager.FINAL_BLOCK_TIMEOUT", 1.0)
async def test_ota_manager_final_block_timeout_not_shortened() -> None:
    """Test that device requests do not shorten the final block timeout."""

    async def image_notify() -> None:
        raise DeliveryError("Failed to send request: APS_NO_ACK")

    # Sending the upgrade end response takes longer than `MAX_TIME_WITHOUT_PROGRESS`
    dev, _ota, log, wake_up = _make_sleepy_device(
        image_notify, upgrade_end_response_delay=0.5
    )
    asyncio.get_running_loop().call_later(0.1, wake_up)

    dev.ota_in_progress = True
    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.SUCCESS
    assert log[-3:] == [
        "image_block_response:last",
        "upgrade_end",
        "upgrade_end_response",
    ]


async def test_ota_manager_cancelled_during_notify() -> None:
    """Test that cancelling the OTA while the image notify is pending cleans up."""

    notify_started = asyncio.Event()
    notify_cancelled = asyncio.Event()

    async def image_notify() -> None:
        notify_started.set()

        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            notify_cancelled.set()
            raise

    dev, _ota, log, _wake_up = _make_sleepy_device(image_notify)

    task = asyncio.create_task(dev.update_firmware(FW_IMAGE))
    await notify_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert notify_cancelled.is_set()
    assert not dev.ota_in_progress
    assert dev._concurrent_requests_semaphore.active_requests == 0
    assert log == ["image_notify"]


@pytest.mark.parametrize(
    "end_status",
    [
        foundation.Status.INVALID_IMAGE,
        foundation.Status.REQUIRE_MORE_IMAGE,
        foundation.Status.ABORT,
    ],
)
@pytest.mark.parametrize(
    ("disable_default_response", "default_rsp_fails"),
    [(False, False), (True, False), (False, True)],
)
async def test_ota_manager_upgrade_end_failure(
    end_status: foundation.Status,
    disable_default_response: bool,
    default_rsp_fails: bool,
) -> None:
    """A failed Upgrade End Request gets a Default Response, not an Upgrade End
    Response telling the device to upgrade (ZCL R8 11.13.9.4).
    """

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)
    assert FW_IMAGE.firmware is not None

    sent_commands = []
    upgrade_end_tsns = []

    async def send_packet(packet: t.ZigbeePacket):
        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = cluster.deserialize(packet.data.serialize())
        sent_commands.append((hdr, cmd))

        if hdr.frame_control.is_general and default_rsp_fails:
            raise DeliveryError("Failed to send the Default Response")

        if isinstance(cmd, Ota.ImageNotifyCommand):
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl(0),
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    current_file_version=FW_IMAGE.firmware.header.file_version - 10,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            assert cmd.status == foundation.Status.SUCCESS

            # The device downloads the image and rejects it
            upgrade_end = make_packet(
                dev,
                cluster,
                "upgrade_end",
                disable_default_response=disable_default_response,
                status=end_status,
                manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                image_type=FW_IMAGE.firmware.header.image_type,
                file_version=FW_IMAGE.firmware.header.file_version,
            )
            upgrade_end_tsns.append(upgrade_end.tsn)
            dev.application.packet_received(upgrade_end)

    dev.application.send_packet = AsyncMock(side_effect=send_packet)

    # The update ends with the device's status, also when the Default Response fails
    status = await dev.update_firmware(FW_IMAGE)
    assert status == end_status

    # No Upgrade End Response is sent for a failed upgrade
    assert not any(
        hdr.frame_control.is_cluster
        and hdr.command_id == Ota.ClientCommandDefs.upgrade_end_response.id
        for hdr, cmd in sent_commands
    )

    # It is acknowledged with a successful Default Response instead
    default_rsps = [
        (hdr, cmd)
        for hdr, cmd in sent_commands
        if hdr.frame_control.is_general
        and hdr.command_id == foundation.GeneralCommand.Default_Response
    ]

    # Not when the request has its disable-default-response bit set
    if disable_default_response:
        assert not default_rsps
        return

    # A failed send is retried by the device's request retries
    if default_rsp_fails:
        assert len(default_rsps) > 1
    else:
        assert len(default_rsps) == 1

    for rsp_hdr, rsp in default_rsps:
        assert rsp_hdr.tsn == upgrade_end_tsns[0]
        assert rsp.command_id == Ota.ServerCommandDefs.upgrade_end.id
        assert rsp.status == foundation.Status.SUCCESS


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.1)
async def test_ota_manager_image_page_zero_data_size() -> None:
    """An Image Page Request with a maximum data size of zero is malformed, it does not
    make the OTA manager send empty Image Block Responses forever.
    """

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)
    assert FW_IMAGE.firmware is not None

    empty_blocks = 0
    malformed_rsps = 0

    async def send_packet(packet: t.ZigbeePacket):
        nonlocal empty_blocks, malformed_rsps

        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = cluster.deserialize(packet.data.serialize())

        if isinstance(cmd, Ota.ImageNotifyCommand):
            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl(0),
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    current_file_version=FW_IMAGE.firmware.header.file_version - 10,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            assert cmd.status == foundation.Status.SUCCESS

            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "image_page",
                    field_control=0,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    file_version=FW_IMAGE.firmware.header.file_version,
                    file_offset=0,
                    maximum_data_size=0,
                    page_size=40,
                    response_spacing=0,
                )
            )
        elif (
            isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema)
            and cmd.status == foundation.Status.MALFORMED_COMMAND
        ):
            malformed_rsps += 1
        elif (
            isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema)
            and cmd.status == foundation.Status.SUCCESS
            and not cmd.image_data
        ):
            empty_blocks += 1

            # Stop the loop for the test, it would never end otherwise
            if empty_blocks >= 100:
                raise RuntimeError("Too many empty image blocks")

    dev.application.send_packet = AsyncMock(side_effect=send_packet)

    status = await dev.update_firmware(FW_IMAGE)

    assert empty_blocks == 0
    assert malformed_rsps == 1
    assert status == foundation.Status.MALFORMED_COMMAND


def _make_device_for_late_upgrade_end() -> tuple[
    zigpy.device.Device, Cluster, list[tuple[foundation.ZCLHeader, object]]
]:
    """Create a device that downloads the image but never finishes in time."""
    assert FW_IMAGE.firmware is not None
    header = FW_IMAGE.firmware.header
    image_data = FW_IMAGE.firmware.serialize()

    app = make_app({})
    dev = app.add_device(nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77"))
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = zigpy.profiles.zha.DeviceType.PUMP
    ota = ep.add_output_cluster(Ota.cluster_id)

    loop = asyncio.get_running_loop()
    sent: list[tuple[foundation.ZCLHeader, object]] = []

    def request_block(offset: int) -> None:
        app.packet_received(
            make_packet(
                dev,
                ota,
                "image_block",
                field_control=Ota.ImageBlockCommand.FieldControl(0),
                manufacturer_code=header.manufacturer_id,
                image_type=header.image_type,
                file_version=header.file_version,
                file_offset=offset,
                maximum_data_size=50,
            )
        )

    async def send_packet(packet: t.ZigbeePacket) -> None:
        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = ota.deserialize(packet.data.serialize())
        sent.append((hdr, cmd))

        if isinstance(cmd, Ota.ImageNotifyCommand):
            app.packet_received(
                make_packet(
                    dev,
                    ota,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl(0),
                    manufacturer_code=header.manufacturer_id,
                    image_type=header.image_type,
                    current_file_version=header.file_version - 10,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            loop.call_soon(request_block, 0)
        elif isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema):
            next_offset = cmd.file_offset + len(cmd.image_data)

            # The device verifies the image for a long time after the last block
            if next_offset < len(image_data):
                loop.call_soon(request_block, next_offset)

    app.send_packet = AsyncMock(side_effect=send_packet)

    return dev, ota, sent


def _upgrade_end_packet(
    dev: zigpy.device.Device,
    ota: Cluster,
    status: foundation.Status,
    *,
    file_version: int | None = None,
) -> t.ZigbeePacket:
    assert FW_IMAGE.firmware is not None
    header = FW_IMAGE.firmware.header

    return make_packet(
        dev,
        ota,
        "upgrade_end",
        status=status,
        manufacturer_code=header.manufacturer_id,
        image_type=header.image_type,
        file_version=header.file_version if file_version is None else file_version,
    )


@patch("zigpy.ota.manager.FINAL_BLOCK_TIMEOUT", 0.1)
async def test_ota_late_upgrade_end_is_answered() -> None:
    """Test that an Upgrade End Request after the OTA timed out is still answered."""
    assert FW_IMAGE.firmware is not None
    header = FW_IMAGE.firmware.header

    dev, ota, sent = _make_device_for_late_upgrade_end()

    status = await dev.update_firmware(FW_IMAGE)
    assert status == foundation.Status.TIMEOUT
    assert not dev.ota_in_progress

    sent.clear()

    # The device finishes verifying the image after the update has ended
    packet = _upgrade_end_packet(dev, ota, foundation.Status.SUCCESS)
    dev.application.packet_received(packet)
    await asyncio.sleep(0.01)

    assert len(sent) == 1
    hdr, cmd = sent[0]
    assert hdr.tsn == packet.tsn
    assert cmd == Ota.ClientCommandDefs.upgrade_end_response.schema(
        manufacturer_code=header.manufacturer_id,
        image_type=header.image_type,
        file_version=header.file_version,
        current_time=0,
        upgrade_time=0,
    )


@pytest.mark.parametrize(
    ("status", "file_version"),
    [
        # The device reports an image we never sent it
        (foundation.Status.SUCCESS, None),
        # The device failed to verify the image
        (foundation.Status.INVALID_IMAGE, None),
    ],
)
async def test_ota_unknown_upgrade_end_gets_default_response(
    status: foundation.Status, file_version: int | None
) -> None:
    """Test that other Upgrade End Requests outside an OTA get a Default Response."""
    dev, ota, sent = _make_device_for_late_upgrade_end()

    # No image was ever transferred to the device
    packet = _upgrade_end_packet(dev, ota, status)
    dev.application.packet_received(packet)
    await asyncio.sleep(0.01)

    assert len(sent) == 1
    hdr, cmd = sent[0]
    assert hdr.tsn == packet.tsn
    assert hdr.command_id == foundation.GeneralCommand.Default_Response
    assert cmd.command_id == Ota.ServerCommandDefs.upgrade_end.id
    assert cmd.status == foundation.Status.SUCCESS


@patch("zigpy.ota.manager.FINAL_BLOCK_TIMEOUT", 0.1)
async def test_ota_late_upgrade_end_other_version_not_answered() -> None:
    """Test that a late Upgrade End Request for another image is not acknowledged."""
    assert FW_IMAGE.firmware is not None

    dev, ota, sent = _make_device_for_late_upgrade_end()

    status = await dev.update_firmware(FW_IMAGE)
    assert status == foundation.Status.TIMEOUT

    sent.clear()

    packet = _upgrade_end_packet(
        dev,
        ota,
        foundation.Status.SUCCESS,
        file_version=FW_IMAGE.firmware.header.file_version + 1,
    )
    dev.application.packet_received(packet)
    await asyncio.sleep(0.01)

    assert len(sent) == 1
    hdr, _cmd = sent[0]
    assert hdr.command_id == foundation.GeneralCommand.Default_Response


async def test_ota_image_page_outside_update_is_aborted() -> None:
    """Test that an Image Page Request outside an OTA is aborted like a block request."""
    assert FW_IMAGE.firmware is not None
    header = FW_IMAGE.firmware.header

    dev, ota, sent = _make_device_for_late_upgrade_end()

    packet = make_packet(
        dev,
        ota,
        "image_page",
        field_control=0,
        manufacturer_code=header.manufacturer_id,
        image_type=header.image_type,
        file_version=header.file_version,
        file_offset=0,
        maximum_data_size=50,
        page_size=500,
        response_spacing=0,
    )
    dev.application.packet_received(packet)
    await asyncio.sleep(0.01)

    assert len(sent) == 1
    hdr, cmd = sent[0]
    assert hdr.tsn == packet.tsn
    assert cmd.status == foundation.Status.ABORT


@pytest.mark.parametrize("ota_in_progress", [False, True])
@pytest.mark.parametrize("disable_default_response", [False, True])
async def test_ota_query_specific_file_unsupported(
    ota_in_progress: bool, disable_default_response: bool
) -> None:
    """Test that a Query Device Specific File Request is answered as unsupported."""
    dev, ota, sent = _make_device_for_late_upgrade_end()
    dev.ota_in_progress = ota_in_progress

    packet = make_packet(
        dev,
        ota,
        "query_specific_file",
        disable_default_response=disable_default_response,
        request_node_addr=dev.ieee,
        manufacturer_code=0x1234,
        image_type=0x0090,
        file_version=0x00000001,
        current_zigbee_stack_version=2,
    )
    dev.application.packet_received(packet)
    await asyncio.sleep(0.01)

    assert len(sent) == 1
    hdr, cmd = sent[0]
    assert hdr.tsn == packet.tsn
    assert hdr.command_id == foundation.GeneralCommand.Default_Response
    assert cmd.status == foundation.Status.UNSUP_CLUSTER_COMMAND


@pytest.mark.parametrize("during_last_block", [False, True])
@patch("zigpy.ota.manager.FINAL_BLOCK_TIMEOUT", 0.1)
async def test_ota_late_upgrade_end_after_failed_verification(
    during_last_block: bool,
) -> None:
    """Test that an image the device rejected is not applied by a late request."""
    dev, ota, sent = _make_device_for_late_upgrade_end()

    loop = asyncio.get_running_loop()
    send_packet = dev.application.send_packet.side_effect

    async def reject_image(packet: t.ZigbeePacket) -> None:
        await send_packet(packet)

        hdr, cmd = ota.deserialize(packet.data.serialize())
        if isinstance(
            cmd, Ota.ClientCommandDefs.image_block_response.schema
        ) and cmd.file_offset + len(cmd.image_data) == len(
            FW_IMAGE.firmware.serialize()
        ):
            # The device fails to verify the image, possibly before the send of the
            # last block has completed
            loop.call_soon(
                dev.application.packet_received,
                _upgrade_end_packet(dev, ota, foundation.Status.INVALID_IMAGE),
            )

            if during_last_block:
                await asyncio.sleep(0.05)

    dev.application.send_packet = AsyncMock(side_effect=reject_image)

    status = await dev.update_firmware(FW_IMAGE)
    assert status == foundation.Status.INVALID_IMAGE

    sent.clear()

    dev.application.packet_received(
        _upgrade_end_packet(dev, ota, foundation.Status.SUCCESS)
    )
    await asyncio.sleep(0.01)

    assert len(sent) == 1
    hdr, _cmd = sent[0]
    assert hdr.command_id == foundation.GeneralCommand.Default_Response


def _other_image_query(dev: zigpy.device.Device, ota: Cluster) -> t.ZigbeePacket:
    """Create a query for the device's other firmware image (e.g. a second chip)."""
    assert FW_IMAGE.firmware is not None
    header = FW_IMAGE.firmware.header

    return make_packet(
        dev,
        ota,
        "query_next_image",
        field_control=Ota.QueryNextImageCommand.FieldControl(0),
        manufacturer_code=header.manufacturer_id,
        image_type=header.image_type ^ 0x0100,
        current_file_version=0x00030104,
    )


@pytest.mark.parametrize("when", ["before", "after", "during_transfer"])
async def test_ota_manager_query_for_other_image(when: str) -> None:
    """Test that a query for another image of the device does not end the update."""
    loop = asyncio.get_running_loop()

    async def image_notify() -> None:
        if when == "before":
            dev.application.packet_received(_other_image_query(dev, ota))
            wake_up()
        elif when == "after":
            wake_up()
            dev.application.packet_received(_other_image_query(dev, ota))
        else:
            wake_up()
            loop.call_later(
                0.01, dev.application.packet_received, _other_image_query(dev, ota)
            )

    dev, ota, log, wake_up = _make_sleepy_device(image_notify)

    dev.ota_in_progress = True
    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.SUCCESS
    assert log[-3:] == [
        "image_block_response:last",
        "upgrade_end",
        "upgrade_end_response",
    ]


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.2)
async def test_ota_manager_only_other_image_queried() -> None:
    """Test that an update ends if the device only queries for its other image."""

    async def image_notify() -> None:
        dev.application.packet_received(_other_image_query(dev, ota))

    dev, ota, log, _wake_up = _make_sleepy_device(image_notify)

    dev.ota_in_progress = True
    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.NO_IMAGE_AVAILABLE
    assert log == ["image_notify", "query_next_image_response:NO_IMAGE_AVAILABLE"]


async def test_ota_manager_query_for_other_image_during_fast_poll_setup() -> None:
    """Test that a query for another image does not stop us from notifying."""

    async def image_notify() -> None:
        wake_up()

    dev, ota, log, wake_up = _make_sleepy_device(image_notify)

    async def begin_fast_polling(*args, **kwargs) -> None:
        # The device's other chip queries while we prepare the device
        dev.application.packet_received(_other_image_query(dev, ota))
        await asyncio.sleep(0.01)

    dev.begin_fast_polling = AsyncMock(side_effect=begin_fast_polling)

    dev.ota_in_progress = True
    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.SUCCESS
    assert log[:3] == [
        "query_next_image_response:NO_IMAGE_AVAILABLE",
        "image_notify",
        "query_next_image",
    ]


async def test_ota_manager_query_matches_image_metadata() -> None:
    """Test that the image type of the index metadata identifies this image."""
    assert FW_IMAGE.firmware is not None
    header = FW_IMAGE.firmware.header

    # The index lists the image under another image type than its file header
    image = FW_IMAGE.replace(
        metadata=FW_IMAGE.metadata.replace(image_type=header.image_type + 1)
    )

    async def image_notify() -> None:
        log.append("query_next_image")
        dev.application.packet_received(
            make_packet(
                dev,
                ota,
                "query_next_image",
                field_control=Ota.QueryNextImageCommand.FieldControl(0),
                manufacturer_code=header.manufacturer_id,
                image_type=header.image_type + 1,
                current_file_version=header.file_version - 10,
            )
        )

    dev, ota, log, _wake_up = _make_sleepy_device(image_notify)

    dev.ota_in_progress = True
    status = await update_firmware(dev, image)

    assert status == foundation.Status.SUCCESS
    assert "query_next_image_response:SUCCESS" in log


def _make_paging_device(
    on_image_block: Callable[[], Awaitable[None]],
    *,
    page_size: int,
    response_spacing: int = 0,
) -> tuple[
    zigpy.device.Device,
    list[t.ZigbeePacket],
    Callable[[], None],
    Callable[[foundation.Status], None],
]:
    """Create a device that downloads the image with Image Page Requests.

    Returns the device, the Image Block Response packets sent to it, and callbacks
    that make it request the first page and send an Upgrade End Request. The device
    requests the first page once it has queried for the image, `on_image_block` is
    called for every block sent to it.
    """
    assert FW_IMAGE.firmware is not None
    header = FW_IMAGE.firmware.header

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)

    # Stop the general cluster handler from interfering
    dev.ota_in_progress = True

    blocks: list[t.ZigbeePacket] = []

    def request_page() -> None:
        app.packet_received(
            make_packet(
                dev,
                cluster,
                "image_page",
                field_control=0,
                manufacturer_code=header.manufacturer_id,
                image_type=header.image_type,
                file_version=header.file_version,
                file_offset=0,
                maximum_data_size=50,
                page_size=page_size,
                response_spacing=response_spacing,
            )
        )

    def upgrade_end(status: foundation.Status) -> None:
        app.packet_received(
            make_packet(
                dev,
                cluster,
                "upgrade_end",
                status=status,
                manufacturer_code=header.manufacturer_id,
                image_type=header.image_type,
                file_version=header.file_version,
            )
        )

    async def send_packet(packet: t.ZigbeePacket) -> None:
        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = cluster.deserialize(packet.data.serialize())

        if isinstance(cmd, Ota.ImageNotifyCommand):
            app.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "query_next_image",
                    field_control=Ota.QueryNextImageCommand.FieldControl(0),
                    manufacturer_code=header.manufacturer_id,
                    image_type=header.image_type,
                    current_file_version=header.file_version - 10,
                )
            )
        elif isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            request_page()
        elif isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema):
            blocks.append(packet)
            await on_image_block()

    app.send_packet = AsyncMock(side_effect=send_packet)

    return dev, blocks, request_page, upgrade_end


def _block_offsets(dev: zigpy.device.Device, blocks: list[t.ZigbeePacket]) -> list[int]:
    cluster = dev.endpoints[1].out_clusters[Ota.cluster_id]
    return [cluster.deserialize(p.data.serialize())[1].file_offset for p in blocks]


@pytest.mark.parametrize("cancel", [False, True])
async def test_ota_manager_image_page_stops_when_update_ends(cancel: bool) -> None:
    """The blocks of an image page stop once the device aborts the update or the
    update is cancelled, they are not sent after `update_firmware` has returned.
    """

    async def on_image_block() -> None:
        if len(blocks) != 3:
            return

        # The device gives up after a few blocks, a page request sent after that is
        # not served either
        if not cancel:
            upgrade_end(foundation.Status.ABORT)
            request_page()
            return

        # The update is cancelled while delivering a block takes a long time
        update.cancel()
        await asyncio.sleep(10)

    # The whole image is requested as a single page
    dev, blocks, request_page, upgrade_end = _make_paging_device(
        on_image_block,
        page_size=len(FW_IMAGE.firmware.serialize()),
        response_spacing=10,
    )

    update = asyncio.create_task(update_firmware(dev, FW_IMAGE))

    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await update
    else:
        assert await update == foundation.Status.ABORT

    # A block still being sent is cancelled
    await asyncio.sleep(0)
    assert dev._concurrent_requests_semaphore.active_requests == 0

    sent_blocks = len(blocks)
    await asyncio.sleep(0.2)

    assert _block_offsets(dev, blocks) == [0, 50, 100]
    assert len(blocks) == sent_blocks


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.3)
async def test_ota_manager_image_page_repeated_request() -> None:
    """A repeated Image Page Request restarts the page instead of sending it twice
    in parallel.
    """

    async def on_image_block() -> None:
        # The device requests the page again, e.g. after its page timeout
        if len(blocks) == 3:
            request_page()

    dev, blocks, request_page, _upgrade_end = _make_paging_device(
        on_image_block, page_size=500, response_spacing=5
    )

    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.TIMEOUT
    assert _block_offsets(dev, blocks) == [0, 50, 100, *range(0, 500, 50)]


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.1)
async def test_ota_manager_image_page_no_aps_ack() -> None:
    """Image Block Responses for an Image Page Request are sent without APS acks
    (ZCL R8 11.13.7.4).
    """

    dev, blocks, _request_page, _upgrade_end = _make_paging_device(
        AsyncMock(), page_size=100
    )

    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.TIMEOUT
    assert len(blocks) == 2
    assert all(t.TransmitOptions.ACK not in p.tx_options for p in blocks)


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.1)
async def test_ota_manager_image_page_long_response_spacing() -> None:
    """A response spacing longer than the stall timeout does not end the update while
    the page is being sent.
    """

    dev, blocks, _request_page, _upgrade_end = _make_paging_device(
        AsyncMock(), page_size=150, response_spacing=200
    )

    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.TIMEOUT
    assert _block_offsets(dev, blocks) == [0, 50, 100]


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.2)
async def test_ota_manager_image_page_request_restarts_stall_timer() -> None:
    """A device repeating its page request while nothing can be sent to it keeps the
    update alive.
    """
    loop = asyncio.get_running_loop()
    coordinator_ready = asyncio.Event()

    async def on_image_block() -> None:
        # The coordinator does not confirm any send for a while, during which the
        # device asks for the page again
        await coordinator_ready.wait()

    dev, blocks, request_page, _upgrade_end = _make_paging_device(
        on_image_block, page_size=150
    )

    for i in range(1, 4):
        loop.call_later(0.1 * i, request_page)

    loop.call_later(0.35, coordinator_ready.set)

    status = await update_firmware(dev, FW_IMAGE)

    assert status == foundation.Status.TIMEOUT
    assert _block_offsets(dev, blocks)[-3:] == [0, 50, 100]
