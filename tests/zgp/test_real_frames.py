"""Manager tests driven by real-device frames.

These tests exercise ``GreenPowerManager._process_commissioning`` and
``_dispatch_gp_command`` with payloads captured from an actual Busch-Jaeger
6716 U "Friends of Hue" switch. The goal is to pin behaviour against real
hardware, not to cover more code paths than the synthetic tests already do.

The frames arrive below the bellows EZSP layer, so the public packet entry
point (``handle_packet``) cannot be used directly without first solving the
bellows parsing bug that is out of scope for this PR. We call the internal
async methods directly, which is the same injection point every other
manager test uses.
"""

from __future__ import annotations

from unittest.mock import patch

from zigpy.zgp.device import GPDevice
from zigpy.zgp.events import CommandReceived, DeviceJoined
from zigpy.zgp.manager import GreenPowerManager
from zigpy.zgp.types import SecurityLevel

from tests.zgp.fixtures.busch_jaeger_6716u import (
    BJ6716U_COMMISSIONING_PAYLOAD,
    BJ6716U_EXPECTED,
    BJ6716U_OPERATIONAL_FRAMES,
    BJ6716U_SOURCE_ID,
)


# A fake decrypted key used when we want to bypass the real AES-CCM key
# unwrap (which would fail because the device uses an out-of-band key that
# is not the default GP link key).
FAKE_DECRYPTED_KEY: bytes = bytes(range(16))


async def _commission(manager: GreenPowerManager) -> None:
    """Open the window and push the real commissioning payload through."""
    await manager.permit_join(time_s=60)
    await manager._process_commissioning(
        source_id=BJ6716U_SOURCE_ID,
        frame_counter=0xFFFFFFFF,
        payload=BJ6716U_COMMISSIONING_PAYLOAD,
    )


# -- Commissioning -----------------------------------------------------------


async def test_rejects_oob_encrypted_key_gracefully(manager, gp_events) -> None:
    """No device is created when the OOB key cannot be decrypted.

    The FoH switch encrypts its GPD key with an individual out-of-band
    key that zigpy does not know. The manager should log a warning and
    bail out cleanly without creating a half-configured device.
    """
    await _commission(manager)

    assert manager.get_device(BJ6716U_SOURCE_ID) is None
    assert not any(isinstance(e, DeviceJoined) for _, e in gp_events)


async def test_creates_device_when_key_unwrap_succeeds(manager) -> None:
    """Patching key unwrap lets us exercise the rest of the flow."""
    with patch(
        "zigpy.zgp.manager.decrypt_security_key",
        return_value=FAKE_DECRYPTED_KEY,
    ):
        await _commission(manager)

    device = manager.get_device(BJ6716U_SOURCE_ID)
    assert device is not None
    assert device.source_id == BJ6716U_SOURCE_ID
    assert device.device_id == BJ6716U_EXPECTED.device_id
    assert bytes(device.security_key) == FAKE_DECRYPTED_KEY
    assert device.security_level == SecurityLevel.FullFrameCounterAndMIC
    # The manager prefers the advertised OutgoingCounter over the
    # notification frame counter when the payload provides one.
    assert device.frame_counter == BJ6716U_EXPECTED.outgoing_counter


async def test_stores_all_17_gpd_commands(manager) -> None:
    """The device exposes every button/scene command it can emit."""
    with patch(
        "zigpy.zgp.manager.decrypt_security_key",
        return_value=FAKE_DECRYPTED_KEY,
    ):
        await _commission(manager)

    device = manager.get_device(BJ6716U_SOURCE_ID)
    assert device is not None
    assert device.gpd_commands == BJ6716U_EXPECTED.gpd_commands
    assert len(device.gpd_commands) == 17


async def test_fires_joined_event(manager, gp_events) -> None:
    """Successful commissioning notifies listeners."""
    with patch(
        "zigpy.zgp.manager.decrypt_security_key",
        return_value=FAKE_DECRYPTED_KEY,
    ):
        await _commission(manager)

    joined = [e for _, e in gp_events if isinstance(e, DeviceJoined)]
    assert len(joined) == 1
    assert joined[0].device.source_id == BJ6716U_SOURCE_ID


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
