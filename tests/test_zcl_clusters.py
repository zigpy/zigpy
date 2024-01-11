import asyncio
import re

import pytest

from zigpy import device
import zigpy.endpoint
import zigpy.types as types
import zigpy.zcl as zcl
import zigpy.zcl.clusters.security as sec
from zigpy.zdo import types as zdo_t

from .async_mock import AsyncMock, MagicMock, patch, sentinel

IMAGE_SIZE = 0x2345
IMAGE_OFFSET = 0x2000


def test_registry():
    for cluster_id, cluster in zcl.Cluster._registry.items():
        assert 0 <= getattr(cluster, "cluster_id", -1) <= 65535
        assert cluster_id == cluster.cluster_id
        assert issubclass(cluster, zcl.Cluster)


def test_attributes():
    for _cluster_id, cluster in zcl.Cluster._registry.items():
        for attrid, attr in cluster.attributes.items():
            assert 0 <= attrid <= 0xFFFF
            assert isinstance(attr, zcl.foundation.ZCLAttributeDef)
            assert attr.id == attrid
            assert attr.name
            assert attr.type
            assert callable(attr.type.deserialize)
            assert callable(attr.type.serialize)


def _test_commands(cmdattr):
    for _cluster_id, cluster in zcl.Cluster._registry.items():
        for cmdid, cmdspec in getattr(cluster, cmdattr).items():
            assert 0 <= cmdid <= 0xFF

            assert cmdspec.id == cmdid
            assert isinstance(cmdspec, zcl.foundation.ZCLCommandDef)
            assert issubclass(cmdspec.schema, types.Struct)

            for field in cmdspec.schema.fields:
                assert callable(field.type.deserialize)
                assert callable(field.type.serialize)


def test_server_commands():
    _test_commands("server_commands")


def test_client_commands():
    _test_commands("client_commands")


def test_ep_attributes():
    seen = set()
    for _cluster_id, cluster in zcl.Cluster._registry.items():
        assert isinstance(cluster.ep_attribute, str)
        assert re.match(r"^[a-z_][a-z0-9_]*$", cluster.ep_attribute)
        assert cluster.ep_attribute not in seen
        seen.add(cluster.ep_attribute)

        ep = zigpy.endpoint.Endpoint(None, 1)
        assert not hasattr(ep, cluster.ep_attribute)


async def test_time_cluster():
    ep = MagicMock()
    ep.reply = AsyncMock()
    t = zcl.Cluster._registry[0x000A](ep)

    hdr_general = zcl.foundation.ZCLHeader.general
    tsn = 123

    t.handle_message(hdr_general(tsn, 1), [[0]])
    await asyncio.sleep(0.01)
    assert ep.reply.call_count == 0

    t.handle_message(hdr_general(tsn, 0), [[0]])
    await asyncio.sleep(0.01)
    assert ep.reply.call_count == 1
    assert ep.reply.call_args[0][2][3] == 0

    t.handle_message(hdr_general(tsn, 0), [[1]])
    await asyncio.sleep(0.01)
    assert ep.reply.call_count == 2
    assert ep.reply.call_args[0][2][3] == 1

    t.handle_message(hdr_general(tsn, 0), [[2]])
    await asyncio.sleep(0.01)
    assert ep.reply.call_count == 3
    assert ep.reply.call_args[0][2][3] == 2

    t.handle_message(hdr_general(tsn, 0), [[0, 1, 2]])
    await asyncio.sleep(0.01)
    assert ep.reply.call_count == 4
    assert ep.reply.call_args[0][2][3] == 0

    t.handle_message(hdr_general(tsn, 0), [[7]])
    await asyncio.sleep(0.01)
    assert ep.reply.call_count == 5
    assert ep.reply.call_args[0][2][3] == 7


