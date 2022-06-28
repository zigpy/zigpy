"""Common fixtures."""
import logging
from unittest.mock import patch

import pytest

import zigpy.application
from zigpy.config import CONF_DATABASE, CONF_DEVICE, CONF_DEVICE_PATH
import zigpy.state as app_state
import zigpy.types as t
import zigpy.zdo.types as zdo_t

from .async_mock import MagicMock

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
    async def request(
        self,
        device,
        profile,
        cluster,
        src_ep,
        dst_ep,
        sequence,
        data,
        expect_reply=True,
        use_ieee=False,
    ):
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

    async def broadcast(
        self,
        profile,
        cluster,
        src_ep,
        dst_ep,
        grpid,
        radius,
        sequence,
        data,
        broadcast_address,
    ):
        pass

    async def mrequest(
        self,
        group_id,
        profile,
        cluster,
        src_ep,
        sequence,
        data,
        *,
        hops=0,
        non_member_radius=3,
    ):
        pass

    async def permit_with_key(self, node, code, time_s=60):
        pass

    async def write_network_info(self, *, network_info, node_info):
        pass

    async def load_network_info(self, *, load_devices=False):
        pass


@pytest.fixture
def app_mock():
    """ConntrollerApplication Mock."""

    config = App.SCHEMA(
        {CONF_DATABASE: None, CONF_DEVICE: {CONF_DEVICE_PATH: "/dev/null"}}
    )

    app = App(config)

    # Accessing the property fails when the mock's `spec_set` is being created
    with patch.object(app, "devices"):
        app_mock = MagicMock(spec_set=app)

    app_mock.state.node_info = app_state.NodeInfo(
        t.NWK(0x0000), ieee=NCP_IEEE, logical_type=zdo_t.LogicalType.Coordinator
    )
    return app_mock
