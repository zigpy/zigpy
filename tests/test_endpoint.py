import asyncio

import pytest

from zigpy import endpoint, group
import zigpy.device
import zigpy.exceptions
import zigpy.types as t
import zigpy.zcl as zcl
from zigpy.zcl.foundation import Status as ZCLStatus
from zigpy.zdo import types

from .async_mock import AsyncMock, MagicMock, sentinel


@pytest.fixture
def ep():
    dev = MagicMock()
    dev.request = AsyncMock()
    return endpoint.Endpoint(dev, 1)


async def _test_initialize(ep, profile):
    async def mockrequest(nwk, epid, tries=None, delay=None):
        sd = types.SimpleDescriptor()
        sd.endpoint = 1
        sd.profile = profile
        sd.device_type = 0xFF
        sd.input_clusters = [5]
        sd.output_clusters = [6]
        return [0, None, sd]

    ep._device.zdo.Simple_Desc_req = mockrequest
    await ep.initialize()

    assert ep.status > endpoint.Status.NEW
    assert 5 in ep.in_clusters
    assert 6 in ep.out_clusters


async def test_inactive_initialize(ep):
    async def mockrequest(nwk, epid, tries=None, delay=None):
        sd = types.SimpleDescriptor()
        sd.endpoint = 2
        return [131, None, sd]

    ep._device.zdo.Simple_Desc_req = mockrequest
    await ep.initialize()
    assert ep.status == endpoint.Status.ENDPOINT_INACTIVE


async def test_initialize_zha(ep):
    return await _test_initialize(ep, 260)


async def test_initialize_zll(ep):
    return await _test_initialize(ep, 49246)


async def test_initialize_fail(ep):
    async def mockrequest(nwk, epid, tries=None, delay=None):
        return [1, None, None]

    ep._device.zdo.Simple_Desc_req = mockrequest
    await ep.initialize()

    assert ep.status == endpoint.Status.NEW


async def test_reinitialize(ep):
    await _test_initialize(ep, 260)
    assert ep.profile_id == 260
    ep.profile_id = 10
    await _test_initialize(ep, 260)
    assert ep.profile_id == 10


def test_add_input_cluster(ep):
    ep.add_input_cluster(0)
    assert 0 in ep.in_clusters
    assert ep.in_clusters[0].is_server is True
    assert ep.in_clusters[0].is_client is False


def test_add_custom_input_cluster(ep):
    mock_cluster = MagicMock()
    ep.add_input_cluster(0, mock_cluster)
    assert 0 in ep.in_clusters
    assert ep.in_clusters[0] is mock_cluster


def test_add_output_cluster(ep):
    ep.add_output_cluster(0)
    assert 0 in ep.out_clusters
    assert ep.out_clusters[0].is_server is False
    assert ep.out_clusters[0].is_client is True


def test_add_custom_output_cluster(ep):
    mock_cluster = MagicMock()
    ep.add_output_cluster(0, mock_cluster)
    assert 0 in ep.out_clusters
    assert ep.out_clusters[0] is mock_cluster


def test_multiple_add_input_cluster(ep):
    ep.add_input_cluster(0)
    assert ep.in_clusters[0].cluster_id == 0
    ep.in_clusters[0].cluster_id = 1
    assert ep.in_clusters[0].cluster_id == 1
    ep.add_input_cluster(0)
    assert ep.in_clusters[0].cluster_id == 1


def test_multiple_add_output_cluster(ep):
    ep.add_output_cluster(0)
    assert ep.out_clusters[0].cluster_id == 0
    ep.out_clusters[0].cluster_id = 1
    assert ep.out_clusters[0].cluster_id == 1
    ep.add_output_cluster(0)
    assert ep.out_clusters[0].cluster_id == 1