async def test_time_cluster_unsupported():
    ep = MagicMock()
    ep.reply = AsyncMock()
    t = zcl.Cluster._registry[0x000A](ep)

    hdr_general = zcl.foundation.ZCLHeader.general
    tsn = 123

    t.handle_cluster_general_request(hdr_general(tsn, 0), [[199, 128]])

    await asyncio.sleep(0.01)

    assert ep.reply.call_count == 1
    assert ep.reply.call_args[0][2][-6:] == b"\xc7\x00\x86\x80\x00\x86"


@pytest.fixture
def dev(monkeypatch, app_mock):
    monkeypatch.setattr(device, "APS_REPLY_TIMEOUT_EXTENDED", 0.1)
    ieee = types.EUI64(map(types.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))

    dev = device.Device(app_mock, ieee, 65535)
    node_desc = zdo_t.NodeDescriptor(1, 1, 1, 4, 5, 6, 7, 8)
    with patch.object(
        dev.zdo, "Node_Desc_req", new=AsyncMock(return_value=(0, 0xFFFF, node_desc))
    ):
        yield dev


@pytest.fixture
def ota_cluster(dev):
    ep = dev.add_endpoint(1)
    # ep.device.application.ota = MagicMock(spec_set=ota.OTA)

    cluster = zcl.Cluster._registry[0x0019](ep)

    with patch.object(cluster, "reply", AsyncMock()), patch.object(
        cluster, "request", AsyncMock()
    ):
        yield cluster


async def test_ota_handle_cluster_req(ota_cluster):
    ota_cluster._handle_cluster_request = AsyncMock()

    hdr = zigpy.zcl.foundation.ZCLHeader.cluster(123, 0x00)
    ota_cluster.handle_cluster_request(hdr, sentinel.args)
    assert ota_cluster._handle_cluster_request.call_count == 1


async def test_ota_handle_cluster_req_wrapper(ota_cluster, caplog):
    ota_cluster._handle_query_next_image = AsyncMock()
    ota_cluster._handle_image_block = AsyncMock()
    ota_cluster._handle_upgrade_end = AsyncMock()

    hdr = zigpy.zcl.foundation.ZCLHeader.cluster(123, 0x01)
    await ota_cluster._handle_cluster_request(hdr, [sentinel.args])
    assert ota_cluster._handle_query_next_image.call_count == 1
    assert ota_cluster._handle_query_next_image.call_args[0][0] == sentinel.args
    assert ota_cluster._handle_image_block.call_count == 0
    assert ota_cluster._handle_upgrade_end.call_count == 0
    ota_cluster._handle_query_next_image.reset_mock()
    ota_cluster._handle_image_block.reset_mock()
    ota_cluster._handle_upgrade_end.reset_mock()

    # This command isn't currently handled
    hdr.command_id = 0x08
    await ota_cluster._handle_cluster_request(hdr, [sentinel.just_args])
    assert ota_cluster._handle_query_next_image.call_count == 0
    assert ota_cluster._handle_image_block.call_count == 0
    assert ota_cluster._handle_upgrade_end.call_count == 0

    # This command doesn't exist
    hdr.command_id = 0x28
    await ota_cluster._handle_cluster_request(hdr, [sentinel.just_args])
    assert ota_cluster._handle_query_next_image.call_count == 0
    assert ota_cluster._handle_image_block.call_count == 0
    assert ota_cluster._handle_upgrade_end.call_count == 0
    assert "Unknown OTA command id" in caplog.text


def _ota_next_image(cluster, has_image=True, upgradeable=False):
    async def get_ota_mock(*args):
        if upgradeable:
            img = MagicMock()
            img.should_update = MagicMock(return_value=True)
            img.key.manufacturer_id = sentinel.manufacturer_id
            img.key.image_type = sentinel.image_type
            img.version = sentinel.image_version
            img.header.image_size = sentinel.image_size
        elif has_image:
            img = MagicMock()
            img.should_update.return_value = False
        else:
            img = None
        return img

    cluster.endpoint.device.application.ota.get_ota_image = MagicMock(
        side_effect=get_ota_mock
    )
    return cluster._handle_query_next_image(
        sentinel.field_ctrl,
        sentinel.manufacturer_id,
        sentinel.image_type,
        sentinel.current_file_version,
        sentinel.hw_version,
        tsn=0x21,
    )


