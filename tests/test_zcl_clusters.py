import asyncio
import re

import pytest
from unittest import mock
import zigpy.endpoint
import zigpy.zcl as zcl
import zigpy.ota as ota
import zigpy.zcl.clusters.security as sec


IMAGE_SIZE = 0x2345
IMAGE_OFFSET = 0x2000


def test_registry():
    for cluster_id, cluster in zcl.Cluster._registry.items():
        assert 0 <= getattr(cluster, 'cluster_id', -1) <= 65535
        assert cluster_id == cluster.cluster_id
        assert issubclass(cluster, zcl.Cluster)


def test_attributes():
    for cluster_id, cluster in zcl.Cluster._registry.items():
        for attrid, attrspec in cluster.attributes.items():
            assert 0 <= attrid <= 0xffff
            assert isinstance(attrspec, tuple)
            assert isinstance(attrspec[0], str)
            assert hasattr(attrspec[1], 'serialize')
            assert hasattr(attrspec[1], 'deserialize')


def _test_commands(cmdattr):
    for cluster_id, cluster in zcl.Cluster._registry.items():
        for cmdid, cmdspec in getattr(cluster, cmdattr).items():
            assert 0 <= cmdid <= 0xff
            assert isinstance(cmdspec, tuple), "Cluster %s" % (cluster_id, )
            assert len(cmdspec) == 3
            assert isinstance(cmdspec[0], str)
            assert isinstance(cmdspec[1], tuple)
            assert isinstance(cmdspec[2], bool)
            for t in cmdspec[1]:
                assert hasattr(t, 'serialize')
                assert hasattr(t, 'deserialize')


def test_server_commands():
    _test_commands('server_commands')


def test_client_commands():
    _test_commands('client_commands')


def test_ep_attributes():
    seen = set()
    for cluster_id, cluster in zcl.Cluster._registry.items():
        assert isinstance(cluster.ep_attribute, str)
        assert re.match('^[a-z_]+$', cluster.ep_attribute)
        assert cluster.ep_attribute not in seen
        seen.add(cluster.ep_attribute)

        ep = zigpy.endpoint.Endpoint(None, 1)
        assert not hasattr(ep, cluster.ep_attribute)


@pytest.mark.asyncio
async def test_time_cluster():
    ep = mock.MagicMock()
    ep.reply.side_effect = asyncio.coroutine(mock.MagicMock())
    t = zcl.Cluster._registry[0x000a](ep)

    tsn = 0

    t.handle_cluster_general_request(tsn, 1, [[0]])
    assert ep.reply.call_count == 0

    t.handle_cluster_general_request(tsn, 0, [[0]])
    assert ep.reply.call_count == 1
    assert ep.reply.call_args[0][2][3] == 0

    t.handle_cluster_general_request(tsn, 0, [[1]])
    assert ep.reply.call_count == 2
    assert ep.reply.call_args[0][2][3] == 1

    t.handle_cluster_general_request(tsn, 0, [[2]])
    assert ep.reply.call_count == 3
    assert ep.reply.call_args[0][2][3] == 2

    t.handle_cluster_general_request(tsn, 0, [[0, 1, 2]])
    assert ep.reply.call_count == 4
    assert ep.reply.call_args[0][2][3] == 0

    t.handle_cluster_general_request(tsn, 0, [[7]])
    assert ep.reply.call_count == 5
    assert ep.reply.call_args[0][2][3] == 7


@pytest.mark.asyncio
async def test_time_cluster_unsupported():
    ep = mock.MagicMock()
    ep.reply.side_effect = asyncio.coroutine(mock.MagicMock())
    t = zcl.Cluster._registry[0x000a](ep)

    tsn = 0

    t.handle_cluster_general_request(tsn, 0, [[199, 128]])
    assert ep.reply.call_count == 1
    assert ep.reply.call_args[0][2][-6:] == b'\xc7\x00\x86\x80\x00\x86'


@pytest.fixture
def ota_cluster():
    ep = mock.MagicMock()
    ep.device.application.ota = mock.MagicMock(spec_set=ota.OTA)
    return zcl.Cluster._registry[0x0019](ep)


@pytest.mark.asyncio
async def test_ota_handle_cluster_req(ota_cluster):
    ota_cluster._handle_cluster_request = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock()))

    ota_cluster.handle_cluster_request(mock.sentinel.tsn, mock.sentinel.cmd,
                                       mock.sentinel.args)
    assert ota_cluster._handle_cluster_request.call_count == 1


