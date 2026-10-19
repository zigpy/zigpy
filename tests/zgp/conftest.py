"""Shared fixtures for Green Power tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest

from zigpy.zgp.manager import GreenPowerManager
from zigpy.zgp.types import SrcID
from zigpy.zgp.util import synthetic_ieee


@pytest.fixture
async def manager(app) -> AsyncGenerator[GreenPowerManager]:
    """Return the GP manager attached to the test application.

    A valid operational Zigbee channel (15) is pinned on the app state so
    GP responses that encode `channel - 11` don't underflow. Individual
    tests remain free to overwrite `app.state.network_info.channel`.
    """
    app.state.network_info.channel = 15
    yield app.green_power
    await app.green_power.shutdown()


def _is_processing(app, task: asyncio.Task) -> bool:
    name = task.get_name()

    if name.startswith("gp_process_command"):
        return True

    if name.startswith("gp_commissioning-0x"):
        # A GPD in bidirectional commissioning leaves its task waiting for its Success
        # GPDF, once its pending device is registered
        src_id = SrcID(int(name.removeprefix("gp_commissioning-0x"), 16))
        return app.green_power.get_pending_device(synthetic_ieee(src_id)) is None

    return False


async def wait_for_gp_processing(app) -> None:
    """Wait for the manager to finish processing received GPDFs."""
    while any(
        not task.done() and _is_processing(app, task) for task in asyncio.all_tasks()
    ):
        await asyncio.sleep(0)


async def wait_for_commissioning() -> None:
    """Wait for all commissioning tasks to finish, once none waits for a Success GPDF."""
    await asyncio.gather(
        *(
            task
            for task in asyncio.all_tasks()
            if task.get_name().startswith("gp_commissioning-")
        ),
        return_exceptions=True,
    )
