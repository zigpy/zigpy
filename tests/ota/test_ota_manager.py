from unittest.mock import AsyncMock, patch

from tests.conftest import make_app, make_node_desc
from tests.ota.test_ota_metadata import image_with_metadata  # noqa: F401
import zigpy.device
from zigpy.ota import OtaImageWithMetadata
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters import Cluster
from zigpy.zcl.clusters.general import Ota
import zigpy.zdo.types as zdo_t


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
