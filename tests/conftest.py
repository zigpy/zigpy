"""Common fixtures."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import copy
import logging
import threading
import typing
from unittest.mock import Mock, patch

import aiosqlite
import pytest

import zigpy.application
from zigpy.config import (
    CONF_DATABASE,
    CONF_DEVICE,
    CONF_DEVICE_PATH,
    CONF_OTA,
    CONF_OTA_ENABLED,
)
import zigpy.state as app_state
import zigpy.types as t
from zigpy.typing import UNDEFINED, UndefinedType
from zigpy.zcl import Cluster, foundation
import zigpy.zdo.types as zdo_t

from .async_mock import AsyncMock, MagicMock

if typing.TYPE_CHECKING:
    import zigpy.device

_LOGGER = logging.getLogger(__name__)

NCP_IEEE = t.EUI64.convert("aa:11:22:bb:33:44:be:ef")


class FailOnBadFormattingHandler(logging.Handler):
    def emit(self, record):
        try:
            record.msg % record.args
        except Exception as e:  # noqa: BLE001
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


class BaseApp(zigpy.application.ControllerApplication):
    async def send_packet(self, packet):
        async with self._limit_concurrency(priority=packet.priority):
            return await self._send_packet(packet)

    async def _send_packet(self, packet):
        await asyncio.sleep(0)

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def start_network(self):
        dev = add_initialized_device(
            app=self, nwk=self.state.node_info.nwk, ieee=self.state.node_info.ieee
        )
        dev.model = "Coordinator Model"
        dev.manufacturer = "Coordinator Manufacturer"

        dev.zdo.Mgmt_NWK_Update_req = AsyncMock(
            return_value=[
                zdo_t.Status.SUCCESS,
                t.Channels.ALL_CHANNELS,
                0,
                0,
                [80] * 16,
            ]
        )

    async def force_remove(self, dev):
        pass

    async def add_endpoint(self, descriptor):
        pass

    async def permit_ncp(self, time_s=60):
        pass

    async def permit_with_link_key(self, node, link_key, time_s=60):
        pass

    async def reset_network_info(self):
        pass

    async def write_network_info(self, *, network_info, node_info):
        pass

    async def load_network_info(self, *, load_devices=False):
        self.state.network_info.channel = 15


class FeaturelessApp(BaseApp):
    """Zigpy application implementation that supports no optional features."""


class App(BaseApp):
    """Zigpy application implementation that supports all optional features."""

    async def _network_scan(self, channels, duration_exp):
        if False:
            yield

    async def _packet_capture(self, channel):
        if False:
            yield

    async def _packet_capture_change_channel(self, channel):
        pass

    async def _set_tx_power(self, tx_power: float) -> float:
        return round(tx_power)

    async def _get_recommended_tx_power(self, country: str) -> float:
        if country == "US":
            return 8
        else:
            return 10

    async def _get_maximum_tx_power(self, country: str) -> float:
        if country == "US":
            return 8
        else:
            return 10


def recursive_dict_merge(
    obj: dict[str, typing.Any], updates: dict[str, typing.Any]
) -> dict[str, typing.Any]:
    result = copy.deepcopy(obj)

    for key, update in updates.items():
        if isinstance(update, dict) and key in result:
            result[key] = recursive_dict_merge(result[key], update)
        else:
            result[key] = update

    return result


def make_app(
    config_updates: dict[str, typing.Any],
    app_base: type[zigpy.application.ControllerApplication] = App,
) -> zigpy.application.ControllerApplication:
    config = recursive_dict_merge(
        {
            CONF_DATABASE: None,
            CONF_DEVICE: {CONF_DEVICE_PATH: "/dev/null"},
            CONF_OTA: {
                CONF_OTA_ENABLED: False,
            },
        },
        config_updates,
    )

    app = app_base(config)
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
    *,
    logical_type: zdo_t.LogicalType = zdo_t.LogicalType.Router,
    manufacturer_code: int = 4174,
) -> zdo_t.NodeDescriptor:
    return zdo_t.NodeDescriptor(
        logical_type=logical_type,
        complex_descriptor_available=0,
        user_descriptor_available=0,
        reserved=0,
        aps_flags=0,
        frequency_band=zdo_t.NodeDescriptor.FrequencyBand.Freq2400MHz,
        mac_capability_flags=zdo_t.NodeDescriptor.MACCapabilityFlags.AllocateAddress,
        manufacturer_code=manufacturer_code,
        maximum_buffer_size=82,
        maximum_incoming_transfer_size=82,
        server_mask=0,
        maximum_outgoing_transfer_size=82,
        descriptor_capability_field=zdo_t.NodeDescriptor.DescriptorCapability.NONE,
    )


def add_initialized_device(app, nwk, ieee):
    dev = app.add_device(nwk=nwk, ieee=ieee)
    dev.node_desc = make_node_desc(logical_type=zdo_t.LogicalType.Router)

    ep = dev.add_endpoint(1)
    ep.status = zigpy.endpoint.Status.ZDO_INIT
    ep.profile_id = 260
    ep.device_type = zigpy.profiles.zha.DeviceType.PUMP

    return dev


@pytest.fixture
def make_initialized_device():
    count = 1

    def inner(app):
        nonlocal count

        dev = add_initialized_device(app, nwk=0x1000 + count, ieee=make_ieee(count))
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


# Taken from Home Assistant's `conftest.py`
@pytest.fixture(autouse=True)
def verify_cleanup() -> typing.Generator[None, None, None]:
    """Verify that the test has cleaned up resources correctly."""

    try:
        event_loop = asyncio.get_running_loop()
    except RuntimeError:
        yield
        return

    threads_before = frozenset(threading.enumerate())
    tasks_before = asyncio.all_tasks(event_loop)
    yield

    event_loop.run_until_complete(event_loop.shutdown_default_executor())

    # Warn and clean-up lingering tasks and timers
    # before moving on to the next test.
    tasks = asyncio.all_tasks(event_loop) - tasks_before
    for task in tasks:
        _LOGGER.warning("Linger task after test %r", task)
        task.cancel()
    if tasks:
        event_loop.run_until_complete(asyncio.wait(tasks))

    for handle in event_loop._scheduled:  # type: ignore[attr-defined]
        if not handle.cancelled():
            _LOGGER.warning("Lingering timer after test %r", handle)
            handle.cancel()

    # Verify no threads were left behind.
    threads = frozenset(threading.enumerate()) - threads_before
    for thread in threads:
        if isinstance(thread, threading._DummyThread):
            continue

        # Kill lingering aiosqlite threads so pytest doesn't hang
        if isinstance(thread, aiosqlite.Connection):
            _LOGGER.warning("Stopping lingering aiosqlite thread %r", thread)
            thread._stop_running()
            thread.join(timeout=1)

        pytest.fail(f"Lingering thread after test: {thread!r}")


@contextmanager
def mock_attribute_reads(
    cluster: Cluster,
    mock_attributes: dict[str | int | foundation.ZCLAttributeDef, typing.Any],
) -> typing.Generator[
    tuple[AsyncMock, dict[str | int | foundation.ZCLAttributeDef, AsyncMock]],
    None,
    None,
]:
    """Mock attribute reads on a cluster."""
    mock_reads = {}

    for key, value in mock_attributes.items():
        if not callable(value):
            value = Mock(return_value=value)

        mock_reads[cluster.find_attribute(key)] = value

    async def read_attributes_raw(
        attributes,
        *args,
        manufacturer: int | UndefinedType | None = UNDEFINED,
        **kwargs,
    ):
        status_records = []

        for attrid in attributes:
            record = foundation.ReadAttributeRecord(attrid=attrid)
            attr_def = cluster.find_attribute(attrid, manufacturer_code=manufacturer)

            if attr_def in mock_reads:
                value = mock_reads[attr_def]()

                if isinstance(value, foundation.Status):
                    record.status = value
                else:
                    record.status = foundation.Status.SUCCESS
                    record.value = foundation.TypeValue(
                        type=attr_def.zcl_type, value=value
                    )
            else:
                record.status = foundation.Status.UNSUPPORTED_ATTRIBUTE

            status_records.append(record)

        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Read_Attributes_rsp
        ].schema(status_records=status_records)

    with patch.object(
        cluster, "read_attributes_raw", autospec=True, side_effect=read_attributes_raw
    ) as mock_read:
        yield mock_read, mock_attributes


@contextmanager
def mock_attribute_writes(
    cluster: Cluster,
    mock_attributes: dict[str | int | foundation.ZCLAttributeDef, typing.Any],
) -> typing.Generator[
    tuple[AsyncMock, dict[str | int | foundation.ZCLAttributeDef, AsyncMock]],
    None,
    None,
]:
    """Mock attribute writes on a cluster."""
    mock_writes = {}

    for key, value in mock_attributes.items():
        if not callable(value):
            value = Mock(return_value=value)

        mock_writes[cluster.find_attribute(key)] = value

    async def write_attributes_raw(
        attributes,
        *args,
        manufacturer: int | UndefinedType | None = UNDEFINED,
        **kwargs,
    ):
        records = []

        for attr in attributes:
            attr_def = cluster.find_attribute(
                attr.attrid, manufacturer_code=manufacturer
            )
            record = foundation.WriteAttributesStatusRecord(attrid=attr_def.id)

            if attr_def in mock_writes:
                value = mock_writes[attr_def](attr.value)

                if isinstance(value, foundation.Status):
                    record.status = value
                else:
                    record.status = foundation.Status.SUCCESS
            else:
                record.status = foundation.Status.UNSUPPORTED_ATTRIBUTE

            records.append(record)

        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Write_Attributes_rsp
        ].schema(status_records=foundation.WriteAttributesResponse(records))

    with patch.object(
        cluster, "_write_attributes", autospec=True, side_effect=write_attributes_raw
    ) as mock_write:
        yield mock_write, mock_attributes


async def mock_attribute_report(
    cluster: Cluster,
    attributes: dict[str | int | foundation.ZCLAttributeDef, typing.Any],
    *,
    tsn: int | None = None,
) -> None:
    """Mock attribute reports on a cluster."""
    reports = []
    manufacturer_codes: set[int | None] = set()

    for attr, value in attributes.items():
        if isinstance(attr, int):
            # Raw attribute ID for unknown attributes
            manufacturer_codes.add(None)
            reports.append(
                foundation.Attribute(
                    attrid=attr,
                    value=foundation.TypeValue(
                        type=foundation.DataType.from_python_type(type(value)).type_id,
                        value=value,
                    ),
                )
            )
        else:
            attr_def = cluster.find_attribute(attr)
            manufacturer_codes.add(cluster._get_effective_manufacturer_code(attr_def))

            reports.append(
                foundation.Attribute(
                    attrid=attr_def.id,
                    value=foundation.TypeValue(type=attr_def.zcl_type, value=value),
                )
            )

    if len(manufacturer_codes) != 1:
        raise ValueError(
            f"All attributes must have the same manufacturer code, got {manufacturer_codes}"
        )

    if tsn is None:
        tsn = cluster.endpoint.device.get_sequence()

    manufacturer: int | None = manufacturer_codes.pop()

    frame_control = foundation.FrameControl(
        frame_type=foundation.FrameType.GLOBAL_COMMAND,
        is_manufacturer_specific=(manufacturer is not None),
        direction=(
            foundation.Direction.Client_to_Server
            if cluster.is_client
            else foundation.Direction.Server_to_Client
        ),
        disable_default_response=False,
        reserved=0b000,
    )

    hdr = foundation.ZCLHeader(
        frame_control=frame_control,
        manufacturer=manufacturer,
        tsn=tsn,
        command_id=foundation.GeneralCommand.Report_Attributes,
    )

    command = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand.Report_Attributes
    ].schema(attribute_reports=reports)

    cluster.handle_cluster_general_request(hdr, command)
