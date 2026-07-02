"""Manager tests driven by frames captured from a real Busch-Jaeger 6716 U.

These pin behaviour against actual hardware. The frames arrive below the
bellows EZSP layer, so we call the manager's internal async methods directly
(the same injection point the other manager tests use).
"""

from __future__ import annotations

from tests.zgp.fixtures.busch_jaeger_6716u import (
    BJ6716U_COMMISSIONING_PAYLOAD,
    BJ6716U_DECRYPTED_KEY,
    BJ6716U_EXPECTED,
    BJ6716U_OPERATIONAL_FRAMES,
    BJ6716U_SOURCE_ID,
)
from zigpy.zgp.device import GPDevice
from zigpy.zgp.events import CommandReceived, DeviceJoined
from zigpy.zgp.manager import GreenPowerManager
from zigpy.zgp.types import SecurityLevel


async def _commission(manager: GreenPowerManager) -> None:
    """Open the window and push the real commissioning payload through."""
    await manager.permit_join(time_s=60)
    await manager._process_commissioning(
        source_id=BJ6716U_SOURCE_ID,
        frame_counter=0xFFFFFFFF,
        payload=BJ6716U_COMMISSIONING_PAYLOAD,
    )


# -- Commissioning -----------------------------------------------------------


async def test_real_commissioning_succeeds(manager, gp_events) -> None:
    """The captured 0xE0 frame unwraps its key and registers the device."""
    await _commission(manager)

    device = manager.get_device(BJ6716U_SOURCE_ID)
    assert device is not None
    assert device.source_id == BJ6716U_SOURCE_ID
    assert device.device_id == BJ6716U_EXPECTED.device_id
    assert bytes(device.security_key) == BJ6716U_DECRYPTED_KEY
    assert device.security_level == SecurityLevel.FullFrameCounterAndMIC
    # The advertised OutgoingCounter wins over the notification frame counter.
    assert device.frame_counter == BJ6716U_EXPECTED.outgoing_counter

    joined = [e for _, e in gp_events if isinstance(e, DeviceJoined)]
    assert len(joined) == 1
    assert joined[0].device.source_id == BJ6716U_SOURCE_ID


async def test_stores_all_17_gpd_commands(manager) -> None:
    """The device exposes every button/scene command it advertised."""
    await _commission(manager)

    device = manager.get_device(BJ6716U_SOURCE_ID)
    assert device is not None
    assert device.gpd_commands == BJ6716U_EXPECTED.gpd_commands
    assert len(device.gpd_commands) == 17


# -- Operational frame handling ---------------------------------------------


def _paired_device(manager: GreenPowerManager) -> GPDevice:
    """Register the switch as if commissioning had just completed."""
    device = GPDevice(
        source_id=BJ6716U_SOURCE_ID,
        device_id=BJ6716U_EXPECTED.device_id,
        frame_counter=BJ6716U_EXPECTED.outgoing_counter,
    )
    manager.add_device(device)
    return device


async def test_accepts_first_operational_frame(manager, gp_events) -> None:
    """Counter 0x1ded (next after commissioning 0x1dec) is accepted."""
    device = _paired_device(manager)
    frame = BJ6716U_OPERATIONAL_FRAMES[0]

    await manager._dispatch_gp_command(
        source_id=BJ6716U_SOURCE_ID,
        frame_counter=frame.frame_counter,
        command_id=frame.command_id,
        payload=b"",
    )

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert len(commands) == 1
    assert commands[0].command_id == frame.command_id
    assert device.frame_counter == frame.frame_counter


async def test_rejects_replayed_counter(manager, gp_events) -> None:
    """Sending the same counter twice only fires the event once."""
    device = _paired_device(manager)
    frame = BJ6716U_OPERATIONAL_FRAMES[0]

    for _ in range(2):
        await manager._dispatch_gp_command(
            source_id=BJ6716U_SOURCE_ID,
            frame_counter=frame.frame_counter,
            command_id=frame.command_id,
            payload=b"",
        )

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert len(commands) == 1
    assert device.frame_counter == frame.frame_counter


async def test_accepts_monotonic_sequence(manager, gp_events) -> None:
    """Four successive counters all produce a command event."""
    device = _paired_device(manager)

    for frame in BJ6716U_OPERATIONAL_FRAMES:
        await manager._dispatch_gp_command(
            source_id=BJ6716U_SOURCE_ID,
            frame_counter=frame.frame_counter,
            command_id=frame.command_id,
            payload=b"",
        )

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert len(commands) == len(BJ6716U_OPERATIONAL_FRAMES)
    assert device.frame_counter == BJ6716U_OPERATIONAL_FRAMES[-1].frame_counter


async def test_rejects_older_counter(manager, gp_events) -> None:
    """An older counter after a recent one is dropped."""
    device = _paired_device(manager)
    recent = BJ6716U_OPERATIONAL_FRAMES[-1]
    older = BJ6716U_OPERATIONAL_FRAMES[0]

    await manager._dispatch_gp_command(
        source_id=BJ6716U_SOURCE_ID,
        frame_counter=recent.frame_counter,
        command_id=recent.command_id,
        payload=b"",
    )
    await manager._dispatch_gp_command(
        source_id=BJ6716U_SOURCE_ID,
        frame_counter=older.frame_counter,
        command_id=older.command_id,
        payload=b"",
    )

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert len(commands) == 1
    assert device.frame_counter == recent.frame_counter
