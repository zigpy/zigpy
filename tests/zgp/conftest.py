"""Shared pytest fixtures for Green Power tests."""

from __future__ import annotations

import asyncio

from tests.async_mock import AsyncMock, MagicMock, Mock

import pytest

import zigpy.types as t

from zigpy.zgp.manager import GreenPowerManager


@pytest.fixture
def mock_app() -> MagicMock:
    """Create a mock ControllerApplication with just enough state for GP."""
    app = MagicMock()
    app.state.node_info.ieee = t.EUI64.convert("00:11:22:33:44:55:66:77")
    app.state.node_info.nwk = t.NWK(0x0000)
    app.state.network_info.channel = 15
    app.send_packet = AsyncMock()
    app.listener_event = Mock()
    app.create_task = Mock(
        side_effect=lambda coro, name=None: asyncio.ensure_future(coro)
    )
    return app


@pytest.fixture
def manager(mock_app: MagicMock) -> GreenPowerManager:
    """Create a GreenPowerManager attached to the mock app."""
    return GreenPowerManager(mock_app)