async def test_ota_handle_query_next_image_no_img(ota_cluster):
    ota_cluster.query_next_image_response = AsyncMock()
    ota_cluster.endpoint.device.ota_in_progress = False

    await _ota_next_image(ota_cluster, has_image=False, upgradeable=False)
    assert ota_cluster.query_next_image_response.call_count == 1
    assert (
        ota_cluster.query_next_image_response.call_args[0][0]
        == zcl.foundation.Status.NO_IMAGE_AVAILABLE
    )
    assert len(ota_cluster.query_next_image_response.call_args[0]) == 1


async def test_ota_handle_query_next_image_not_upgradeable(ota_cluster):
    ota_cluster.query_next_image_response = AsyncMock()
    ota_cluster.endpoint.device.ota_in_progress = False

    await _ota_next_image(ota_cluster, has_image=True, upgradeable=False)
    assert ota_cluster.query_next_image_response.call_count == 1
    assert (
        ota_cluster.query_next_image_response.call_args[0][0]
        == zcl.foundation.Status.NO_IMAGE_AVAILABLE
    )
    assert len(ota_cluster.query_next_image_response.call_args[0]) == 1


async def test_ota_handle_query_next_image_upgradeable(ota_cluster):
    ota_cluster.query_next_image_response = AsyncMock()
    ota_cluster.endpoint.device.ota_in_progress = False

    class Listener:
        device_ota_update_available = MagicMock()

    listener = Listener()
    ota_cluster.endpoint.device.add_listener(listener)
    await _ota_next_image(ota_cluster, has_image=True, upgradeable=True)
    assert ota_cluster.query_next_image_response.call_count == 1
    assert (
        ota_cluster.query_next_image_response.call_args[0][0]
        == zcl.foundation.Status.NO_IMAGE_AVAILABLE
    )
    assert len(ota_cluster.query_next_image_response.call_args[0]) == 1
    assert listener.device_ota_update_available.call_count == 1


def test_ias_zone_type():
    extra = b"\xaa\x55"
    zone, rest = sec.IasZone.ZoneType.deserialize(b"\x0d\x00" + extra)
    assert rest == extra
    assert zone is sec.IasZone.ZoneType.Motion_Sensor

    zone, rest = sec.IasZone.ZoneType.deserialize(b"\x81\x81" + extra)
    assert rest == extra
    assert zone.name.startswith("manufacturer_specific")
    assert zone.value == 0x8181


def test_ias_ace_audible_notification():
    extra = b"\xaa\x55"
    notification_type, rest = sec.IasAce.AudibleNotification.deserialize(
        b"\x00" + extra
    )
    assert rest == extra
    assert notification_type is sec.IasAce.AudibleNotification.Mute

    notification_type, rest = sec.IasAce.AudibleNotification.deserialize(
        b"\x81" + extra
    )
    assert rest == extra
    assert notification_type.name.startswith("manufacturer_specific")
    assert notification_type.value == 0x81


def test_basic_cluster_power_source():
    extra = b"The rest of the owl\xaa\x55"
    pwr_src, rest = zcl.clusters.general.Basic.PowerSource.deserialize(b"\x81" + extra)

    assert rest == extra
    assert pwr_src == zcl.clusters.general.Basic.PowerSource.Mains_single_phase
    assert pwr_src == 0x01
    assert pwr_src.value == 0x01
    assert pwr_src.battery_backup


