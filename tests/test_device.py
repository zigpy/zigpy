import asyncio
from datetime import datetime, timezone
import logging
from unittest.mock import call

import pytest

from zigpy import device, endpoint
import zigpy.application
import zigpy.exceptions
from zigpy.ota import OtaImagesResult
import zigpy.ota.image
from zigpy.profiles import zha
import zigpy.state
import zigpy.types as t
import zigpy.util
from zigpy.zcl import ClusterType, foundation
from zigpy.zcl.clusters.general import Basic, Ota, PollControl
from zigpy.zdo import types as zdo_t

from .async_mock import AsyncMock, MagicMock, patch, sentinel


@pytest.fixture
def dev(monkeypatch, app_mock):
    monkeypatch.setattr(device, "APS_REPLY_TIMEOUT_EXTENDED", 0.1)
    ieee = t.EUI64(map(t.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))

    dev = device.Device(app_mock, ieee, 65535)
    node_desc = zdo_t.NodeDescriptor(1, 1, 1, 4, 5, 6, 7, 8)
    with patch.object(
        dev.zdo, "Node_Desc_req", new=AsyncMock(return_value=(0, 0xFFFF, node_desc))
    ):
        yield dev


async def test_initialize(monkeypatch, dev):
    async def mockrequest(*args, **kwargs):
        return [0, None, [0, 1, 2, 3, 4]]

    async def mockepinit(self, *args, **kwargs):
        self.status = endpoint.Status.ZDO_INIT
        self.add_input_cluster(Basic.cluster_id)

    async def mock_ep_get_model_info(self):
        if self.endpoint_id == 1:
            return None, None
        elif self.endpoint_id == 2:
            return "Model", None
        elif self.endpoint_id == 3:
            return None, "Manufacturer"
        else:
            return "Model2", "Manufacturer2"

    monkeypatch.setattr(endpoint.Endpoint, "initialize", mockepinit)
    monkeypatch.setattr(endpoint.Endpoint, "get_model_info", mock_ep_get_model_info)
    dev.zdo.Active_EP_req = mockrequest
    await dev.initialize()

    assert dev.endpoints[0] is dev.zdo
    assert 1 in dev.endpoints
    assert 2 in dev.endpoints
    assert 3 in dev.endpoints
    assert 4 in dev.endpoints
    assert dev._application.device_initialized.call_count == 1
    assert dev.is_initialized

    # First one for each is chosen
    assert dev.model == "Model"
    assert dev.manufacturer == "Manufacturer"

    dev.schedule_initialize()
    assert dev._application.device_initialized.call_count == 2

    await dev.initialize()
    assert dev._application.device_initialized.call_count == 3


async def test_initialize_fail(dev):
    async def mockrequest(nwk, tries=None, delay=None):
        return [1, dev.nwk, []]

    dev.zdo.Active_EP_req = mockrequest
    await dev.initialize()

    assert not dev.is_initialized
    assert not dev.has_non_zdo_endpoints


@patch("zigpy.device.Device.get_node_descriptor", AsyncMock())
async def test_initialize_ep_failed(monkeypatch, dev):
    async def mockrequest(req, nwk, tries=None, delay=None):
        return [0, None, [1, 2]]

    async def mockepinit(self):
        raise AttributeError

    monkeypatch.setattr(endpoint.Endpoint, "initialize", mockepinit)

    dev.zdo.request = mockrequest
    await dev.initialize()

    assert not dev.is_initialized
    assert dev.application.listener_event.call_count == 1
    assert dev.application.listener_event.call_args[0][0] == "device_init_failure"


async def test_failed_request(dev):
    assert dev.last_seen is None
    dev._application.send_packet = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("Uh oh")
    )
    with pytest.raises(zigpy.exceptions.DeliveryError):
        await dev.request(1, 2, 3, 4, 5, b"1234")
    assert dev.last_seen is None


def test_skip_configuration(dev):
    assert dev.skip_configuration is False
    dev.skip_configuration = True
    assert dev.skip_configuration is True


def test_radio_details(dev):
    dev.radio_details(1, 2)
    assert dev.lqi == 1
    assert dev.rssi == 2

    dev.radio_details(lqi=3)
    assert dev.lqi == 3
    assert dev.rssi == 2

    dev.radio_details(rssi=4)
    assert dev.lqi == 3
    assert dev.rssi == 4


async def test_handle_message_deserialize_error(dev):
    ep = dev.add_endpoint(3)
    ep.deserialize = MagicMock(side_effect=ValueError)
    ep.handle_message = MagicMock()

    dev.packet_received(
        t.ZigbeePacket(
            profile_id=99,
            cluster_id=98,
            src_ep=3,
            dst_ep=3,
            data=t.SerializableBytes(b"abcd"),
            dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        )
    )

    assert ep.handle_message.call_count == 0


def test_endpoint_getitem(dev):
    ep = dev.add_endpoint(3)
    assert dev[3] is ep

    with pytest.raises(KeyError):
        dev[1]


async def test_broadcast(app_mock):
    app_mock.state.node_info.ieee = t.EUI64.convert("08:09:0A:0B:0C:0D:0E:0F")

    (profile, cluster, src_ep, dst_ep, data) = (
        zha.PROFILE_ID,
        1,
        2,
        3,
        b"\x02\x01\x00",
    )
    await device.broadcast(app_mock, profile, cluster, src_ep, dst_ep, 0, 0, 123, data)

    assert app_mock.send_packet.call_count == 1
    packet = app_mock.send_packet.mock_calls[0].args[0]

    assert packet.profile_id == profile
    assert packet.cluster_id == cluster
    assert packet.src_ep == src_ep
    assert packet.dst_ep == dst_ep
    assert packet.data.serialize() == data


async def _get_node_descriptor(dev, zdo_success=True, request_success=True):
    async def mockrequest(nwk, tries=None, delay=None, **kwargs):
        if not request_success:
            raise asyncio.TimeoutError

        status = 0 if zdo_success else 1
        return [status, nwk, zdo_t.NodeDescriptor.deserialize(b"abcdefghijklm")[0]]

    dev.zdo.Node_Desc_req = MagicMock(side_effect=mockrequest)
    return await dev.get_node_descriptor()


async def test_get_node_descriptor(dev):
    nd = await _get_node_descriptor(dev, zdo_success=True, request_success=True)

    assert nd is not None
    assert isinstance(nd, zdo_t.NodeDescriptor)
    assert dev.zdo.Node_Desc_req.call_count == 1


async def test_get_node_descriptor_no_reply(dev):
    with pytest.raises(asyncio.TimeoutError):
        await _get_node_descriptor(dev, zdo_success=True, request_success=False)

    assert dev.zdo.Node_Desc_req.call_count == 1


