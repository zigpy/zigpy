"""Tests for Green Power device packet handling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from zigpy.device import GreenPowerDevice
import zigpy.types as t
from zigpy.zgp.types import (
    ApplicationID,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SrcID,
)

TIMESTAMP = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def device() -> GreenPowerDevice:
    return GreenPowerDevice(
        None, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )


@pytest.fixture
def events(device) -> list:
    events = []
    device.on_event("gp_command_received", events.append)
    return events


def make_packet(
    frame_counter: int,
    *,
    security_level: SecurityLevel = SecurityLevel.Encrypted,
    security_key_type: SecurityKeyType = SecurityKeyType.GPDGroupKey,
    offset: timedelta = timedelta(0),
    lqi: int = 200,
    rssi: int = -50,
) -> t.ZigbeeGpPacket:
    return t.ZigbeeGpPacket(
        timestamp=TIMESTAMP + offset,
        application_id=ApplicationID.SrcID,
        src_id=SrcID(0x12345678),
        command_id=GPDCommandID.Toggle,
        frame_counter=t.uint32_t(frame_counter),
        security_level=security_level,
        security_key_type=security_key_type,
        lqi=t.uint8_t(lqi),
        rssi=t.int8s(rssi),
    )


def commission_security(device: GreenPowerDevice) -> None:
    device.security_level = SecurityLevel.Encrypted
    device.security_key_type = SecurityKeyType.GPDGroupKey


def test_missing_gpd_id() -> None:
    with pytest.raises(ValueError, match="`src_id` is required"):
        GreenPowerDevice(None, application_id=ApplicationID.SrcID)

    with pytest.raises(ValueError, match="`ieee` is required"):
        GreenPowerDevice(None, application_id=ApplicationID.IEEE)


def test_packet_received(device, events) -> None:
    device.packet_received(make_packet(1000))

    assert len(events) == 1
    assert events[0].device_ieee == str(device.ieee)
    assert events[0].command_id == GPDCommandID.Toggle
    assert device.frame_counter == 1000
    assert device.last_seen == TIMESTAMP.timestamp()
    assert device.lqi == 200
    assert device.rssi == -50


def test_relayed_duplicate_does_not_refresh_state(device, events) -> None:
    """The same GPDF forwarded by a second, worse proxy keeps the first reception."""
    device.packet_received(make_packet(1000))
    device.packet_received(
        make_packet(1000, offset=timedelta(seconds=0.5), lqi=3, rssi=-120)
    )

    assert len(events) == 1
    assert device.lqi == 200
    assert device.rssi == -50
    assert device.last_seen == TIMESTAMP.timestamp()


def test_replay_does_not_refresh_state(device, events) -> None:
    """A protected frame failing the freshness check does not indicate liveness."""
    device.packet_received(make_packet(1000))
    device.packet_received(make_packet(500, offset=timedelta(days=3), lqi=1, rssi=-100))

    assert len(events) == 1
    assert device.frame_counter == 1000
    assert device.lqi == 200
    assert device.rssi == -50
    assert device.last_seen == TIMESTAMP.timestamp()


@pytest.mark.parametrize(
    ("offsets", "expected_events"),
    [
        # A repeated MAC sequence number within the 2s window is a duplicate
        ([timedelta(seconds=1)], 1),
        # Outside of it, it is a new (e.g. random sequence number) frame
        ([timedelta(seconds=3)], 2),
        # The window is anchored at the last accepted frame: it does not slide
        # forward on each filtered duplicate
        ([timedelta(seconds=1.5), timedelta(seconds=3)], 2),
    ],
)
def test_unprotected_duplicate_window(device, events, offsets, expected_events) -> None:
    device.packet_received(
        make_packet(
            7,
            security_level=SecurityLevel.NoSecurity,
            security_key_type=SecurityKeyType.NoKey,
        )
    )

    for offset in offsets:
        device.packet_received(
            make_packet(
                7,
                security_level=SecurityLevel.NoSecurity,
                security_key_type=SecurityKeyType.NoKey,
                offset=offset,
            )
        )

    assert len(events) == expected_events


@pytest.mark.parametrize(
    ("security_level", "security_key_type"),
    [
        (SecurityLevel.NoSecurity, SecurityKeyType.NoKey),
        (SecurityLevel.FullFrameCounterAndMIC, SecurityKeyType.GPDGroupKey),
        (SecurityLevel.Encrypted, SecurityKeyType.IndividualKey),
    ],
)
def test_security_mismatch_is_dropped(
    device, events, security_level, security_key_type
) -> None:
    """Frames not matching the commissioned security parameters are silently dropped."""
    commission_security(device)

    device.packet_received(make_packet(5000))
    device.packet_received(
        make_packet(
            42,
            security_level=security_level,
            security_key_type=security_key_type,
            offset=timedelta(seconds=10),
        )
    )

    assert len(events) == 1
    assert device.frame_counter == 5000


def test_unprotected_frame_cannot_reset_frame_counter(device, events) -> None:
    """An unprotected inject must not break the anti-replay counter (A.3.5.2.4.2)."""
    commission_security(device)

    device.packet_received(make_packet(5000))
    device.packet_received(make_packet(4000, offset=timedelta(seconds=10)))
    device.packet_received(
        make_packet(
            42,
            security_level=SecurityLevel.NoSecurity,
            security_key_type=SecurityKeyType.NoKey,
            offset=timedelta(seconds=20),
        )
    )
    device.packet_received(make_packet(4000, offset=timedelta(seconds=30)))

    assert len(events) == 1
    assert device.frame_counter == 5000
