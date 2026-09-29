"""Shared fixtures for Green Power tests.

The top-level :mod:`tests.conftest` already provides an ``app`` fixture
that returns a real :class:`~zigpy.application.ControllerApplication`
instance (with ``send_packet`` and ``listener_event`` wrapped for
inspection). Pytest discovers it automatically for nested conftests, so
ZGP tests just declare ``app`` as a parameter.

Because :attr:`ControllerApplication.green_power` is constructed in
``__init__``, the :class:`GreenPowerManager` is reachable as
``app.green_power``. The ``manager`` fixture below is a convenience
alias for tests that only need the manager.
"""

from __future__ import annotations

import pytest

from zigpy.zgp.manager import GreenPowerManager


@pytest.fixture
def manager(app) -> GreenPowerManager:
    """Return the GP manager attached to the test application.

    A valid operational Zigbee channel (15) is pinned on the app state so
    GP responses that encode ``channel - 11`` don't underflow. Individual
    tests remain free to overwrite ``app.state.network_info.channel``.
    """
    app.state.network_info.channel = 15
    return app.green_power


@pytest.fixture
def gp_events(manager: GreenPowerManager) -> list[tuple[str, object]]:
    """Capture every event emitted by the manager as ``(event_type, data)``.

    Replaces the old pattern of spying on ``app.listener_event`` now that
    ``GreenPowerManager`` uses :class:`~zigpy.event.EventBase` directly.
    """
    captured: list[tuple[str, object]] = []
    manager.on_all_events(
        lambda event_name, data: captured.append((event_name, data)),
        with_context=True,
    )
    return captured