async def test_get_node_descriptor_fail(dev):
    with pytest.raises(zigpy.exceptions.InvalidResponse):
        await _get_node_descriptor(dev, zdo_success=False, request_success=True)

    assert dev.zdo.Node_Desc_req.call_count == 1


async def test_add_to_group(dev, monkeypatch):
    grp_id, grp_name = 0x1234, "test group 0x1234"
    epmock = MagicMock(spec_set=endpoint.Endpoint)
    monkeypatch.setattr(endpoint, "Endpoint", MagicMock(return_value=epmock))
    epmock.add_to_group = AsyncMock()

    dev.add_endpoint(3)
    dev.add_endpoint(4)

    await dev.add_to_group(grp_id, grp_name)
    assert epmock.add_to_group.call_count == 2
    assert epmock.add_to_group.call_args[0][0] == grp_id
    assert epmock.add_to_group.call_args[0][1] == grp_name


async def test_remove_from_group(dev, monkeypatch):
    grp_id = 0x1234
    epmock = MagicMock(spec_set=endpoint.Endpoint)
    monkeypatch.setattr(endpoint, "Endpoint", MagicMock(return_value=epmock))
    epmock.remove_from_group = AsyncMock()

    dev.add_endpoint(3)
    dev.add_endpoint(4)

    await dev.remove_from_group(grp_id)
    assert epmock.remove_from_group.call_count == 2
    assert epmock.remove_from_group.call_args[0][0] == grp_id


async def test_schedule_group_membership(dev, caplog):
    """Test preempting group membership scan."""

    p1 = patch.object(dev, "group_membership_scan", new=AsyncMock())
    caplog.set_level(logging.DEBUG)
    with p1 as scan_mock:
        dev.schedule_group_membership_scan()
        await asyncio.sleep(0)
        assert scan_mock.call_count == 1
        assert scan_mock.await_count == 1
        assert not [r for r in caplog.records if r.name != "asyncio"]

        scan_mock.reset_mock()
        dev.schedule_group_membership_scan()
        dev.schedule_group_membership_scan()
        await asyncio.sleep(0)
        assert scan_mock.await_count == 1
        assert "Cancelling old group rescan" in caplog.text


async def test_group_membership_scan(dev):
    ep = dev.add_endpoint(1)
    ep.status = endpoint.Status.ZDO_INIT

    with patch.object(ep, "group_membership_scan", new=AsyncMock()):
        await dev.group_membership_scan()
        assert ep.group_membership_scan.await_count == 1


def test_device_manufacture_id_override(dev):
    """Test manufacturer id override."""

    assert dev.manufacturer_id is None
    assert dev.manufacturer_id_override is None

    dev.node_desc = zdo_t.NodeDescriptor(1, 64, 142, 4153, 82, 255, 0, 255, 0)
    assert dev.manufacturer_id == 4153

    dev.manufacturer_id_override = 2345
    assert dev.manufacturer_id == 2345

    dev.node_desc = None
    assert dev.manufacturer_id == 2345


def test_device_name(dev):
    """Test device name property."""

    assert dev.nwk == 0xFFFF
    assert dev.name == "0xFFFF"


def test_device_last_seen(dev, monkeypatch):
    """Test the device last_seen property handles updates and broadcasts events."""

    monkeypatch.setattr(dev, "listener_event", MagicMock())
    assert dev.last_seen is None

    dev.last_seen = 0
    epoch = datetime(1970, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
    assert dev.last_seen == epoch.timestamp()

    dev.listener_event.assert_called_once_with("device_last_seen_updated", epoch)
    dev.listener_event.reset_mock()

    now = datetime.now(timezone.utc)
    dev.last_seen = now
    dev.listener_event.assert_called_once_with("device_last_seen_updated", now)


async def test_ignore_unknown_endpoint(dev, caplog):
    """Test that unknown endpoints are ignored."""
    dev.add_endpoint(1)

    with caplog.at_level(logging.DEBUG):
        dev.packet_received(
            t.ZigbeePacket(
                profile_id=260,
                cluster_id=1,
                src_ep=2,
                dst_ep=3,
                data=t.SerializableBytes(b"some data"),
                src=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK,
                    address=dev.nwk,
                ),
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK,
                    address=0x0000,
                ),
            )
        )

    assert "Ignoring message on unknown endpoint" in caplog.text


async def test_handle_custom_profile(dev) -> None:
    """Test that custom profile messages are handled."""
    dev.add_endpoint(1)

    packet = t.ZigbeePacket(
        profile_id=0x1234,
        cluster_id=1,
        src_ep=1,
        dst_ep=1,
        data=t.SerializableBytes(b"custom data"),
        src=t.AddrModeAddress(
            addr_mode=t.AddrMode.NWK,
            address=dev.nwk,
        ),
        dst=t.AddrModeAddress(
            addr_mode=t.AddrMode.NWK,
            address=0x0000,
        ),
    )

    with patch.object(dev, "custom_profile_packet_received") as mock_handler:
        dev.packet_received(packet)

    assert mock_handler.mock_calls == [call(packet)]


async def test_handle_unknown_cluster(dev, caplog) -> None:
    """Test that unknown cluster messages are ignored."""
    dev.add_endpoint(1)

    with caplog.at_level(logging.DEBUG):
        dev.packet_received(
            t.ZigbeePacket(
                profile_id=260,
                cluster_id=0x9999,  # Unknown cluster
                src_ep=1,
                dst_ep=1,
                data=t.SerializableBytes(b"unknown cluster data"),
                src=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK,
                    address=dev.nwk,
                ),
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK,
                    address=0x0000,
                ),
            )
        )

    assert "Ignoring message on unknown cluster: 0x9999" in caplog.text


async def test_update_device_firmware_no_ota_cluster(dev):
    """Test that device firmware updates fails: no ota cluster."""
    with pytest.raises(ValueError, match="Cluster 0x0019 not found"):
        await dev.update_firmware(sentinel.firmware_image, sentinel.progress_callback)

    dev.add_endpoint(1)
    dev.endpoints[1].output_clusters = MagicMock(side_effect=KeyError)
    with pytest.raises(ValueError, match="Cluster 0x0019 not found"):
        await dev.update_firmware(sentinel.firmware_image, sentinel.progress_callback)


