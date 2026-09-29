import asyncio
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
    src_ep: int = 1,
    **kwargs,
):
    req_hdr, req_cmd = cluster._create_request(
        general=False,
        command_id=cluster.commands_by_name[cmd_name].id,
        schema=cluster.commands_by_name[cmd_name].schema,
        disable_default_response=False,
        direction=foundation.Direction.Client_to_Server,
        args=(),
        kwargs=kwargs,
    )

    return t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=dev.nwk),
        src_ep=src_ep,
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


@pytest.mark.parametrize("device_ep", [1, 2])
async def test_ota_manager_multiple_ota_endpoints(device_ep: int) -> None:
    """Test that an update driven from any OTA endpoint of a device is answered."""

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )

    ep2 = dev.add_endpoint(2)
    ep2.status = zigpy.endpoint.Status.ZDO_INIT
    ep2.profile_id = 260
    ep2.device_type = zigpy.profiles.zha.DeviceType.PUMP

    for ep_id in (1, 2):
        dev.endpoints[ep_id].add_output_cluster(Ota.cluster_id)

    cluster = dev.endpoints[device_ep].out_clusters[Ota.cluster_id]

    reconstructed_firmware = bytearray()
    reply_endpoints = set()

    async def send_packet(packet: t.ZigbeePacket):
        if packet.cluster_id != Ota.cluster_id:
            return

        hdr, cmd = cluster.deserialize(packet.data.serialize())
        assert FW_IMAGE.firmware is not None

        if isinstance(cmd, Ota.ImageNotifyCommand):
            # `image_notify` is sent to the first endpoint exposing the cluster
            assert packet.dst_ep == 1

            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "query_next_image",
                    src_ep=device_ep,
                    field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                    manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                    image_type=FW_IMAGE.firmware.header.image_type,
                    current_file_version=FW_IMAGE.firmware.header.file_version - 10,
                    hardware_version=1,
                )
            )
            return

        # Every reply to the device is sent back to the endpoint that asked
        reply_endpoints.add(packet.dst_ep)

        if isinstance(cmd, Ota.ClientCommandDefs.query_next_image_response.schema):
            assert cmd.status == foundation.Status.SUCCESS

            dev.application.packet_received(
                make_packet(
                    dev,
                    cluster,
                    "image_block",
                    src_ep=device_ep,
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

            reconstructed_firmware[
                cmd.file_offset : cmd.file_offset + len(cmd.image_data)
            ] = cmd.image_data

            if cmd.file_offset + len(cmd.image_data) == len(
                FW_IMAGE.firmware.serialize()
            ):
                dev.application.packet_received(
                    make_packet(
                        dev,
                        cluster,
                        "upgrade_end",
                        src_ep=device_ep,
                        status=foundation.Status.SUCCESS,
                        manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                        image_type=FW_IMAGE.firmware.header.image_type,
                        file_version=FW_IMAGE.firmware.header.file_version,
                    )
                )
            else:
                dev.application.packet_received(
                    make_packet(
                        dev,
                        cluster,
                        "image_block",
                        src_ep=device_ep,
                        field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                        manufacturer_code=FW_IMAGE.firmware.header.manufacturer_id,
                        image_type=FW_IMAGE.firmware.header.image_type,
                        file_version=FW_IMAGE.firmware.header.file_version,
                        file_offset=cmd.file_offset + 40,
                        maximum_data_size=40,
                        request_node_addr=dev.ieee,
                    )
                )

    dev.application.send_packet = AsyncMock(side_effect=send_packet)
    result = await update_firmware(dev, FW_IMAGE)

    assert result == foundation.Status.SUCCESS
    assert bytes(reconstructed_firmware) == FW_IMAGE.firmware.serialize()
    assert reply_endpoints == {device_ep}


async def test_ota_manager_registration_failure_unwinds() -> None:
    """Test that a failure to own every OTA command leaves nothing registered."""

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)

    # Something else already owns the last command the manager registers
    unsub = cluster.respond_to_command(
        Ota.ServerCommandDefs.upgrade_end, AsyncMock(), default=False
    )

    with pytest.raises(ValueError, match="a non-default owner is already registered"):
        await update_firmware(dev, FW_IMAGE)

    unsub()

    # The earlier registrations did not leak: the cluster's own defaults answer again
    cluster.image_block_response = AsyncMock()
    packet = make_packet(
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
    dev.packet_received(packet)
    await asyncio.sleep(0)

    assert cluster.image_block_response.mock_calls == [
        call(foundation.Status.ABORT, tsn=packet.tsn)
    ]


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
        pytest.raises(aiohttp.ClientError, match="Download failed"),
    ):
        await update_firmware(MagicMock(), deferred_image)
