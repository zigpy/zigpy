"""Test Units for neighbors."""
import asyncio

import pytest

import zigpy.device
import zigpy.exceptions
import zigpy.neighbor
import zigpy.types as t
import zigpy.zdo.types as zdo_t

from .async_mock import AsyncMock, MagicMock, patch, sentinel


@pytest.fixture
def device():
    """Device fixture."""

    ieee = t.EUI64.convert("01:02:03:04:05:06:07:08")
    dev = zigpy.device.Device(MagicMock(), ieee, 0x1234)
    p2 = patch("zigpy.neighbor.REQUEST_DELAY", new=(0, 0))
    with patch.object(dev.zdo, "request", new=AsyncMock()), p2:
        yield dev


@pytest.fixture
def neighbours_f(device):
    """Neighbors fixture."""

    return zigpy.neighbor.Neighbors(device)


async def test_neighbors_scan(neighbours_f, device):
    """Test scanning."""

    data_in = (
        b'\x00\x10\x00\x03h\xf1W\xde\xcb\xaf4"\xfa\x0e\n\x00\x00\xa3"\x00)\x03%\x02'
        b'\x0f\xffh\xf1W\xde\xcb\xaf4"\x12Q\x03\xfe\xff^\xcf\xd0\xd4\x14%\x02\x0f\xfeh'
        b'\xf1W\xde\xcb\xaf4"&R \x00\x00\xa3"\x00\xd2\'%\x02\x0f\xff',
        b'\x00\x10\x03\x03h\xf1W\xde\xcb\xaf4"\x83\x19!\x00\x00\xa3"\x00\x10A%\x02\x0f'
        b'\xffh\xf1W\xde\xcb\xaf4"\xa8` \x00\x00\xa3"\x00\xe9e%\x02\x0f\xffh\xf1W\xde'
        b'\xcb\xaf4")\xb9\xda\xfe\xff\xcc\xcc\xccXw%\x02\x0f\xff',
        b'\x00\x10\x06\x03h\xf1W\xde\xcb\xaf4"`\xda!\x00\x00\xa3"\x00Z\x99%\x02\x0f'
        b'\xfeh\xf1W\xde\xcb\xaf4"\xe6\x8f\xd9\xfe\xff\xcc\xcc\xcc\xc3\x9b%\x02\x0f'
        b'\xffh\xf1W\xde\xcb\xaf4"p\xac$\xfe\xff\xd7k\x08f\xa5%\x02\x0f\xff',
        b'\x00\x10\t\x03h\xf1W\xde\xcb\xaf4"\x16\xed\x00\x00\x00\xa3"\x00\xf0\xb7%\x02'
        b'\x0f\xffh\xf1W\xde\xcb\xaf4"mn\x1c\x00\x00\xa3"\x00p\xda%\x02\x0f\xffh\xf1W'
        b'\xde\xcb\xaf4"\x80\xf4\xa6\x0c\x00o\r\x00\x9c\xda%\x02\x0f\xff',
        b'\x00\x10\x0c\x03h\xf1W\xde\xcb\xaf4"\xf48\xed\x18\x00K\x12\x009\xe8%\x02\x0f'
        b'\xfdh\xf1W\xde\xcb\xaf4"B\xd9!\x00\x00\xa3"\x00\x83\xed%\x02\x0f\xfeh\xf1W'
        b'\xde\xcb\xaf4"\xfe-\xed\x18\x00K\x12\x00\x1e\xf0%\x02\x0f\xfe',
        b'\x00\x10\x0f\x01h\xf1W\xde\xcb\xaf4"\x93\x13\x05\x00\x00\xb8\xd1\xf0\n\xf2%'
        b"\x02\x0f\xfc",
    )
    listener = MagicMock()
    neighbours_f.add_listener(listener)
    schema = zdo_t.CLUSTERS[zdo_t.ZDOCmd.Mgmt_Lqi_rsp][1]
    device.zdo.request.side_effect = (t.deserialize(d, schema)[0] for d in data_in)

    assert neighbours_f.neighbors == []
    res = await neighbours_f.scan()
    assert res
    assert neighbours_f.neighbors
    assert listener.neighbors_updated.call_count == 1


@pytest.mark.parametrize(
    "side_effect", (asyncio.TimeoutError, zigpy.exceptions.APIException)
)
async def test_neighbors_scan_fail(neighbours_f, device, side_effect):
    """Test scan fail."""

    assert neighbours_f.ieee == device.ieee
    listener = MagicMock()
    neighbours_f.add_listener(listener)
    device.zdo.request.side_effect = side_effect

    assert neighbours_f.neighbors == []
    res = await neighbours_f.scan()
    assert res is None
    assert neighbours_f.neighbors == []
    assert listener.neighbors_updated.call_count == 0


async def test_neighbors_unsupported(neighbours_f, device):
    """Test scanning."""

    listener = MagicMock()
    neighbours_f.add_listener(listener)
    device.zdo.request.return_value = (zdo_t.Status.NOT_SUPPORTED, [])

    assert neighbours_f.neighbors == []
    assert neighbours_f.supported is True
    res = await neighbours_f.scan()
    assert neighbours_f.supported is False
    assert res is None
    assert neighbours_f.neighbors == []
    assert listener.neighbors_updated.call_count == 0


async def test_neighbors_invalid_ieee(neighbours_f, device):
    """Test scanning."""

    data_in = (
        b'\x00\x02\x00\x02h\xf1W\xde\xcb\xaf4"\xff\xff\xff\xff\xff\xff\xff\xff)\x03'
        b'%\x02\x0f\xffh\xf1W\xde\xcb\xaf4"\x00\x00\x00\x00\x00\x00\x00\x00\x15\x14'
        b"%\x02\x0f\xfe",
    )

    listener = MagicMock()
    neighbours_f.add_listener(listener)
    schema = zdo_t.CLUSTERS[zdo_t.ZDOCmd.Mgmt_Lqi_rsp][1]
    device.zdo.request.side_effect = (t.deserialize(d, schema)[0] for d in data_in)

    assert neighbours_f.neighbors == []
    res = await neighbours_f.scan()
    assert res == []
    assert neighbours_f.neighbors == []
    assert listener.neighbors_updated.call_count == 1


def test_neighbor(device):
    """Test neighbor struct."""

    nei = zigpy.neighbor.Neighbor(
        zdo_t.Neighbor(device.ieee, device.ieee, 1, 2, 3, 4, 5), device
    )
    assert nei.device is device
    assert nei.neighbor.ieee == device.ieee


def test_neihgbors_magic_methods(neighbours_f):
    """Test neighbors methods."""

    neighbours_f.append(sentinel.other)
    neighbours_f[0] = sentinel.nei
    assert neighbours_f[0] is sentinel.nei
    assert [n for n in neighbours_f] == [sentinel.nei]