async def test_update_device_firmware_already_in_progress(dev, caplog):
    """Test that device firmware updates no ops when update is in progress."""
    dev.ota_in_progress = True
    await dev.update_firmware(sentinel.firmware_image, sentinel.progress_callback)
    assert "OTA already in progress" in caplog.text


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.1)
@patch("zigpy.device.AFTER_OTA_ATTR_READ_DELAY", 0.01)
@patch(
    "zigpy.device.OTA_RETRY_DECORATOR",
    zigpy.util.retryable_request(tries=1, delay=0.01),
)
async def test_update_device_firmware(monkeypatch, dev, caplog):
    """Test that device firmware updates execute the expected calls."""
    ep = dev.add_endpoint(1)
    cluster = zigpy.zcl.Cluster.from_id(ep, Ota.cluster_id, is_server=False)
    ep.add_output_cluster(Ota.cluster_id, cluster)

    async def mockrequest(nwk, tries=None, delay=None):
        return [0, None, [0, 1, 2, 3, 4]]

    async def mockepinit(self, *args, **kwargs):
        self.status = endpoint.Status.ZDO_INIT
        self.add_input_cluster(Basic.cluster_id)

    async def mock_ep_get_model_info(self):
        if self.endpoint_id == 1:
            return "Model2", "Manufacturer2"

    monkeypatch.setattr(endpoint.Endpoint, "initialize", mockepinit)
    monkeypatch.setattr(endpoint.Endpoint, "get_model_info", mock_ep_get_model_info)
    dev.zdo.Active_EP_req = mockrequest
    await dev.initialize()

    fw_image = zigpy.ota.OtaImageWithMetadata(
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
                image_size=56 + 2 + 4 + 8,
            ),
            subelements=[zigpy.ota.image.SubElement(tag_id=0x0000, data=b"fw_image")],
        ),
    )

    fw_image_force = fw_image.replace(
        firmware=fw_image.firmware.replace(
            header=fw_image.firmware.header.replace(
                file_version=0xFFFFFFFF - 1,
            )
        )
    )

    dev.application.ota.get_ota_images = MagicMock(
        return_value=OtaImagesResult(upgrades=(), downgrades=())
    )
    dev.update_firmware = MagicMock(wraps=dev.update_firmware)

    def make_packet(cmd_name: str, **kwargs):
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

    async def send_packet(packet: t.ZigbeePacket):
        if dev.update_firmware.mock_calls[-1].kwargs.get("force", False):
            active_fw_image = fw_image_force
        else:
            active_fw_image = fw_image

        if packet.cluster_id == Ota.cluster_id:
            hdr, cmd = cluster.deserialize(packet.data.serialize())
            if isinstance(cmd, Ota.ImageNotifyCommand):
                dev.application.packet_received(
                    make_packet(
                        "query_next_image",
                        field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                        manufacturer_code=active_fw_image.firmware.header.manufacturer_id,
                        image_type=active_fw_image.firmware.header.image_type,
                        current_file_version=(
                            active_fw_image.firmware.header.file_version - 10
                        ),
                        hardware_version=1,
                    )
                )
            elif isinstance(
                cmd, Ota.ClientCommandDefs.query_next_image_response.schema
            ):
                assert cmd.status == foundation.Status.SUCCESS
                assert (
                    cmd.manufacturer_code
                    == active_fw_image.firmware.header.manufacturer_id
                )
                assert cmd.image_type == active_fw_image.firmware.header.image_type
                assert cmd.file_version == active_fw_image.firmware.header.file_version
                assert cmd.image_size == active_fw_image.firmware.header.image_size
                dev.application.packet_received(
                    make_packet(
                        "image_block",
                        field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                        manufacturer_code=active_fw_image.firmware.header.manufacturer_id,
                        image_type=active_fw_image.firmware.header.image_type,
                        file_version=active_fw_image.firmware.header.file_version,
                        file_offset=0,
                        maximum_data_size=40,
                        request_node_addr=dev.ieee,
                    )
                )
            elif isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema):
                if cmd.file_offset == 0:
                    assert cmd.status == foundation.Status.SUCCESS
                    assert (
                        cmd.manufacturer_code
                        == active_fw_image.firmware.header.manufacturer_id
                    )
                    assert cmd.image_type == active_fw_image.firmware.header.image_type
                    assert (
                        cmd.file_version == active_fw_image.firmware.header.file_version
                    )
                    assert cmd.file_offset == 0
                    assert cmd.image_data == active_fw_image.firmware.serialize()[0:40]
                    dev.application.packet_received(
                        make_packet(
                            "image_block",
                            field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                            manufacturer_code=active_fw_image.firmware.header.manufacturer_id,
                            image_type=active_fw_image.firmware.header.image_type,
                            file_version=active_fw_image.firmware.header.file_version,
                            file_offset=40,
                            maximum_data_size=40,
                            request_node_addr=dev.ieee,
                        )
                    )
                elif cmd.file_offset == 40:
                    assert cmd.status == foundation.Status.SUCCESS
                    assert (
                        cmd.manufacturer_code
                        == active_fw_image.firmware.header.manufacturer_id
                    )
                    assert cmd.image_type == active_fw_image.firmware.header.image_type
                    assert (
                        cmd.file_version == active_fw_image.firmware.header.file_version
                    )
                    assert cmd.file_offset == 40
                    assert cmd.image_data == active_fw_image.firmware.serialize()[40:70]
                    dev.application.packet_received(
                        make_packet(
                            "upgrade_end",
                            status=foundation.Status.SUCCESS,
                            manufacturer_code=active_fw_image.firmware.header.manufacturer_id,
                            image_type=active_fw_image.firmware.header.image_type,
                            file_version=active_fw_image.firmware.header.file_version,
                        )
                    )

            elif isinstance(cmd, Ota.ClientCommandDefs.upgrade_end_response.schema):
                assert (
                    cmd.manufacturer_code
                    == active_fw_image.firmware.header.manufacturer_id
                )
                assert cmd.image_type == active_fw_image.firmware.header.image_type
                assert cmd.file_version == active_fw_image.firmware.header.file_version
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
                    direction=foundation.Direction.Client_to_Server,
                    args=(),
                    kwargs={
                        "status_records": [
                            foundation.ReadAttributeRecord(
                                attrid=Ota.AttributeDefs.current_file_version.id,
                                status=foundation.Status.SUCCESS,
                                value=foundation.TypeValue(
                                    type=foundation.DataTypeId.uint32,
                                    value=active_fw_image.firmware.header.file_version,
                                ),
                            )
                        ]
                    },
                )

                dev.application.packet_received(
                    t.ZigbeePacket(
                        src=t.AddrModeAddress(
                            addr_mode=t.AddrMode.NWK, address=dev.nwk
                        ),
                        src_ep=1,
                        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
                        dst_ep=1,
                        tsn=hdr.tsn,
                        profile_id=260,
                        cluster_id=cluster.cluster_id,
                        data=t.SerializableBytes(
                            req_hdr.serialize() + req_cmd.serialize()
                        ),
                        lqi=255,
                        rssi=-30,
                    )
                )

    dev.application.send_packet = AsyncMock(side_effect=send_packet)
    progress_callback = MagicMock()
    result = await dev.update_firmware(fw_image, progress_callback)
    assert (
        dev.endpoints[1]
        .out_clusters[Ota.cluster_id]
        ._attr_cache[Ota.AttributeDefs.current_file_version.id]
        == 0x12345678
    )

    assert dev.application.send_packet.await_count == 6
    assert progress_callback.call_count == 2
    assert progress_callback.call_args_list[0] == call(40, 70, 57.142857142857146)
    assert progress_callback.call_args_list[1] == call(70, 70, 100.0)
    assert result == foundation.Status.SUCCESS

    progress_callback.reset_mock()
    dev.application.send_packet.reset_mock()
    result = await dev.update_firmware(
        fw_image, progress_callback=progress_callback, force=True
    )

    assert dev.application.send_packet.await_count == 6
    assert progress_callback.call_count == 2
    assert progress_callback.call_args_list[0] == call(40, 70, 57.142857142857146)
    assert progress_callback.call_args_list[1] == call(70, 70, 100.0)
    assert result == foundation.Status.SUCCESS

    # _image_query_req exception test
    dev.application.send_packet.reset_mock()
    progress_callback.reset_mock()
    image_notify = cluster.image_notify
    cluster.image_notify = AsyncMock(side_effect=zigpy.exceptions.DeliveryError("Foo"))
    result = await dev.update_firmware(fw_image, progress_callback=progress_callback)
    assert dev.application.send_packet.await_count == 0
    assert progress_callback.call_count == 0
    assert "OTA image_notify handler exception" in caplog.text
    assert result != foundation.Status.SUCCESS
    cluster.image_notify = image_notify
    caplog.clear()

    # _image_query_req exception test
    dev.application.send_packet.reset_mock()
    progress_callback.reset_mock()
    query_next_image_response = cluster.query_next_image_response
    cluster.query_next_image_response = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("Foo")
    )
    result = await dev.update_firmware(fw_image, progress_callback=progress_callback)
    assert dev.application.send_packet.await_count == 1  # just image notify
    assert progress_callback.call_count == 0
    assert "OTA query_next_image handler exception" in caplog.text
    assert result != foundation.Status.SUCCESS
    cluster.query_next_image_response = query_next_image_response
    caplog.clear()

    # _image_block_req exception test
    dev.application.send_packet.reset_mock()
    progress_callback.reset_mock()
    image_block_response = cluster.image_block_response
    cluster.image_block_response = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("Foo")
    )
    result = await dev.update_firmware(fw_image, progress_callback=progress_callback)
    assert (
        dev.application.send_packet.await_count == 2
    )  # just image notify + query next image
    assert progress_callback.call_count == 0
    assert "OTA image_block handler exception" in caplog.text
    assert result != foundation.Status.SUCCESS
    cluster.image_block_response = image_block_response
    caplog.clear()

    # _upgrade_end exception test
    dev.application.send_packet.reset_mock()
    progress_callback.reset_mock()
    upgrade_end_response = cluster.upgrade_end_response
    cluster.upgrade_end_response = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("Foo")
    )
    result = await dev.update_firmware(fw_image, progress_callback=progress_callback)
    assert (
        dev.application.send_packet.await_count == 4
    )  # just image notify, qne, and 2 img blocks
    assert progress_callback.call_count == 2
    assert "OTA upgrade_end handler exception" in caplog.text
    assert result != foundation.Status.SUCCESS
    cluster.upgrade_end_response = upgrade_end_response
    caplog.clear()

    async def send_packet(packet: t.ZigbeePacket):
        if packet.cluster_id == Ota.cluster_id:
            hdr, cmd = cluster.deserialize(packet.data.serialize())
            if isinstance(cmd, Ota.ImageNotifyCommand):
                dev.application.packet_received(
                    make_packet(
                        "query_next_image",
                        field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                        manufacturer_code=fw_image.firmware.header.manufacturer_id,
                        image_type=fw_image.firmware.header.image_type,
                        current_file_version=fw_image.firmware.header.file_version - 10,
                        hardware_version=1,
                    )
                )
            elif isinstance(
                cmd, Ota.ClientCommandDefs.query_next_image_response.schema
            ):
                assert cmd.status == foundation.Status.SUCCESS
                assert cmd.manufacturer_code == fw_image.firmware.header.manufacturer_id
                assert cmd.image_type == fw_image.firmware.header.image_type
                assert cmd.file_version == fw_image.firmware.header.file_version
                assert cmd.image_size == fw_image.firmware.header.image_size
                dev.application.packet_received(
                    make_packet(
                        "image_block",
                        field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                        manufacturer_code=fw_image.firmware.header.manufacturer_id,
                        image_type=fw_image.firmware.header.image_type,
                        file_version=fw_image.firmware.header.file_version,
                        file_offset=300,
                        maximum_data_size=40,
                        request_node_addr=dev.ieee,
                    )
                )

    dev.application.send_packet = AsyncMock(side_effect=send_packet)

    progress_callback.reset_mock()
    image_block_response = cluster.image_block_response
    cluster.image_block_response = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("Foo")
    )
    result = await dev.update_firmware(fw_image, progress_callback=progress_callback)
    assert (
        dev.application.send_packet.await_count == 2
    )  # just image notify, qne, img block response fails
    assert progress_callback.call_count == 0
    assert "OTA image_block handler[MALFORMED_COMMAND] exception" in caplog.text
    assert result == foundation.Status.MALFORMED_COMMAND
    cluster.image_block_response = image_block_response


