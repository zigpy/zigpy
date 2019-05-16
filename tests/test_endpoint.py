from unittest import mock

import pytest
import zigpy.zcl as zcl
from zigpy.zcl.foundation import Status as ZCLStatus

from zigpy import endpoint, group
from zigpy.zdo import types


@pytest.fixture
def ep():
    dev = mock.MagicMock()
    return endpoint.Endpoint(dev, 1)


async def _test_initialize(ep, profile):
    async def mockrequest(nwk, epid, tries=None, delay=None):
        sd = types.SimpleDescriptor()
        sd.endpoint = 1
        sd.profile = profile
        sd.device_type = 0xff
        sd.input_clusters = [5]
        sd.output_clusters = [6]
        return [0, None, sd]

    ep._device.zdo.Simple_Desc_req = mockrequest
    await ep.initialize()

    assert ep.status > endpoint.Status.NEW
    assert 5 in ep.in_clusters
    assert 6 in ep.out_clusters


@pytest.mark.asyncio
async def test_initialize_zha(ep):
    return await _test_initialize(ep, 260)


@pytest.mark.asyncio
async def test_initialize_zll(ep):
    return await _test_initialize(ep, 49246)


@pytest.mark.asyncio
async def test_initialize_fail(ep):
    async def mockrequest(nwk, epid, tries=None, delay=None):
        return [1, None, None]

    ep._device.zdo.Simple_Desc_req = mockrequest
    await ep.initialize()

    assert ep.status == endpoint.Status.NEW


@pytest.mark.asyncio
async def test_reinitialize(ep):
    await _test_initialize(ep, 260)
    assert ep.profile_id == 260
    ep.profile_id = 10
    await _test_initialize(ep, 260)
    assert ep.profile_id == 10


def test_add_input_cluster(ep):
    ep.add_input_cluster(0)
    assert 0 in ep.in_clusters


def test_add_custom_input_cluster(ep):
    mock_cluster = mock.MagicMock()
    ep.add_input_cluster(0, mock_cluster)
    assert 0 in ep.in_clusters
    assert ep.in_clusters[0] is mock_cluster


def test_add_output_cluster(ep):
    ep.add_output_cluster(0)
    assert 0 in ep.out_clusters


def test_add_custom_output_cluster(ep):
    mock_cluster = mock.MagicMock()
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
    c.handle_message = mock.MagicMock()
    ep.handle_message(False, 0, 0, 0, 1, [])
    c.handle_message.assert_called_once_with(False, 0, 1, [])


def test_handle_message_output(ep):
    c = ep.add_output_cluster(0)
    c.handle_message = mock.MagicMock()
    ep.handle_message(False, 0, 0, 0, 1, [])
    c.handle_message.assert_called_once_with(False, 0, 1, [])


def test_handle_request_unknown(ep):
    ep.handle_message(False, 0, 99, 0, 0, [])


def test_cluster_attr(ep):
    with pytest.raises(AttributeError):
        ep.basic
    ep.add_input_cluster(0)
    ep.basic


def test_request(ep):
    ep.profile_id = 260
    ep.request(7, 8, b'')
    assert ep._device.request.call_count == 1


def test_request_change_profileid(ep):
    ep.profile_id = 49246
    ep.request(7, 9, b'')
    ep.profile_id = 49246
    ep.request(0x1000, 10, b'')
    ep.profile_id = 260
    ep.request(0x1000, 11, b'')
    assert ep._device.request.call_count == 3


def test_reply(ep):
    ep.profile_id = 260
    ep.reply(7, 8, b'')
    assert ep._device.reply.call_count == 1


def _mk_rar(attrid, value, status=0):
    r = zcl.foundation.ReadAttributeRecord()
    r.attrid = attrid
    r.status = status
    r.value = zcl.foundation.TypeValue()
    r.value.value = value
    return r


@pytest.mark.asyncio
async def test_init_endpoint_info(ep):
    clus = ep.add_input_cluster(0)
    assert 0 in ep.in_clusters
    assert ep.in_clusters[0] is clus

    async def mockrequest(foundation, command, schema, args, manufacturer=None):
        assert foundation is True
        assert command == 0
        rar4 = _mk_rar(4, b'Custom')
        rar5 = _mk_rar(5, b'Model')
        return [[rar4, rar5]]
    clus.request = mockrequest

    await test_initialize_zha(ep)
    assert ep.manufacturer == 'Custom'
    assert ep.model == 'Model'


@pytest.mark.asyncio
async def test_init_endpoint_info_none(ep):
    clus = ep.add_input_cluster(0)
    assert 0 in ep.in_clusters
    assert ep.in_clusters[0] is clus

    async def mockrequest(foundation, command, schema, args, manufacturer=None):
        assert foundation is True
        assert command == 0
        rar4 = _mk_rar(4, None)
        rar5 = _mk_rar(5, None)
        return [[rar4, rar5]]
    clus.request = mockrequest

    await test_initialize_zha(ep)


