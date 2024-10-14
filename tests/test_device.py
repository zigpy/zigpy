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
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import Basic, Ota
from zigpy.zdo import types as zdo_t

from .async_mock import ANY, AsyncMock, MagicMock, int_sentinel, patch, sentinel


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


async def test_request(dev):
    seq = int_sentinel.tsn

    async def mock_req(*args, **kwargs):
        dev._pending[seq].result.set_result(sentinel.result)

    dev.application.send_packet = AsyncMock(side_effect=mock_req)
    r = await dev.request(1, 2, 3, 3, seq, b"")
    assert r is sentinel.result
    assert dev._application.send_packet.call_count == 1


async def test_request_without_reply(dev):
    seq = int_sentinel.tsn

    dev._pending.new = MagicMock()
    dev.application.send_packet = AsyncMock()
    r = await dev.request(1, 2, 3, 3, seq, b"", expect_reply=False)
    assert r is None
    assert dev._application.send_packet.call_count == 1
    assert len(dev._pending.new.mock_calls) == 0


async def test_request_tsn_error(dev):
    seq = int_sentinel.tsn

    dev._pending.new = MagicMock(side_effect=zigpy.exceptions.ControllerException())
    dev.application.request = MagicMock()
    dev.application.send_packet = AsyncMock()

    # We don't leave a dangling coroutine on error
    with pytest.raises(zigpy.exceptions.ControllerException):
        await dev.request(1, 2, 3, 3, seq, b"")

    assert dev._application.send_packet.call_count == 0
    assert dev._application.request.call_count == 0
    assert len(dev._pending.new.mock_calls) == 1


async def test_failed_request(dev):
    assert dev.last_seen is None
    dev._application.send_packet = AsyncMock(
        side_effect=zigpy.exceptions.DeliveryError("Uh oh")
    )
    with pytest.raises(zigpy.exceptions.DeliveryError):
        await dev.request(1, 2, 3, 4, 5, b"")
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


async def test_handle_message_read_report_conf(dev):
    ep = dev.add_endpoint(3)
    ep.add_input_cluster(0x702)
    tsn = 0x56
    req_mock = MagicMock()
    dev._pending[tsn] = req_mock

    # Read Report Configuration Success
    rsp = dev.handle_message(
        0x104,  # profile
        0x702,  # cluster
        3,  # source EP
        3,  # dest EP
        b"\x18\x56\x09\x00\x00\x00\x00\x25\x1e\x00\x84\x03\x01\x02\x03\x04\x05\x06",  # message
    )
    # Returns decoded msg when response is not pending, None otherwise
    assert rsp is None
    assert req_mock.result.set_result.call_count == 1
    cfg_sup1 = req_mock.result.set_result.call_args[0][0].attribute_configs[0]
    assert isinstance(cfg_sup1, zigpy.zcl.foundation.AttributeReportingConfigWithStatus)
    assert cfg_sup1.status == zigpy.zcl.foundation.Status.SUCCESS
    assert cfg_sup1.config.direction == 0
    assert cfg_sup1.config.attrid == 0
    assert cfg_sup1.config.datatype == 0x25
    assert cfg_sup1.config.min_interval == 30
    assert cfg_sup1.config.max_interval == 900
    assert cfg_sup1.config.reportable_change == 0x060504030201

    # Unsupported attributes
    tsn2 = 0x5B
    req_mock2 = MagicMock()
    dev._pending[tsn2] = req_mock2
    rsp2 = dev.handle_message(
        0x104,  # profile
        0x702,  # cluster
        3,  # source EP
        3,  # dest EP
        b"\x18\x5b\x09\x86\x00\x00\x00\x86\x00\x12\x00\x86\x00\x00\x04",  # message 3x("Unsupported attribute" response)
    )
    # Returns decoded msg when response is not pending, None otherwise
    assert rsp2 is None
    cfg_unsup1, cfg_unsup2, cfg_unsup3 = req_mock2.result.set_result.call_args[0][
        0
    ].attribute_configs
    assert (
        cfg_unsup1.status
        == cfg_unsup2.status
        == cfg_unsup3.status
        == zigpy.zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE
    )
    assert cfg_unsup1.config.direction == 0x00 and cfg_unsup1.config.attrid == 0x0000
    assert cfg_unsup2.config.direction == 0x00 and cfg_unsup2.config.attrid == 0x0012
    assert cfg_unsup3.config.direction == 0x00 and cfg_unsup3.config.attrid == 0x0400

    # One supported, one unsupported
    tsn3 = 0x5C
    req_mock3 = MagicMock()
    dev._pending[tsn3] = req_mock3
    rsp3 = dev.handle_message(
        0x104,  # profile
        0x702,  # cluster
        3,  # source EP
        3,  # dest EP
        b"\x18\x5c\x09\x86\x00\x00\x00\x00\x00\x00\x00\x25\x1e\x00\x84\x03\x01\x02\x03\x04\x05\x06",
    )
    assert rsp3 is None
    cfg_unsup4, cfg_sup2 = req_mock3.result.set_result.call_args[0][0].attribute_configs
    assert cfg_unsup4.status == zigpy.zcl.foundation.Status.UNSUPPORTED_ATTRIBUTE
    assert cfg_sup2.status == zigpy.zcl.foundation.Status.SUCCESS
    assert cfg_sup2.serialize() == cfg_sup1.serialize()