@patch("zigpy.ota.manager.MAX_TIME_WITHOUT_PROGRESS", 0.1)
@patch("zigpy.device.AFTER_OTA_ATTR_READ_DELAY", 0.01)
@patch(
    "zigpy.device.OTA_RETRY_DECORATOR",
    zigpy.util.retryable_request(tries=1, delay=0.01),
)
async def test_update_legrand_device_firmware(monkeypatch, dev, caplog):
    """Legrand device (manufacturer_code == 4129) firmware update expects the "image_block" command "maximum_data_size" to be complied with."""
    ep = dev.add_endpoint(1)
    cluster = zigpy.zcl.Cluster.from_id(ep, Ota.cluster_id, is_server=False)
    ep.add_output_cluster(Ota.cluster_id, cluster)

    async def mockrequest(nwk, tries=None, delay=None):
        return [0, None, [0, 1, 2, 3, 4]]

    async def mockepinit(self, *args, **kwargs):
        self.status = endpoint.Status.ZDO_INIT
        self.add_input_cluster(Basic.cluster_id)

    async def mock_ep_get_model_info(self):
        if self.endpoint_id == 1:
            return "SomeModel", "Legrand"

    monkeypatch.setattr(endpoint.Endpoint, "initialize", mockepinit)
    monkeypatch.setattr(endpoint.Endpoint, "get_model_info", mock_ep_get_model_info)
    dev.zdo.Active_EP_req = mockrequest
    await dev.initialize()

    fw_image = zigpy.ota.OtaImageWithMetadata(
        metadata=zigpy.ota.providers.BaseOtaImageMetadata(
            file_version=0x12345678,
            manufacturer_id=4129,
            image_type=0x90,
        ),
        firmware=zigpy.ota.image.OTAImage(
            header=zigpy.ota.image.OTAImageHeader(
                upgrade_file_id=zigpy.ota.image.OTAImageHeader.MAGIC_VALUE,
                file_version=0x12345678,
                image_type=0x90,
                manufacturer_id=4129,
                header_version=256,
                header_length=56,
                field_control=0,
                stack_version=2,
                header_string="This is a test header!",
                image_size=56 + 2 + 4 + 8,
            ),
            subelements=[zigpy.ota.image.SubElement(tag_id=0x0000, data=b"fw_image")],
        ),
    )

    fw_image_force = fw_image.replace(
        firmware=fw_image.firmware.replace(
            header=fw_image.firmware.header.replace(
                file_version=0xFFFFFFFF - 1,
            )
        )
    )

    dev.application.ota.get_ota_images = MagicMock(
        return_value=OtaImagesResult(upgrades=(), downgrades=())
    )
    dev.update_firmware = MagicMock(wraps=dev.update_firmware)

    def make_packet(cmd_name: str, **kwargs):
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

    async def send_packet(packet: t.ZigbeePacket):
        if dev.update_firmware.mock_calls[-1].kwargs.get("force", False):
            active_fw_image = fw_image_force
        else:
            active_fw_image = fw_image

        if packet.cluster_id == Ota.cluster_id:
            hdr, cmd = cluster.deserialize(packet.data.serialize())
            if isinstance(cmd, Ota.ImageNotifyCommand):
                dev.application.packet_received(
                    make_packet(
                        "query_next_image",
                        field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                        manufacturer_code=active_fw_image.firmware.header.manufacturer_id,
                        image_type=active_fw_image.firmware.header.image_type,
                        current_file_version=active_fw_image.firmware.header.file_version
                        - 10,
                        hardware_version=1,
                    )
                )
            elif isinstance(
                cmd, Ota.ClientCommandDefs.query_next_image_response.schema
            ):
                assert cmd.status == foundation.Status.SUCCESS
                assert (
                    cmd.manufacturer_code
                    == active_fw_image.firmware.header.manufacturer_id
                )
                assert cmd.image_type == active_fw_image.firmware.header.image_type
                assert cmd.file_version == active_fw_image.firmware.header.file_version
                assert cmd.image_size == active_fw_image.firmware.header.image_size
                dev.application.packet_received(
                    make_packet(
                        "image_block",
                        field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                        manufacturer_code=active_fw_image.firmware.header.manufacturer_id,
                        image_type=active_fw_image.firmware.header.image_type,
                        file_version=active_fw_image.firmware.header.file_version,
                        file_offset=0,
                        maximum_data_size=64,
                        request_node_addr=dev.ieee,
                    )
                )
            elif isinstance(cmd, Ota.ClientCommandDefs.image_block_response.schema):
                if cmd.file_offset == 0:
                    assert cmd.status == foundation.Status.SUCCESS
                    assert (
                        cmd.manufacturer_code
                        == active_fw_image.firmware.header.manufacturer_id
                    )
                    assert cmd.image_type == active_fw_image.firmware.header.image_type
                    assert (
                        cmd.file_version == active_fw_image.firmware.header.file_version
                    )
                    assert cmd.file_offset == 0
                    assert cmd.image_data == active_fw_image.firmware.serialize()[0:64]
                    dev.application.packet_received(
                        make_packet(
                            "image_block",
                            field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                            manufacturer_code=active_fw_image.firmware.header.manufacturer_id,
                            image_type=active_fw_image.firmware.header.image_type,
                            file_version=active_fw_image.firmware.header.file_version,
                            file_offset=64,
                            maximum_data_size=64,
                            request_node_addr=dev.ieee,
                        )
                    )
                elif cmd.file_offset == 64:
                    assert cmd.status == foundation.Status.SUCCESS
                    assert (
                        cmd.manufacturer_code
                        == active_fw_image.firmware.header.manufacturer_id
                    )
                    assert cmd.image_type == active_fw_image.firmware.header.image_type
                    assert (
                        cmd.file_version == active_fw_image.firmware.header.file_version
                    )
                    assert cmd.file_offset == 64
                    assert cmd.image_data == active_fw_image.firmware.serialize()[64:70]
                    dev.application.packet_received(
                        make_packet(
                            "upgrade_end",
                            status=foundation.Status.SUCCESS,
                            manufacturer_code=active_fw_image.firmware.header.manufacturer_id,
                            image_type=active_fw_image.firmware.header.image_type,
                            file_version=active_fw_image.firmware.header.file_version,
                        )
                    )

            elif isinstance(cmd, Ota.ClientCommandDefs.upgrade_end_response.schema):
                assert (
                    cmd.manufacturer_code
                    == active_fw_image.firmware.header.manufacturer_id
                )
                assert cmd.image_type == active_fw_image.firmware.header.image_type
                assert cmd.file_version == active_fw_image.firmware.header.file_version
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
                    direction=foundation.Direction.Client_to_Server,
                    args=(),
                    kwargs={
                        "status_records": [
                            foundation.ReadAttributeRecord(
                                attrid=Ota.AttributeDefs.current_file_version.id,
                                status=foundation.Status.SUCCESS,
                                value=foundation.TypeValue(
                                    type=foundation.DataTypeId.uint32,
                                    value=active_fw_image.firmware.header.file_version,
                                ),
                            )
                        ]
                    },
                )

                dev.application.packet_received(
                    t.ZigbeePacket(
                        src=t.AddrModeAddress(
                            addr_mode=t.AddrMode.NWK, address=dev.nwk
                        ),
                        src_ep=1,
                        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
                        dst_ep=1,
                        tsn=hdr.tsn,
                        profile_id=260,
                        cluster_id=cluster.cluster_id,
                        data=t.SerializableBytes(
                            req_hdr.serialize() + req_cmd.serialize()
                        ),
                        lqi=255,
                        rssi=-30,
                    )
                )

    dev.application.send_packet = AsyncMock(side_effect=send_packet)
    progress_callback = MagicMock()
    result = await dev.update_firmware(fw_image, progress_callback)
    assert (
        dev.endpoints[1]
        .out_clusters[Ota.cluster_id]
        ._attr_cache[Ota.AttributeDefs.current_file_version.id]
        == 0x12345678
    )

    assert dev.application.send_packet.await_count == 6
    assert progress_callback.call_count == 2
    assert progress_callback.call_args_list[0] == call(64, 70, 91.42857142857143)
    assert progress_callback.call_args_list[1] == call(70, 70, 100.0)
    assert result == foundation.Status.SUCCESS

    progress_callback.reset_mock()
    dev.application.send_packet.reset_mock()
    result = await dev.update_firmware(
        fw_image, progress_callback=progress_callback, force=True
    )

    assert dev.application.send_packet.await_count == 6
    assert progress_callback.call_count == 2
    assert progress_callback.call_args_list[0] == call(64, 70, 91.42857142857143)
    assert progress_callback.call_args_list[1] == call(70, 70, 100.0)
    assert result == foundation.Status.SUCCESS

    # _image_query_req exception test
    dev.application.send_packet.reset_mock()
    progress_callback.reset_mock()
    image_notify = cluster.image_notify
    cluster.image_notify = AsyncMock(side_effect=zigpy.exceptions.DeliveryError("Foo"))
    result = await dev.update_firmware(fw_image, progress_callback=progress_callback)
    assert dev.application.send_packet.await_count == 0
    assert progress_callback.call_count == 0
    assert "OTA image_notify handler exception" in caplog.text
    assert result != foundation.Status.SUCCESS
    cluster.image_notify = image_notify
    caplog.clear()

    # _image_query_req exception test
    dev.application.send_packet.reset_mock()
    progress_callback.reset_mock()
    query_next_image_response = cluster.query_next_image_response
    cluster.query_next_image_response = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("Foo")
    )
    result = await dev.update_firmware(fw_image, progress_callback=progress_callback)
    assert dev.application.send_packet.await_count == 1  # just image notify
    assert progress_callback.call_count == 0
    assert "OTA query_next_image handler exception" in caplog.text
    assert result != foundation.Status.SUCCESS
    cluster.query_next_image_response = query_next_image_response
    caplog.clear()

    # _image_block_req exception test
    dev.application.send_packet.reset_mock()
    progress_callback.reset_mock()
    image_block_response = cluster.image_block_response
    cluster.image_block_response = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("Foo")
    )
    result = await dev.update_firmware(fw_image, progress_callback=progress_callback)
    assert (
        dev.application.send_packet.await_count == 2
    )  # just image notify + query next image
    assert progress_callback.call_count == 0
    assert "OTA image_block handler exception" in caplog.text
    assert result != foundation.Status.SUCCESS
    cluster.image_block_response = image_block_response
    caplog.clear()

    # _upgrade_end exception test
    dev.application.send_packet.reset_mock()
    progress_callback.reset_mock()
    upgrade_end_response = cluster.upgrade_end_response
    cluster.upgrade_end_response = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("Foo")
    )
    result = await dev.update_firmware(fw_image, progress_callback=progress_callback)
    assert (
        dev.application.send_packet.await_count == 4
    )  # just image notify, qne, and 2 img blocks
    assert progress_callback.call_count == 2
    assert "OTA upgrade_end handler exception" in caplog.text
    assert result != foundation.Status.SUCCESS
    cluster.upgrade_end_response = upgrade_end_response
    caplog.clear()

    async def send_packet(packet: t.ZigbeePacket):
        if packet.cluster_id == Ota.cluster_id:
            hdr, cmd = cluster.deserialize(packet.data.serialize())
            if isinstance(cmd, Ota.ImageNotifyCommand):
                dev.application.packet_received(
                    make_packet(
                        "query_next_image",
                        field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
                        manufacturer_code=fw_image.firmware.header.manufacturer_id,
                        image_type=fw_image.firmware.header.image_type,
                        current_file_version=fw_image.firmware.header.file_version - 10,
                        hardware_version=1,
                    )
                )
            elif isinstance(
                cmd, Ota.ClientCommandDefs.query_next_image_response.schema
            ):
                assert cmd.status == foundation.Status.SUCCESS
                assert cmd.manufacturer_code == fw_image.firmware.header.manufacturer_id
                assert cmd.image_type == fw_image.firmware.header.image_type
                assert cmd.file_version == fw_image.firmware.header.file_version
                assert cmd.image_size == fw_image.firmware.header.image_size
                dev.application.packet_received(
                    make_packet(
                        "image_block",
                        field_control=Ota.ImageBlockCommand.FieldControl.RequestNodeAddr,
                        manufacturer_code=fw_image.firmware.header.manufacturer_id,
                        image_type=fw_image.firmware.header.image_type,
                        file_version=fw_image.firmware.header.file_version,
                        file_offset=300,
                        maximum_data_size=64,
                        request_node_addr=dev.ieee,
                    )
                )

    dev.application.send_packet = AsyncMock(side_effect=send_packet)

    progress_callback.reset_mock()
    image_block_response = cluster.image_block_response
    cluster.image_block_response = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("Foo")
    )
    result = await dev.update_firmware(fw_image, progress_callback=progress_callback)
    assert (
        dev.application.send_packet.await_count == 2
    )  # just image notify, qne, img block response fails
    assert progress_callback.call_count == 0
    assert "OTA image_block handler[MALFORMED_COMMAND] exception" in caplog.text
    assert result == foundation.Status.MALFORMED_COMMAND
    cluster.image_block_response = image_block_response