@pytest.mark.parametrize(
    "raw, mode, name",
    (
        (0x00, 0, "Stop"),
        (0x01, 0, "Stop"),
        (0x02, 0, "Stop"),
        (0x03, 0, "Stop"),
        (0x30, 3, "Emergency"),
        (0x31, 3, "Emergency"),
        (0x32, 3, "Emergency"),
        (0x33, 3, "Emergency"),
    ),
)
def test_security_iaswd_warning_mode(raw, mode, name):
    """Test warning command class of IasWD cluster."""

    def _test(warning, data):
        assert warning.serialize() == data
        assert warning == raw
        assert warning.mode == mode
        assert warning.mode.name == name
        warning.mode = mode
        assert warning.serialize() == data
        assert warning.mode == mode

    data = types.uint8_t(raw).serialize()
    _test(sec.IasWd.Warning(raw), data)

    extra = b"The rest of the owl\xaa\x55"
    warn, rest = sec.IasWd.Warning.deserialize(data + extra)
    assert rest == extra
    _test(warn, data)
    repr(warn)


def test_security_iaswd_warning_mode_2():
    """Test warning command class of IasWD cluster."""

    def _test(data, raw, mode, name):
        warning, _ = sec.IasWd.Warning.deserialize(data)
        assert warning.serialize() == data
        assert warning == raw
        assert warning.mode == mode
        assert warning.mode.name == name
        warning.mode = mode
        assert warning.serialize() == data
        assert warning.mode == mode

    for mode in sec.IasWd.Warning.WarningMode:
        for other in range(16):
            raw = mode << 4 | other
            data = types.uint8_t(raw).serialize()
            _test(data, raw, mode.value, mode.name)


def test_security_iaswd_warning_strobe():
    """Test strobe of warning command class of IasWD cluster."""

    for strobe in sec.IasWd.Warning.Strobe:
        for mode in range(16):
            for siren in range(4):
                raw = mode << 4 | siren
                raw |= strobe.value << 2
                data = types.uint8_t(raw).serialize()
                warning, _ = sec.IasWd.Warning.deserialize(data)
                assert warning.serialize() == data
                assert warning == raw
                assert warning.strobe == strobe.value
                assert warning.strobe.name == strobe.name
                warning.strobe = strobe
                assert warning.serialize() == data
                assert warning.strobe == strobe.value


def test_security_iaswd_warning_siren():
    """Test siren of warning command class of IasWD cluster."""

    for siren in sec.IasWd.Warning.SirenLevel:
        for mode in range(16):
            for strobe in range(4):
                raw = mode << 4 | (strobe << 2)
                raw |= siren.value
                data = types.uint8_t(raw).serialize()
                warning, _ = sec.IasWd.Warning.deserialize(data)
                assert warning.serialize() == data
                assert warning == raw
                assert warning.level == siren.value
                assert warning.level.name == siren.name
                warning.level = siren
                assert warning.serialize() == data
                assert warning.level == siren.value


@pytest.mark.parametrize(
    "raw, mode, name",
    (
        (0x00, 0, "Armed"),
        (0x01, 0, "Armed"),
        (0x02, 0, "Armed"),
        (0x03, 0, "Armed"),
        (0x10, 1, "Disarmed"),
        (0x11, 1, "Disarmed"),
        (0x12, 1, "Disarmed"),
        (0x13, 1, "Disarmed"),
    ),
)
def test_security_iaswd_squawk_mode(raw, mode, name):
    """Test squawk command class of IasWD cluster."""

    def _test(squawk, data):
        assert squawk.serialize() == data
        assert squawk == raw
        assert squawk.mode == mode
        assert squawk.mode.name == name
        squawk.mode = mode
        assert squawk.serialize() == data
        assert squawk.mode == mode

    data = types.uint8_t(raw).serialize()
    _test(sec.IasWd.Squawk(raw), data)

    extra = b"The rest of the owl\xaa\x55"
    squawk, rest = sec.IasWd.Squawk.deserialize(data + extra)
    assert rest == extra
    _test(squawk, data)
    repr(squawk)