@pytest.mark.asyncio
async def test_ota_handle_cluster_req_wrapper(ota_cluster):
    ota_cluster._handle_query_next_image = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )
    ota_cluster._handle_image_block = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )
    ota_cluster._handle_upgrade_end = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    await ota_cluster._handle_cluster_request(mock.sentinel.tsn,
                                              0x01,
                                              [mock.sentinel.args])
    assert ota_cluster._handle_query_next_image.call_count == 1
    assert ota_cluster._handle_query_next_image.call_args[0][0] == mock.sentinel.args
    assert ota_cluster._handle_image_block.call_count == 0
    assert ota_cluster._handle_upgrade_end.call_count == 0
    ota_cluster._handle_query_next_image.reset_mock()
    ota_cluster._handle_image_block.reset_mock()
    ota_cluster._handle_upgrade_end.reset_mock()

    await ota_cluster._handle_cluster_request(mock.sentinel.tsn,
                                              0x03,
                                              [mock.sentinel.block_args])
    assert ota_cluster._handle_query_next_image.call_count == 0
    assert ota_cluster._handle_image_block.call_count == 1
    assert ota_cluster._handle_image_block.call_args[0][0] == mock.sentinel.block_args
    assert ota_cluster._handle_upgrade_end.call_count == 0
    ota_cluster._handle_query_next_image.reset_mock()
    ota_cluster._handle_image_block.reset_mock()
    ota_cluster._handle_upgrade_end.reset_mock()

    await ota_cluster._handle_cluster_request(mock.sentinel.tsn,
                                              0x06,
                                              [mock.sentinel.end_args])
    assert ota_cluster._handle_query_next_image.call_count == 0
    assert ota_cluster._handle_image_block.call_count == 0
    assert ota_cluster._handle_upgrade_end.call_count == 1
    assert ota_cluster._handle_upgrade_end.call_args[0][0] == mock.sentinel.end_args
    ota_cluster._handle_query_next_image.reset_mock()
    ota_cluster._handle_image_block.reset_mock()
    ota_cluster._handle_upgrade_end.reset_mock()

    await ota_cluster._handle_cluster_request(mock.sentinel.tsn,
                                              0x78,
                                              [mock.sentinel.just_args])
    assert ota_cluster._handle_query_next_image.call_count == 0
    assert ota_cluster._handle_image_block.call_count == 0
    assert ota_cluster._handle_upgrade_end.call_count == 0


def _ota_next_image(cluster, has_image=True, upgradeable=False):
    async def get_ota_mock(*args):
        if upgradeable:
            img = mock.MagicMock()
            img.should_update.return_value = True
            img.key.manufacturer_id = mock.sentinel.manufacturer_id
            img.key.image_type = mock.sentinel.image_type
            img.version = mock.sentinel.image_version
            img.header.image_size = mock.sentinel.image_size
        elif has_image:
            img = mock.MagicMock()
            img.should_update.return_value = False
        else:
            img = None
        return img

    cluster.endpoint.device.application.ota.get_ota_image.side_effect = \
        get_ota_mock
    return cluster._handle_query_next_image(
        mock.sentinel.field_ctrl,
        mock.sentinel.manufacturer_id,
        mock.sentinel.image_type,
        mock.sentinel.current_file_version,
        mock.sentinel.hw_version
    )


@pytest.mark.asyncio
async def test_ota_handle_query_next_image_no_img(ota_cluster):
    ota_cluster.query_next_image_response = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    await _ota_next_image(ota_cluster, has_image=False, upgradeable=False)
    assert ota_cluster.query_next_image_response.call_count == 1
    assert ota_cluster.query_next_image_response.call_args[0][0] == \
        zcl.foundation.Status.NO_IMAGE_AVAILABLE
    assert len(ota_cluster.query_next_image_response.call_args[0]) == 1


@pytest.mark.asyncio
async def test_ota_handle_query_next_image_not_upgradeable(ota_cluster):
    ota_cluster.query_next_image_response = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    await _ota_next_image(ota_cluster, has_image=True, upgradeable=False)
    assert ota_cluster.query_next_image_response.call_count == 1
    assert ota_cluster.query_next_image_response.call_args[0][0] == \
        zcl.foundation.Status.NO_IMAGE_AVAILABLE
    assert len(ota_cluster.query_next_image_response.call_args[0]) == 1


@pytest.mark.asyncio
async def test_ota_handle_query_next_image_upgradeable(ota_cluster):
    ota_cluster.query_next_image_response = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    await _ota_next_image(ota_cluster, has_image=True, upgradeable=True)
    assert ota_cluster.query_next_image_response.call_count == 1
    assert ota_cluster.query_next_image_response.call_args[0][0] == \
        zcl.foundation.Status.SUCCESS
    assert ota_cluster.query_next_image_response.call_args[0][1] == \
        mock.sentinel.manufacturer_id
    assert ota_cluster.query_next_image_response.call_args[0][2] == \
        mock.sentinel.image_type
    assert ota_cluster.query_next_image_response.call_args[0][3] == \
        mock.sentinel.image_version
    assert ota_cluster.query_next_image_response.call_args[0][4] == \
        mock.sentinel.image_size


