"""Shared fixtures for Green Power tests."""

from __future__ import annotations

import asyncio

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


async def wait_for_gp_processing() -> None:
    """Wait for the manager to finish processing received commissioning GPDFs."""
    await asyncio.gather(
        *(
            task
            for task in asyncio.all_tasks()
            if task.get_name().startswith("gp_process_command")
        )
    )
