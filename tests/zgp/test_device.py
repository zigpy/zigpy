"""Tests for Green Power device packet handling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from zigpy.device import GreenPowerDevice
import zigpy.types as t
from zigpy.zgp.commands import GPGenericSwitchConfiguration, GPStepPayload
from zigpy.zgp.types import (
    ApplicationID,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SrcID,
    SwitchType,
)
from zigpy.zgp.util import derive_alias

TIMESTAMP = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)
IEEE = t.EUI64.convert("11:22:33:44:55:66:77:88")


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
    command_id: GPDCommandID = GPDCommandID.Toggle,
    payload: bytes = b"",
    security_level: SecurityLevel = SecurityLevel.Encrypted,
    security_key_type: SecurityKeyType = SecurityKeyType.GPDGroupKey,
    security_status: SecurityStatus | None = None,
    offset: timedelta = timedelta(0),
    lqi: int = 200,
    rssi: int = -50,
    application_id: ApplicationID = ApplicationID.SrcID,
    endpoint: int | None = None,
) -> t.ZigbeeGpPacket:
    return t.ZigbeeGpPacket(
        timestamp=TIMESTAMP + offset,
        application_id=application_id,
        src_id=SrcID(0x12345678) if application_id is ApplicationID.SrcID else None,
        ieee=IEEE if application_id is ApplicationID.IEEE else None,
        endpoint=None if endpoint is None else t.uint8_t(endpoint),
        command_id=command_id,
        payload=t.SerializableBytes(payload),
        frame_counter=t.uint32_t(frame_counter),
        security_level=security_level,
        security_key_type=security_key_type,
        security_status=security_status,
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


def test_ieee_addressed_gpd() -> None:
    device = GreenPowerDevice(None, application_id=ApplicationID.IEEE, ieee=IEEE)

    assert device.ieee == IEEE
    assert device.nwk == derive_alias(IEEE)
    assert device.src_id is None
    assert device.name == f"GreenPowerDevice {IEEE}"


def test_device_properties(device) -> None:
    assert device.src_id == 0x12345678
    assert device.nwk == derive_alias(0x12345678)
    assert device.name == "GreenPowerDevice 0x12345678"
    assert device.is_initialized
    assert device.manufacturer_id is None

    device.gpd_manufacturer_id = t.uint16_t(0x1234)
    device.switch_configuration = GPGenericSwitchConfiguration(
        num_contacts=2, switch_type=SwitchType.Rocker, _reserved=0
    )
    device.mac_seq_num_capability = True

    assert device.manufacturer_id == 0x1234
    assert device.get_signature() == {
        "application_id": ApplicationID.SrcID,
        "src_id": 0x12345678,
        "device_id": None,
        "manufacturer_id": 0x1234,
        "model_id": None,
        "commands": [],
        "server_cluster_ids": [],
        "client_cluster_ids": [],
        "switch_configuration": GPGenericSwitchConfiguration(0x22),
        "mac_seq_num_capability": True,
    }


def test_packet_received(device, events) -> None:
    device.packet_received(make_packet(1000))

    assert len(events) == 1
    assert events[0].device_ieee == str(device.ieee)
    assert events[0].command_id == GPDCommandID.Toggle
    assert device.frame_counter == 1000
    assert device.last_seen == TIMESTAMP.timestamp()
    assert device.lqi == 200
    assert device.rssi == -50


def test_packet_received_parses_command(device, events) -> None:
    device.packet_received(
        make_packet(1, command_id=GPDCommandID.StepUp, payload=b"\x05\x0a\x00")
    )

    assert len(events) == 1
    assert events[0].command == GPStepPayload(step_size=5, transition_time=10)


def test_packet_received_unparseable_payload(device, events) -> None:
    """A GPDF whose payload fails to parse is still delivered, without a command."""
    device.packet_received(make_packet(1, command_id=GPDCommandID.StepUp, payload=b""))

    assert len(events) == 1
    assert events[0].command is None


def test_packet_received_command_without_schema(device, events) -> None:
    device.packet_received(
        make_packet(1, command_id=GPDCommandID.ApplicationDescription, payload=b"\x01")
    )

    assert len(events) == 1
    assert events[0].command is None


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
            6000,
            security_level=security_level,
            security_key_type=security_key_type,
            offset=timedelta(seconds=10),
        )
    )

    assert len(events) == 1
    assert device.frame_counter == 5000


def test_undecrypted_frame_is_dropped(device, events) -> None:
    """An encrypted GPDF the radio did not decrypt has no readable command ID."""
    commission_security(device)

    device.packet_received(make_packet(5000))
    device.packet_received(
        make_packet(
            6000,
            security_status=SecurityStatus.Unprocessed,
            offset=timedelta(seconds=10),
        )
    )

    assert len(events) == 1
    assert device.frame_counter == 5000


def test_unprotected_frame_cannot_reset_frame_counter(device, events) -> None:
    """An unprotected inject must not break the anti-replay counter (A.3.5.2.4)."""
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


@pytest.mark.parametrize("endpoint", [3, 5, 0x00, 0xFF])
def test_ieee_frame_endpoint_passthrough(endpoint) -> None:
    """IEEE addressing delivers the frame's endpoint, wildcards included."""
    device = GreenPowerDevice(None, application_id=ApplicationID.IEEE, ieee=IEEE)

    events = []
    device.on_event("gp_command_received", events.append)

    device.packet_received(
        make_packet(1000, application_id=ApplicationID.IEEE, endpoint=endpoint)
    )

    assert len(events) == 1
    assert events[0].endpoint_id == endpoint