def _ota_image_block(cluster,
                     has_image=True,
                     correct_version=True,
                     wrong_offset=False):
    async def get_ota_mock(*args):
        if has_image:
            img = mock.MagicMock()
            img.should_update.return_value = True
            img.key.manufacturer_id = mock.sentinel.manufacturer_id
            img.key.image_type = mock.sentinel.image_type
            img.version = mock.sentinel.image_version
            img.header.image_size = IMAGE_SIZE
            if wrong_offset:
                img.get_image_block.side_effect = ValueError()
            else:
                img.get_image_block.return_value = mock.sentinel.data
            if not correct_version:
                img.version = mock.sentinel.wrong_image_version
        else:
            img = None
        return img

    cluster.endpoint.device.application.ota.get_ota_image.side_effect = \
        get_ota_mock
    return cluster._handle_image_block(
        mock.sentinel.field_ctrl,
        mock.sentinel.manufacturer_id,
        mock.sentinel.image_type,
        mock.sentinel.image_version,
        IMAGE_OFFSET,
        mock.sentinel.max_data_size,
        mock.sentinel.addr,
        mock.sentinel.delay,
    )


@pytest.mark.asyncio
async def test_ota_handle_image_block_no_img(ota_cluster):
    ota_cluster.image_block_response = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    await _ota_image_block(ota_cluster, has_image=False, correct_version=True)
    assert ota_cluster.image_block_response.call_count == 1
    assert ota_cluster.image_block_response.call_args[0][0] == \
        zcl.foundation.Status.ABORT
    assert len(ota_cluster.image_block_response.call_args[0]) == 1
    ota_cluster.image_block_response.reset_mock()

    await _ota_image_block(ota_cluster, has_image=False, correct_version=False)
    assert ota_cluster.image_block_response.call_count == 1
    assert ota_cluster.image_block_response.call_args[0][0] == \
        zcl.foundation.Status.ABORT
    assert len(ota_cluster.image_block_response.call_args[0]) == 1


@pytest.mark.asyncio
async def test_ota_handle_image_block(ota_cluster):
    ota_cluster.image_block_response = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    await _ota_image_block(ota_cluster, has_image=True, correct_version=True)
    assert ota_cluster.image_block_response.call_count == 1
    assert ota_cluster.image_block_response.call_args[0][0] == \
        zcl.foundation.Status.SUCCESS
    assert ota_cluster.image_block_response.call_args[0][1] == \
        mock.sentinel.manufacturer_id
    assert ota_cluster.image_block_response.call_args[0][2] == \
        mock.sentinel.image_type
    assert ota_cluster.image_block_response.call_args[0][3] == \
        mock.sentinel.image_version
    assert ota_cluster.image_block_response.call_args[0][4] == \
        IMAGE_OFFSET
    assert ota_cluster.image_block_response.call_args[0][5] == \
        mock.sentinel.data
    ota_cluster.image_block_response.reset_mock()

    await _ota_image_block(ota_cluster, has_image=True, correct_version=False)
    assert ota_cluster.image_block_response.call_count == 1
    assert ota_cluster.image_block_response.call_args[0][0] == \
        zcl.foundation.Status.ABORT
    assert len(ota_cluster.image_block_response.call_args[0]) == 1


@pytest.mark.asyncio
async def test_ota_handle_image_block_wrong_offset(ota_cluster):
    ota_cluster.image_block_response = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    await _ota_image_block(ota_cluster,
                           has_image=True,
                           correct_version=True,
                           wrong_offset=True)
    assert ota_cluster.image_block_response.call_count == 1
    assert ota_cluster.image_block_response.call_args[0][0] == \
        zcl.foundation.Status.MALFORMED_COMMAND
    assert len(ota_cluster.image_block_response.call_args[0]) == 1


@pytest.mark.asyncio
async def test_ota_handle_upgrade_end(ota_cluster):
    ota_cluster.upgrade_end_response = mock.MagicMock(
        side_effect=asyncio.coroutine(mock.MagicMock())
    )

    await ota_cluster._handle_upgrade_end(mock.sentinel.status,
                                          mock.sentinel.manufacturer_id,
                                          mock.sentinel.image_type,
                                          mock.sentinel.image_version)

    assert ota_cluster.upgrade_end_response.call_count == 1
    assert ota_cluster.upgrade_end_response.call_args[0][0] == \
        mock.sentinel.manufacturer_id
    assert ota_cluster.upgrade_end_response.call_args[0][1] == \
        mock.sentinel.image_type
    assert ota_cluster.upgrade_end_response.call_args[0][2] == \
        mock.sentinel.image_version
    assert ota_cluster.upgrade_end_response.call_args[0][3] == 0x0000
    assert ota_cluster.upgrade_end_response.call_args[0][4] == 0x0000


def test_ias_zone_type():
    extra = b'\xaa\x55'
    zone, rest = sec.IasZoneType.deserialize(b'\x0d\x00' + extra)
    assert rest == extra
    assert zone is sec.IasZoneType.Motion_Sensor

    zone, rest = sec.IasZoneType.deserialize(b'\x81\x81' + extra)
    assert rest == extra
    assert zone.name.startswith('manufacturer_specific')
    assert zone.value == 0x8181