def test_security_iaswd_squawk_strobe():
    """Test strobe of squawk command class of IasWD cluster."""

    for strobe in sec.IasWd.Squawk.Strobe:
        for mode in range(16):
            for level in range(4):
                raw = mode << 4 | level
                raw |= strobe.value << 3
                data = types.uint8_t(raw).serialize()
                squawk, _ = sec.IasWd.Squawk.deserialize(data)
                assert squawk.serialize() == data
                assert squawk == raw
                assert squawk.strobe == strobe.value
                assert squawk.strobe == strobe
                assert squawk.strobe.name == strobe.name
                squawk.strobe = strobe
                assert squawk.serialize() == data
                assert squawk.strobe == strobe


def test_security_iaswd_squawk_level():
    """Test level of squawk command class of IasWD cluster."""

    for level in sec.IasWd.Squawk.SquawkLevel:
        for other in range(64):
            raw = other << 2 | level.value
            data = types.uint8_t(raw).serialize()
            squawk, _ = sec.IasWd.Squawk.deserialize(data)
            assert squawk.serialize() == data
            assert squawk == raw
            assert squawk.level == level.value
            assert squawk.level == level
            assert squawk.level.name == level.name
            squawk.level = level
            assert squawk.serialize() == data
            assert squawk.level == level


def test_hvac_thermostat_system_type():
    """Test system_type class."""

    hvac = zcl.clusters.hvac
    sys_type = hvac.Thermostat.SystemType(0x00)
    assert sys_type.cooling_system_stage == hvac.CoolingSystemStage.Cool_Stage_1
    assert sys_type.heating_system_stage == hvac.HeatingSystemStage.Heat_Stage_1
    assert sys_type.heating_fuel_source == hvac.HeatingFuelSource.Electric
    assert sys_type.heating_system_type == hvac.HeatingSystemType.Conventional

    sys_type = hvac.Thermostat.SystemType(0x35)
    assert sys_type.cooling_system_stage == hvac.CoolingSystemStage.Cool_Stage_2
    assert sys_type.heating_system_stage == hvac.HeatingSystemStage.Heat_Stage_2
    assert sys_type.heating_fuel_source == hvac.HeatingFuelSource.Gas
    assert sys_type.heating_system_type == hvac.HeatingSystemType.Heat_Pump


@patch("zigpy.zcl.Cluster.send_default_rsp")
async def test_ias_zone(send_rsp_mock):
    """Test sending default response on zone status notification."""

    ep = MagicMock()
    ep.reply = AsyncMock()
    t = zcl.Cluster._registry[sec.IasZone.cluster_id](ep, is_server=False)

    # suppress default response
    hdr, args = t.deserialize(b"\tK\x00&\x00\x00\x00\x00\x00")
    hdr.frame_control.disable_default_response = True
    t.handle_message(hdr, args)
    assert send_rsp_mock.call_count == 0

    # this should generate a default response
    hdr.frame_control.disable_default_response = False
    t.handle_message(hdr, args)
    assert send_rsp_mock.call_count == 0

    t = zcl.Cluster._registry[sec.IasZone.cluster_id](ep, is_server=True)

    # suppress default response
    hdr, args = t.deserialize(b"\tK\x00&\x00\x00\x00\x00\x00")
    hdr.frame_control.disable_default_response = True
    t.handle_message(hdr, args)
    assert send_rsp_mock.call_count == 0

    # this should generate a default response
    hdr.frame_control.disable_default_response = False
    t.handle_message(hdr, args)
    assert send_rsp_mock.call_count == 1


def test_ota_image_block_field_control():
    """Test OTA image_block with field control deserializes properly."""
    data = bytes.fromhex("01d403020b101d01001f000100000000400000")

    ep = MagicMock()
    cluster = zcl.clusters.general.Ota(ep)

    hdr, response = cluster.deserialize(data)
    assert hdr.serialize() + response.serialize() == data

    image_block = cluster.commands_by_name["image_block"].schema

    assert response == image_block(
        field_control=image_block.FieldControl.MinimumBlockPeriod,
        manufacturer_code=4107,
        image_type=285,
        file_version=0x01001F00,
        file_offset=0,
        maximum_data_size=64,
        minimum_block_period=0,
    )

    assert response.request_node_addr is None