@pytest.mark.asyncio
async def test_init_endpoint_info_unicode(ep):
    clus = ep.add_input_cluster(0)
    assert 0 in ep.in_clusters
    assert ep.in_clusters[0] is clus

    async def mockrequest(foundation, command, schema, args, manufacturer=None):
        assert foundation is True
        assert command == 0
        rar4 = _mk_rar(4, b'\x81')
        rar5 = _mk_rar(5, b'\x81')
        return [[rar4, rar5]]
    clus.request = mockrequest

    await test_initialize_zha(ep)


def _init_endpoint_info(ep, test_manuf=None, test_model=None):
    clus = ep.add_input_cluster(0)
    assert 0 in ep.in_clusters
    assert ep.in_clusters[0] is clus

    async def mockrequest(foundation, command, schema, args, manufacturer=None):
        assert foundation is True
        assert command == 0
        rar4 = _mk_rar(4, test_manuf)
        rar5 = _mk_rar(5, test_model)
        return [[rar4, rar5]]
    clus.request = mockrequest

    return test_initialize_zha(ep)


@pytest.mark.asyncio
async def test_init_endpoint_info_null_padded_manuf(ep):
    manufacturer = b'Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07'
    model = b'Mock Model'
    await _init_endpoint_info(ep, manufacturer, model)

    assert ep.manufacturer == 'Mock Manufacturer'
    assert ep.model == 'Mock Model'


@pytest.mark.asyncio
async def test_init_endpoint_info_null_padded_model(ep):
    manufacturer = b'Mock Manufacturer'
    model = b'Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    await _init_endpoint_info(ep, manufacturer, model)

    assert ep.manufacturer == 'Mock Manufacturer'
    assert ep.model == 'Mock Model'


@pytest.mark.asyncio
async def test_init_endpoint_info_null_padded_manuf_model(ep):
    manufacturer = b'Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07'
    model = b'Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    await _init_endpoint_info(ep, manufacturer, model)

    assert ep.manufacturer == 'Mock Manufacturer'
    assert ep.model == 'Mock Model'


def _group_add_mock(ep, success=True,
                    no_groups_cluster=False):
    async def mock_req(*args, **kwargs):
        if success:
            return [ZCLStatus.SUCCESS, mock.sentinel.group_id]
        return [ZCLStatus.DUPLICATE_EXISTS, mock.sentinel.group_id]

    if not no_groups_cluster:
        ep.add_input_cluster(4)
    ep.request = mock.MagicMock(side_effect=mock_req)

    ep.device.application.groups = mock.MagicMock(spec_set=group.Groups)
    return ep


@pytest.mark.asyncio
async def test_add_to_group(ep):
    ep = _group_add_mock(ep)

    grp_id, grp_name = 0x1234, "Group name 0x1234**"
    res = await ep.add_to_group(grp_id, grp_name)
    assert res == ZCLStatus.SUCCESS
    assert ep.request.call_count == 1
    groups = ep.device.application.groups
    assert groups.add_group.call_count == 1
    assert groups.remove_group.call_count == 0
    assert groups.add_group.call_args[0][0] == grp_id
    assert groups.add_group.call_args[0][1] == grp_name


@pytest.mark.asyncio
async def test_add_to_group_no_groups(ep):
    ep = _group_add_mock(ep, no_groups_cluster=True)

    grp_id, grp_name = 0x1234, "Group name 0x1234**"
    res = await ep.add_to_group(grp_id, grp_name)
    assert res != ZCLStatus.SUCCESS
    assert ep.request.call_count == 0
    groups = ep.device.application.groups
    assert groups.add_group.call_count == 0
    assert groups.remove_group.call_count == 0


@pytest.mark.asyncio
async def test_add_to_group_fail(ep):
    ep = _group_add_mock(ep, success=False)

    grp_id, grp_name = 0x1234, "Group name 0x1234**"
    res = await ep.add_to_group(grp_id, grp_name)
    assert res != ZCLStatus.SUCCESS
    assert ep.request.call_count == 1
    groups = ep.device.application.groups
    assert groups.add_group.call_count == 0
    assert groups.remove_group.call_count == 0


def _group_remove_mock(ep, success=True,
                       no_groups_cluster=False, not_member=False):
    async def mock_req(*args, **kwargs):
        if success:
            return [ZCLStatus.SUCCESS, mock.sentinel.group_id]
        return [ZCLStatus.DUPLICATE_EXISTS, mock.sentinel.group_id]

    if not no_groups_cluster:
        ep.add_input_cluster(4)
    ep.request = mock.MagicMock(side_effect=mock_req)

    ep.device.application.groups = mock.MagicMock(spec_set=group.Groups)
    grp = mock.MagicMock(spec_set=group.Group)
    ep.device.application.groups.__contains__.return_value = not not_member
    ep.device.application.groups.__getitem__.return_value = grp
    return ep, grp


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