def test_handle_message(ep):
    c = ep.add_input_cluster(0)
    c.handle_message = MagicMock()
    ep.handle_message(sentinel.profile, 0, sentinel.hdr, sentinel.data)
    c.handle_message.assert_called_once_with(sentinel.hdr, sentinel.data)


def test_handle_message_output(ep):
    c = ep.add_output_cluster(0)
    c.handle_message = MagicMock()
    ep.handle_message(sentinel.profile, 0, sentinel.hdr, sentinel.data)
    c.handle_message.assert_called_once_with(sentinel.hdr, sentinel.data)


def test_handle_request_unknown(ep):
    hdr = MagicMock()
    hdr.command_id = sentinel.command_id
    ep.handle_message(sentinel.profile, 99, hdr, sentinel.args)


def test_cluster_attr(ep):
    with pytest.raises(AttributeError):
        ep.basic
    ep.add_input_cluster(0)
    ep.basic


async def test_request(ep):
    ep.profile_id = 260
    await ep.request(7, 8, b"")
    assert ep._device.request.call_count == 1
    assert ep._device.request.await_count == 1


async def test_request_change_profileid(ep):
    ep.profile_id = 49246
    await ep.request(7, 9, b"")
    ep.profile_id = 49246
    await ep.request(0x1000, 10, b"")
    ep.profile_id = 260
    await ep.request(0x1000, 11, b"")
    assert ep._device.request.call_count == 3
    assert ep._device.request.await_count == 3


def test_reply(ep):
    ep.profile_id = 260
    ep.reply(7, 8, b"")
    assert ep._device.reply.call_count == 1


def test_reply_change_profile_id(ep):
    ep.profile_id = 49246
    ep.reply(0x1000, 8, b"", 0x3F)
    assert ep._device.reply.call_count == 1
    assert ep._device.reply.call_args[0][0] == ep.profile_id

    ep.reply(0x1000, 8, b"", 0x40)
    assert ep._device.reply.call_count == 2
    assert ep._device.reply.call_args[0][0] == 0x0104

    ep.profile_id = 0xBEEF
    ep.reply(0x1000, 8, b"", 0x40)
    assert ep._device.reply.call_count == 3
    assert ep._device.reply.call_args[0][0] == ep.profile_id


def _mk_rar(attrid, value, status=0):
    r = zcl.foundation.ReadAttributeRecord()
    r.attrid = attrid
    r.status = status
    r.value = zcl.foundation.TypeValue()
    r.value.value = value
    return r


def _get_model_info(ep, test_manuf=None, test_model=None, fail=False, timeout=False):
    clus = ep.add_input_cluster(0)
    assert 0 in ep.in_clusters
    assert ep.in_clusters[0] is clus

    async def mockrequest(
        foundation, command, schema, args, manufacturer=None, **kwargs
    ):
        assert foundation is True
        assert command == 0
        if fail:
            if timeout:
                raise asyncio.TimeoutError
            else:
                raise zigpy.exceptions.ZigbeeException
        nonlocal test_manuf, test_model

        result = []
        if 4 in args:
            if test_manuf is not None:
                test_manuf = t.uint8_t(len(test_manuf)).serialize() + test_manuf
                rar4 = _mk_rar(4, t.CharacterString.deserialize(test_manuf)[0])
                result.append(rar4)
            else:
                rar4 = _mk_rar(4, None, status=1)
                result.append(rar4)

        if 5 in args:
            if test_model is not None:
                test_model = t.uint8_t(len(test_model)).serialize() + test_model
                rar5 = _mk_rar(5, t.CharacterString.deserialize(test_model)[0])
                result.append(rar5)
            else:
                rar5 = _mk_rar(5, None, status=1)
                result.append(rar5)

        return [result]

    clus.request = mockrequest

    return ep.get_model_info()


async def test_get_model_info(ep):
    manufacturer = b"Mock Manufacturer"
    model = b"Mock Model"

    mod, man = await _get_model_info(ep, manufacturer, model)

    assert man == "Mock Manufacturer"
    assert mod == "Mock Model"