async def test_request_exception_propagation(dev):
    """Test that exceptions are propagated to the caller."""
    tsn = 0x12

    ep = dev.add_endpoint(1)
    ep.add_input_cluster(Basic.cluster_id)
    ep.basic.deserialize = MagicMock(side_effect=RuntimeError())

    dev.get_sequence = MagicMock(return_value=tsn)

    asyncio.get_running_loop().call_soon(
        dev.packet_received,
        t.ZigbeePacket(
            profile_id=260,
            cluster_id=Basic.cluster_id,
            src_ep=1,
            dst_ep=1,
            data=t.SerializableBytes(
                foundation.ZCLHeader(
                    frame_control=foundation.FrameControl(
                        frame_type=foundation.FrameType.CLUSTER_COMMAND,
                        is_manufacturer_specific=False,
                        direction=foundation.Direction.Server_to_Client,
                        disable_default_response=True,
                        reserved=0,
                    ),
                    tsn=tsn,
                    command_id=foundation.GeneralCommand.Default_Response,
                    manufacturer=None,
                ).serialize()
                + (
                    foundation.GENERAL_COMMANDS[
                        foundation.GeneralCommand.Default_Response
                    ]
                    .schema(
                        command_id=Basic.ServerCommandDefs.reset_fact_default.id,
                        status=foundation.Status.SUCCESS,
                    )
                    .serialize()
                )
            ),
            src=t.AddrModeAddress(
                addr_mode=t.AddrMode.NWK,
                address=dev.nwk,
            ),
            dst=t.AddrModeAddress(
                addr_mode=t.AddrMode.NWK,
                address=0x0000,
            ),
        ),
    )

    with pytest.raises(zigpy.exceptions.ParsingError) as exc:
        await ep.basic.reset_fact_default()

    assert type(exc.value.__cause__) is RuntimeError


