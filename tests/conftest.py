"""Common fixtures."""
import logging

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

    try:
        yield
    finally:
        root.removeHandler(handler)


class App(zigpy.application.ControllerApplication):
    async def shutdown(self):
        pass

    async def startup(self, auto_form=False):
        pass

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

    async def permit_ncp(self, time_s=60):
        pass

    async def probe(self, config):
        return True


@pytest.fixture
def app_mock():
    """ConntrollerApplication Mock."""

    config = App.SCHEMA(
        {CONF_DATABASE: None, CONF_DEVICE: {CONF_DEVICE_PATH: "/dev/null"}}
    )
    app_mock = MagicMock(spec_set=App(config))
    app_mock.state.node_information = app_state.NodeInfo(
        t.NWK(0x0000), ieee=NCP_IEEE, logical_type=zdo_t.LogicalType.Coordinator
    )
    return app_mock
