import itertools
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from tests.conftest import add_initialized_device, make_app, make_node_desc
from tests.ota.test_ota_metadata import image_with_metadata  # noqa: F401
import zigpy.application
import zigpy.device
import zigpy.exceptions
from zigpy.exceptions import DeliveryError
from zigpy.ota import OtaImageWithMetadata
import zigpy.ota.image
from zigpy.ota.manager import update_firmware
import zigpy.state
import zigpy.types as t
import zigpy.util
from zigpy.zcl import foundation
from zigpy.zcl.clusters import Cluster
from zigpy.zcl.clusters.general import Ota
from zigpy.zdo import types as zdo_t
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


def make_packet(dev: zigpy.device.Device, cluster: Cluster, cmd_name: str, **kwargs):
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


async def test_ota_manager_image_page_failure():
    """Test that the OTA manager fails properly with invalid image page requests."""

    app = make_app({})
    dev = add_initialized_device(
        app, nwk=0x1234, ieee=t.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster = dev.endpoints[1].add_output_cluster(Ota.cluster_id)

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

    assert result == foundation.Status.FAILURE
