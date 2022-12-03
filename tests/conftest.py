"""Common fixtures."""
from __future__ import annotations

import copy
import logging
import typing
from unittest.mock import Mock

import pytest

import zigpy.application
from zigpy.config import CONF_DATABASE, CONF_DEVICE, CONF_DEVICE_PATH
import zigpy.state as app_state
import zigpy.types as t
import zigpy.zdo.types as zdo_t

from .async_mock import AsyncMock, MagicMock

if typing.TYPE_CHECKING:
    import zigpy.device


NCP_IEEE = t.EUI64.convert("aa:11:22:bb:33:44:be:ef")


class FailOnBadFormattingHandler(logging.Handler):
    def emit(self, record):
        try:
            record.msg % record.args
        except Exception as e:
            pytest.fail(
                f"Failed to format log message {record.msg!r} with {record.args!r}: {e}"
            )


@pytest.fixture(autouse=True)
def raise_on_bad_log_formatting():
    handler = FailOnBadFormattingHandler()

    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    try:
        yield
    finally:
        root.removeHandler(handler)


class App(zigpy.application.ControllerApplication):
    async def send_packet(self, packet):
        pass

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def start_network(self):
        pass

    async def force_remove(self, dev):
        pass

    async def add_endpoint(self, descriptor):
        pass

    async def permit_ncp(self, time_s=60):
        pass

    async def permit_with_key(self, node, code, time_s=60):
        pass

    async def reset_network_info(self):
        pass

    async def write_network_info(self, *, network_info, node_info):
        pass

    async def load_network_info(self, *, load_devices=False):
        pass


def recursive_dict_merge(
    obj: dict[str, typing.Any], updates: dict[str, typing.Any]
) -> dict[str, typing.Any]:
    result = copy.deepcopy(obj)

    for key, update in updates.items():
        if isinstance(update, dict):
            result[key] = recursive_dict_merge(result[key], update)
        else:
            result[key] = update

    return result


def make_app(
    config_updates: dict[str, typing.Any],
    app_base: zigpy.application.ControllerApplication = App,
) -> zigpy.application.ControllerApplication:
    config = recursive_dict_merge(
        {CONF_DATABASE: None, CONF_DEVICE: {CONF_DEVICE_PATH: "/dev/null"}},
        config_updates,
    )

    app = app_base(app_base.SCHEMA(config))
    app.state.node_info = app_state.NodeInfo(
        nwk=t.NWK(0x0000), ieee=NCP_IEEE, logical_type=zdo_t.LogicalType.Coordinator
    )

    app.device_initialized = Mock(wraps=app.device_initialized)
    app.listener_event = Mock(wraps=app.listener_event)
    app.get_sequence = MagicMock(wraps=app.get_sequence, return_value=123)
    app.send_packet = AsyncMock(wraps=app.send_packet)
    app.write_network_info = AsyncMock(wraps=app.write_network_info)

    return app


@pytest.fixture
def app():
    """ControllerApplication Mock."""
    return make_app({})


@pytest.fixture
def app_mock():
    """ControllerApplication Mock."""
    return make_app({})


def make_ieee(start=0):
    return t.EUI64(map(t.uint8_t, range(start, start + 8)))


def make_node_desc(
    *, logical_type: zdo_t.LogicalType = zdo_t.LogicalType.Router
) -> zdo_t.NodeDescriptor:
    return zdo_t.NodeDescriptor(
        logical_type=logical_type,
        complex_descriptor_available=0,
        user_descriptor_available=0,
        reserved=0,
        aps_flags=0,
        frequency_band=zdo_t.NodeDescriptor.FrequencyBand.Freq2400MHz,
        mac_capability_flags=zdo_t.NodeDescriptor.MACCapabilityFlags.AllocateAddress,
        manufacturer_code=4174,
        maximum_buffer_size=82,
        maximum_incoming_transfer_size=82,
        server_mask=0,
        maximum_outgoing_transfer_size=82,
        descriptor_capability_field=zdo_t.NodeDescriptor.DescriptorCapability.NONE,
    )


@pytest.fixture
def make_initialized_device():
    count = 1

    def inner(app):
        nonlocal count

        dev = app.add_device(nwk=0x1000 + count, ieee=make_ieee(count))
        dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

        ep = dev.add_endpoint(1)
        ep.status = zigpy.endpoint.Status.ZDO_INIT
        ep.profile_id = 260
        ep.device_type = zigpy.profiles.zha.DeviceType.PUMP

        count += 1

        return dev

    return inner


def make_neighbor(
    *,
    ieee: t.EUI64,
    nwk: t.NWK,
    device_type: zdo_t.Neighbor.DeviceType = zdo_t.Neighbor.DeviceType.Router,
    rx_on_when_idle=True,
    relationship: zdo_t.Neighbor.Relationship = zdo_t.Neighbor.Relationship.Child,
) -> zdo_t.Neighbor:
    return zdo_t.Neighbor(
        extended_pan_id=make_ieee(start=0),
        ieee=ieee,
        nwk=nwk,
        device_type=device_type,
        rx_on_when_idle=int(rx_on_when_idle),
        relationship=relationship,
        reserved1=0,
        permit_joining=0,
        reserved2=0,
        depth=15,
        lqi=250,
    )


def make_neighbor_from_device(
    device: zigpy.device.Device,
    *,
    relationship: zdo_t.Neighbor.Relationship = zdo_t.Neighbor.Relationship.Child,
):
    assert device.node_desc is not None
    return make_neighbor(
        ieee=device.ieee,
        nwk=device.nwk,
        device_type=zdo_t.Neighbor.DeviceType(int(device.node_desc.logical_type)),
        rx_on_when_idle=device.node_desc.is_receiver_on_when_idle,
        relationship=relationship,
    )


def make_route(
    *,
    dest_nwk: t.NWK,
    next_hop: t.NWK,
    status: zdo_t.RouteStatus = zdo_t.RouteStatus.Active,
) -> zdo_t.Route:
    return zdo_t.Route(
        DstNWK=dest_nwk,
        RouteStatus=status,
        MemoryConstrained=0,
        ManyToOne=0,
        RouteRecordRequired=0,
        Reserved=0,
        NextHop=next_hop,
    )