async def test_debouncing(dev):
    """Test that request debouncing filters out duplicate packets."""

    ep = dev.add_endpoint(1)
    cluster = ep.add_input_cluster(0xEF00)

    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=dev.nwk),
        src_ep=1,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        dst_ep=1,
        source_route=None,
        extended_timeout=False,
        tsn=202,
        profile_id=260,
        cluster_id=cluster.cluster_id,
        data=t.SerializableBytes(b"\t6\x02\x00\x89m\x02\x00\x04\x00\x00\x00\x00"),
        tx_options=t.TransmitOptions.NONE,
        radius=0,
        non_member_radius=0,
        lqi=148,
        rssi=-63,
    )

    packet_received = MagicMock()

    with dev.application.callback_for_response(
        src=dev,
        filters=[lambda hdr, cmd: True],
        callback=packet_received,
    ):
        for i in range(10):
            new_packet = packet.replace(
                timestamp=None,
                tsn=packet.tsn + i,
                lqi=packet.lqi + i,
                rssi=packet.rssi + i,
            )
            dev.packet_received(new_packet)

    assert len(packet_received.mock_calls) == 1


async def test_device_concurrency(dev: device.Device) -> None:
    """Test that the device can handle multiple requests concurrently."""
    ep = dev.add_endpoint(1)
    ep.add_input_cluster(Basic.cluster_id)

    async def delayed_receive(*args, **kwargs) -> None:
        await asyncio.sleep(0.1)

    dev._application.request = AsyncMock(side_effect=delayed_receive)

    await asyncio.gather(
        # First low priority request makes it through, since the slot is free
        dev.request(
            profile=0x0401,
            cluster=Basic.cluster_id,
            src_ep=1,
            dst_ep=1,
            sequence=dev.get_sequence(),
            data=b"test low 1!",
            priority=t.PacketPriority.LOW,
            expect_reply=False,
        ),
        # Second one (and all subsequent requests) are enqueued
        dev.request(
            profile=0x0401,
            cluster=Basic.cluster_id,
            src_ep=1,
            dst_ep=1,
            sequence=dev.get_sequence(),
            data=b"test low 2!",
            priority=t.PacketPriority.LOW,
            expect_reply=False,
        ),
        dev.request(
            profile=0x0401,
            cluster=Basic.cluster_id,
            src_ep=1,
            dst_ep=1,
            sequence=dev.get_sequence(),
            data=b"test normal!",
            expect_reply=False,
        ),
        dev.request(
            profile=0x0401,
            cluster=Basic.cluster_id,
            src_ep=1,
            dst_ep=1,
            sequence=dev.get_sequence(),
            data=b"test high!",
            priority=999,
            expect_reply=False,
        ),
        dev.request(
            profile=0x0401,
            cluster=Basic.cluster_id,
            src_ep=1,
            dst_ep=1,
            sequence=dev.get_sequence(),
            data=b"test high!",
            priority=t.PacketPriority.HIGH,
            expect_reply=False,
        ),
    )

    assert len(dev._application.request.mock_calls) == 5
    assert [c.kwargs["priority"] for c in dev._application.request.mock_calls] == [
        t.PacketPriority.LOW,  # First one that made it through
        999,  # Super high
        t.PacketPriority.HIGH,
        None,  # Normal
        t.PacketPriority.LOW,
    ]