async def test_init_endpoint_info_none(ep):
    mod, man = await _get_model_info(ep)

    assert man is None
    assert mod is None


async def test_init_endpoint_info_null_padded_manuf(ep):
    manufacturer = b"Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07"
    model = b"Mock Model"
    mod, man = await _get_model_info(ep, manufacturer, model)

    assert man == "Mock Manufacturer"
    assert mod == "Mock Model"


async def test_init_endpoint_info_null_padded_model(ep):
    manufacturer = b"Mock Manufacturer"
    model = b"Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    mod, man = await _get_model_info(ep, manufacturer, model)

    assert man == "Mock Manufacturer"
    assert mod == "Mock Model"


async def test_init_endpoint_info_null_padded_manuf_model(ep):
    manufacturer = b"Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07"
    model = b"Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    mod, man = await _get_model_info(ep, manufacturer, model)

    assert man == "Mock Manufacturer"
    assert mod == "Mock Model"


async def test_get_model_info_delivery_error(ep):
    manufacturer = b"Mock Manufacturer"
    model = b"Mock Model"
    mod, man = await _get_model_info(ep, manufacturer, model, fail=True)

    assert man is None
    assert mod is None


async def test_get_model_info_timeout(ep):
    manufacturer = b"Mock Manufacturer"
    model = b"Mock Model"
    mod, man = await _get_model_info(ep, manufacturer, model, fail=True, timeout=True)

    assert man is None
    assert mod is None


def _group_add_mock(ep, status=ZCLStatus.SUCCESS, no_groups_cluster=False):
    async def mock_req(*args, **kwargs):
        return [status, sentinel.group_id]

    if not no_groups_cluster:
        ep.add_input_cluster(4)
    ep.request = MagicMock(side_effect=mock_req)

    ep.device.application.groups = MagicMock(spec_set=group.Groups)
    return ep


@pytest.mark.parametrize("status", (ZCLStatus.SUCCESS, ZCLStatus.DUPLICATE_EXISTS))
async def test_add_to_group(ep, status):
    ep = _group_add_mock(ep, status=status)

    grp_id, grp_name = 0x1234, "Group name 0x1234**"
    res = await ep.add_to_group(grp_id, grp_name)
    assert res == status
    assert ep.request.call_count == 1
    groups = ep.device.application.groups
    assert groups.add_group.call_count == 1
    assert groups.remove_group.call_count == 0
    assert groups.add_group.call_args[0][0] == grp_id
    assert groups.add_group.call_args[0][1] == grp_name


async def test_add_to_group_no_groups(ep):
    ep = _group_add_mock(ep, no_groups_cluster=True)

    grp_id, grp_name = 0x1234, "Group name 0x1234**"
    res = await ep.add_to_group(grp_id, grp_name)
    assert res != ZCLStatus.SUCCESS
    assert ep.request.call_count == 0
    groups = ep.device.application.groups
    assert groups.add_group.call_count == 0
    assert groups.remove_group.call_count == 0


@pytest.mark.parametrize(
    "status",
    (s for s in ZCLStatus if s not in (ZCLStatus.SUCCESS, ZCLStatus.DUPLICATE_EXISTS)),
)
async def test_add_to_group_fail(ep, status):
    ep = _group_add_mock(ep, status=status)

    grp_id, grp_name = 0x1234, "Group name 0x1234**"
    res = await ep.add_to_group(grp_id, grp_name)
    assert res != ZCLStatus.SUCCESS
    assert ep.request.call_count == 1
    groups = ep.device.application.groups
    assert groups.add_group.call_count == 0
    assert groups.remove_group.call_count == 0