async def test_handle_message_deserialize_error(dev):
    ep = dev.add_endpoint(3)
    dev.deserialize = MagicMock(side_effect=ValueError)
    ep.handle_message = MagicMock()
    dev.handle_message(99, 98, 3, 3, b"abcd")
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

    dev.update_last_seen()
    dev.listener_event.assert_called_once_with("device_last_seen_updated", ANY)
    event_time = dev.listener_event.mock_calls[0].args[1]
    assert (event_time - datetime.now(timezone.utc)).total_seconds() < 0.1


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
                data=t.SerializableBytes(b"data"),
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


async def test_update_device_firmware_no_ota_cluster(dev):
    """Test that device firmware updates fails: no ota cluster."""
    with pytest.raises(ValueError, match="Device has no OTA cluster"):
        await dev.update_firmware(sentinel.firmware_image, sentinel.progress_callback)

    dev.add_endpoint(1)
    dev.endpoints[1].output_clusters = MagicMock(side_effect=KeyError)
    with pytest.raises(ValueError, match="Device has no OTA cluster"):
        await dev.update_firmware(sentinel.firmware_image, sentinel.progress_callback)


async def test_update_device_firmware_already_in_progress(dev, caplog):
    """Test that device firmware updates no ops when update is in progress."""
    dev.ota_in_progress = True
    await dev.update_firmware(sentinel.firmware_image, sentinel.progress_callback)
    assert "OTA already in progress" in caplog.text


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
                    direction=foundation.Direction.Server_to_Client,
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
    assert result == foundation.Status.FAILURE
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
    assert result == foundation.Status.FAILURE
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
    assert result == foundation.Status.FAILURE
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
    assert result == foundation.Status.FAILURE
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


async def test_deserialize_backwards_compat(dev):
    """Test that deserialization uses the method if it is overloaded."""
    dev._packet_debouncer.filter = MagicMock(return_value=False)

    packet = t.ZigbeePacket(
        profile_id=260,
        cluster_id=Basic.cluster_id,
        src_ep=1,
        dst_ep=1,
        data=t.SerializableBytes(
            b"\x18\x56\x09\x00\x00\x00\x00\x25\x1e\x00\x84\x03\x01\x02\x03\x04\x05\x06"
        ),
        src=t.AddrModeAddress(
            addr_mode=t.AddrMode.NWK,
            address=dev.nwk,
        ),
        dst=t.AddrModeAddress(
            addr_mode=t.AddrMode.NWK,
            address=0x0000,
        ),
    )

    ep = dev.add_endpoint(1)
    ep.add_input_cluster(Basic.cluster_id)

    dev.packet_received(packet)

    # Replace the method
    dev.deserialize = MagicMock(side_effect=dev.deserialize)
    dev.packet_received(packet)

    assert dev.deserialize.call_count == 1


async def test_request_exception_propagation(dev, event_loop):
    """Test that exceptions are propagated to the caller."""
    tsn = 0x12

    ep = dev.add_endpoint(1)
    ep.add_input_cluster(Basic.cluster_id)
    ep.deserialize = MagicMock(side_effect=RuntimeError())

    dev.get_sequence = MagicMock(return_value=tsn)

    event_loop.call_soon(
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
        t.PacketPriority.NORMAL,
        t.PacketPriority.LOW,
    ]