async def test_duplicate_request_sending(dev: device.Device) -> None:
    """Test that a device throws an error if requests duplicate."""

    ep = dev.add_endpoint(1)
    ep.add_input_cluster(Basic.cluster_id)

    async def delayed_receive(*args, **kwargs) -> None:
        await asyncio.sleep(0.1)
        raise asyncio.TimeoutError()

    dev._application.request = AsyncMock(side_effect=delayed_receive)
    dev._concurrent_requests_semaphore.max_value = 100000

    # We send 256 + 1 requests
    errors = await asyncio.gather(
        *(dev.endpoints[1].basic.reset_fact_default() for _ in range(256 + 1)),
        return_exceptions=True,
    )

    # The 257th will fail to send because it will collide with the first due to TSN
    # wrapping
    assert all(isinstance(errors[i], asyncio.TimeoutError) for i in range(256))
    assert isinstance(errors[256], zigpy.exceptions.ControllerException)
    assert str(errors[256]).startswith("Duplicate request key: ")


async def test_duplicate_request_matching(dev: device.Device, caplog) -> None:
    """Test that a device handles duplicate packets matching the same request."""
    ep = dev.add_endpoint(1)
    ep.add_input_cluster(Basic.cluster_id)

    def send_responses():
        packet = t.ZigbeePacket(
            src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=dev.nwk),
            src_ep=1,
            dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
            dst_ep=1,
            tsn=1,
            profile_id=260,
            cluster_id=Basic.cluster_id,
            data=t.SerializableBytes(
                foundation.ZCLHeader(
                    frame_control=foundation.FrameControl(
                        frame_type=foundation.FrameType.GLOBAL_COMMAND,
                        is_manufacturer_specific=False,
                        direction=foundation.Direction.Server_to_Client,
                        disable_default_response=True,
                        reserved=0,
                    ),
                    tsn=1,
                    command_id=foundation.GeneralCommand.Default_Response,
                ).serialize()
                + (
                    foundation.GENERAL_COMMANDS[
                        foundation.GeneralCommand.Default_Response
                    ]
                    .schema(
                        command_id=Basic.ServerCommandDefs.reset_fact_default.id,
                        status=foundation.Status.SUCCESS,
                    )
                    .serialize()
                )
            ),
            lqi=255,
            rssi=-30,
        )

        dev.packet_received(packet)
        dev.packet_received(packet)
        dev.packet_received(packet)

    with (
        caplog.at_level(logging.DEBUG),
        patch.object(dev, "_should_filter_packet", return_value=False),
    ):
        asyncio.get_running_loop().call_soon(send_responses)
        await dev.endpoints[1].basic.reset_fact_default()

    assert "probably duplicate response" in caplog.text


