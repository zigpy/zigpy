import asyncio
from unittest import mock

import pytest
import zigpy.zcl as zcl

from zigpy import endpoint
from zigpy.zdo import types


@pytest.fixture
def ep():
    dev = mock.MagicMock()
    return endpoint.Endpoint(dev, 1)


def _test_initialize(ep, profile):
    loop = asyncio.get_event_loop()

    async def mockrequest(req, nwk, epid, tries=None, delay=None):
        sd = types.SimpleDescriptor()
        sd.endpoint = 1
        sd.profile = profile
        sd.device_type = 0xff
        sd.input_clusters = [5]
        sd.output_clusters = [6]
        return [0, None, sd]

    ep._device.zdo.request = mockrequest
    loop.run_until_complete(ep.initialize())

    assert ep.status > endpoint.Status.NEW
    assert 5 in ep.in_clusters
    assert 6 in ep.out_clusters


def test_initialize_zha(ep):
    return _test_initialize(ep, 260)


def test_initialize_zll(ep):
    return _test_initialize(ep, 49246)


def test_initialize_fail(ep):
    loop = asyncio.get_event_loop()

    async def mockrequest(req, nwk, epid, tries=None, delay=None):
        return [1, None, None]

    ep._device.zdo.request = mockrequest
    loop.run_until_complete(ep.initialize())

    assert ep.status == endpoint.Status.NEW


def test_reinitialize(ep):
    _test_initialize(ep, 260)
    assert ep.profile_id == 260
    ep.profile_id = 10
    _test_initialize(ep, 260)
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


def test_init_endpoint_info(ep):
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

    test_initialize_zha(ep)
    assert ep.manufacturer == 'Custom'
    assert ep.model == 'Model'


def test_init_endpoint_info_none(ep):
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

    test_initialize_zha(ep)


def test_init_endpoint_info_unicode(ep):
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

    test_initialize_zha(ep)


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


def test_init_endpoint_info_null_padded_manuf(ep):
    manufacturer = b'Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07'
    model = b'Mock Model'
    _init_endpoint_info(ep, manufacturer, model)

    assert ep.manufacturer == 'Mock Manufacturer'
    assert ep.model == 'Mock Model'


def test_init_endpoint_info_null_padded_model(ep):
    manufacturer = b'Mock Manufacturer'
    model = b'Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    _init_endpoint_info(ep, manufacturer, model)

    assert ep.manufacturer == 'Mock Manufacturer'
    assert ep.model == 'Mock Model'


def test_init_endpoint_info_null_padded_manuf_model(ep):
    manufacturer = b'Mock Manufacturer\x00\x04\\\x00\\\x00\x00\x00\x00\x00\x07'
    model = b'Mock Model\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    _init_endpoint_info(ep, manufacturer, model)

    assert ep.manufacturer == 'Mock Manufacturer'
    assert ep.model == 'Mock Model'