def _group_remove_mock(ep, success=True, no_groups_cluster=False, not_member=False):
    async def mock_req(*args, **kwargs):
        if success:
            return [ZCLStatus.SUCCESS, sentinel.group_id]
        return [ZCLStatus.DUPLICATE_EXISTS, sentinel.group_id]

    if not no_groups_cluster:
        ep.add_input_cluster(4)
    ep.request = MagicMock(side_effect=mock_req)

    ep.device.application.groups = MagicMock(spec_set=group.Groups)
    grp = MagicMock(spec_set=group.Group)
    ep.device.application.groups.__contains__.return_value = not not_member
    ep.device.application.groups.__getitem__.return_value = grp
    return ep, grp


async def test_remove_from_group(ep):
    grp_id = 0x1234
    ep, grp_mock = _group_remove_mock(ep)
    res = await ep.remove_from_group(grp_id)
    assert res == ZCLStatus.SUCCESS
    assert ep.request.call_count == 1
    groups = ep.device.application.groups
    assert groups.add_group.call_count == 0
    assert groups.remove_group.call_count == 0
    assert groups.__getitem__.call_args[0][0] == grp_id
    assert grp_mock.add_member.call_count == 0
    assert grp_mock.remove_member.call_count == 1
    assert grp_mock.remove_member.call_args[0][0] == ep


async def test_remove_from_group_no_groups_cluster(ep):
    grp_id = 0x1234
    ep, grp_mock = _group_remove_mock(ep, no_groups_cluster=True)
    res = await ep.remove_from_group(grp_id)
    assert res != ZCLStatus.SUCCESS
    assert ep.request.call_count == 0
    groups = ep.device.application.groups
    assert groups.add_group.call_count == 0
    assert groups.remove_group.call_count == 0
    assert grp_mock.add_member.call_count == 0
    assert grp_mock.remove_member.call_count == 0


async def test_remove_from_group_fail(ep):
    grp_id = 0x1234
    ep, grp_mock = _group_remove_mock(ep, success=False)
    res = await ep.remove_from_group(grp_id)
    assert res != ZCLStatus.SUCCESS
    assert ep.request.call_count == 1
    groups = ep.device.application.groups
    assert groups.add_group.call_count == 0
    assert groups.remove_group.call_count == 0
    assert grp_mock.add_member.call_count == 0
    assert grp_mock.remove_member.call_count == 0


def test_ep_manufacturer(ep):
    ep.device.manufacturer = sentinel.device_manufacturer
    assert ep.manufacturer is sentinel.device_manufacturer

    ep.manufacturer = sentinel.ep_manufacturer
    assert ep.manufacturer is sentinel.ep_manufacturer


def test_ep_model(ep):
    ep.device.model = sentinel.device_model
    assert ep.model is sentinel.device_model

    ep.model = sentinel.ep_model
    assert ep.model is sentinel.ep_model


async def test_group_membership_scan(ep):
    """Test group membership scan."""

    ep.device.application.groups.update_group_membership = MagicMock()
    await ep.group_membership_scan()
    assert ep.device.application.groups.update_group_membership.call_count == 0
    assert ep.device.request.call_count == 0

    ep.add_input_cluster(4)
    ep.device.request.return_value = [0, [1, 3, 7]]
    await ep.group_membership_scan()
    assert ep.device.application.groups.update_group_membership.call_count == 1
    assert ep.device.application.groups.update_group_membership.call_args[0][1] == {
        1,
        3,
        7,
    }
    assert ep.device.request.call_count == 1


async def test_group_membership_scan_fail(ep):
    """Test group membership scan failure."""

    ep.device.application.groups.update_group_membership = MagicMock()
    ep.add_input_cluster(4)
    ep.device.request.side_effect = asyncio.TimeoutError
    await ep.group_membership_scan()
    assert ep.device.application.groups.update_group_membership.call_count == 0
    assert ep.device.request.call_count == 1


def test_endpoint_manufacturer_id(ep):
    """Test manufacturer id."""
    ep.device.manufacturer_id = sentinel.manufacturer_id
    assert ep.manufacturer_id is sentinel.manufacturer_id