@pytest.mark.parametrize("cluster_type", [ClusterType.Server, ClusterType.Client])
async def test_find_cluster(dev: device.Device, cluster_type: ClusterType) -> None:
    """Test finding a cluster by ID and type."""
    ep = dev.add_endpoint(1)
    in_cluster = ep.add_input_cluster(Basic.cluster_id)
    out_cluster = ep.add_output_cluster(Basic.cluster_id)

    found_cluster = dev.find_cluster(Basic.cluster_id, cluster_type)

    if cluster_type is ClusterType.Server:
        assert found_cluster is in_cluster
    else:
        assert found_cluster is out_cluster


async def test_find_cluster_not_found(dev: device.Device) -> None:
    """Test finding a cluster that doesn't exist."""
    dev.add_endpoint(1)

    with pytest.raises(ValueError, match=r"Cluster 0x0000 not found in any endpoint"):
        dev.find_cluster(Basic.cluster_id, ClusterType.Server)


@pytest.mark.parametrize(
    ("initializing", "semaphore_locked", "expected_fast_poll"),
    [
        (True, False, True),  # Fast poll enabled because the device is initializing
        (False, True, True),  # Fast poll enabled because semaphore is locked
        (False, False, False),
    ],
)
async def test_poll_control_checkin_callback(
    dev: device.Device,
    initializing: bool,
    semaphore_locked: bool,
    expected_fast_poll: bool,
) -> None:
    """Test PollControl check-in callback with different device states."""
    ep = dev.add_endpoint(1)
    poll_control = ep.add_input_cluster(PollControl.cluster_id)
    poll_control.checkin_response = AsyncMock()

    # Mock device state
    if initializing:
        # Create a mock task that isn't done yet
        mock_task = MagicMock()
        mock_task.done.return_value = False
        dev._initialize_task = mock_task
    else:
        dev._initialize_task = None

    if semaphore_locked:
        await dev._concurrent_requests_semaphore.acquire()

    zcl_hdr = foundation.ZCLHeader(
        frame_control=foundation.FrameControl(
            frame_type=foundation.FrameType.CLUSTER_COMMAND,
            is_manufacturer_specific=False,
            direction=foundation.Direction.Server_to_Client,
            disable_default_response=1,
            reserved=0,
        ),
        tsn=0x12,
        command_id=PollControl.ClientCommandDefs.checkin.id,
    )
    command = PollControl.ClientCommandDefs.checkin.schema()

    # Test the callback
    await dev.poll_control_checkin_callback(zcl_hdr, command)

    # Verify the correct response was sent
    if expected_fast_poll:
        assert poll_control.checkin_response.mock_calls == [
            call(
                start_fast_polling=expected_fast_poll,
                fast_poll_timeout=int(device.DEFAULT_FAST_POLL_TIMEOUT * 4),
                tsn=0x12,
            )
        ]
    else:
        assert poll_control.checkin_response.mock_calls == [
            call(
                start_fast_polling=expected_fast_poll,
                fast_poll_timeout=0,
                tsn=0x12,
            )
        ]

    # Clean up semaphore if we acquired it
    if semaphore_locked:
        dev._concurrent_requests_semaphore.release()


async def test_begin_fast_polling_with_cluster(dev: device.Device) -> None:
    """Test beginning fast polling when PollControl cluster exists."""
    ep = dev.add_endpoint(1)
    poll_control = ep.add_input_cluster(PollControl.cluster_id)
    poll_control.bind = AsyncMock()
    poll_control.write_attributes = AsyncMock()

    timeout = 45.0
    await dev.begin_fast_polling(timeout)

    # Verify bind was called
    assert poll_control.bind.mock_calls == [call()]

    # Verify write_attributes was called with correct timeout
    assert poll_control.write_attributes.mock_calls == [
        call({PollControl.AttributeDefs.fast_poll_timeout.id: int(timeout * 4)})
    ]

    # Verify end time was set
    assert dev._fast_polling_end_time > datetime.now(timezone.utc)


async def test_begin_fast_polling_no_cluster(dev: device.Device) -> None:
    """Test beginning fast polling when PollControl cluster doesn't exist."""
    dev.add_endpoint(1)  # No PollControl cluster

    # Should return silently without error
    await dev.begin_fast_polling()

    # End time should remain at minimum
    assert dev._fast_polling_end_time == datetime.min.replace(tzinfo=timezone.utc)


async def test_reset_timers(dev: device.Device) -> None:
    """Test resetting device timers."""
    # Set a future end time
    dev._fast_polling_end_time = datetime.now(timezone.utc)

    # Reset timers
    dev.reset_timers()

    # Verify end time was reset to minimum
    assert dev._fast_polling_end_time == datetime.min.replace(tzinfo=timezone.utc)


async def test_on_remove_callbacks(dev: device.Device) -> None:
    """Test that on_remove calls all registered callbacks."""
    callback1 = MagicMock()
    callback2 = MagicMock()

    # Add callbacks manually
    dev._on_remove_callbacks.extend([callback1, callback2])

    # Call on_remove
    dev.on_remove()

    # Verify callbacks were called
    callback1.assert_called_once()
    callback2.assert_called_once()

    # Verify callbacks list was cleared
    assert not dev._on_remove_callbacks


async def test_initialize_fast_polling_failure(dev: device.Device) -> None:
    """Test that fast polling is attempted during initialization."""
    ep = dev.add_endpoint(1)
    ep.add_input_cluster(PollControl.cluster_id)

    dev.begin_fast_polling = AsyncMock(side_effect=[asyncio.TimeoutError(), None])

    async def mockepinit(self, *args, **kwargs):
        self.status = endpoint.Status.ZDO_INIT
        self.add_input_cluster(Basic.cluster_id)

    async def mock_ep_get_model_info(self):
        if self.endpoint_id == 1:
            return "Model2", "Manufacturer2"

    with patch("zigpy.endpoint.Endpoint.initialize", mockepinit):
        with patch("zigpy.endpoint.Endpoint.get_model_info", mock_ep_get_model_info):
            with patch.object(
                dev.zdo,
                "Active_EP_req",
                AsyncMock(return_value=[0, None, [0, 1, 2, 3, 4]]),
            ):
                await dev.initialize()

    # Initialization attempted to fast poll but failure didn't stop it
    assert dev.begin_fast_polling.mock_calls == [call()]
