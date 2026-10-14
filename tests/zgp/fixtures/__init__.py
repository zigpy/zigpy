"""Real-world frame fixtures for Green Power tests."""

from __future__ import annotations

from typing import Any, NamedTuple

import zigpy.types as t
from zigpy.zgp.types import DeviceID, GPDCommandID, SecurityLevel


class CapturedFrame(NamedTuple):
    """A protected GPDF as the radio delivers it, without security processing."""

    frame_counter: int
    # Encrypted at SecurityLevel 0b11
    command_id: int
    payload: bytes
    mic: int

    # What the sink delivers once it has verified and decrypted the GPDF
    expected_command_id: GPDCommandID
    expected_command: t.Struct


class CapturedGPD(NamedTuple):
    """A GPD commissioned directly by the coordinator, then pressed."""

    src_id: int
    device_id: DeviceID
    security_level: SecurityLevel

    commissioning_payload: bytes
    # Unprotected, so the frame counter is the MAC sequence number
    commissioning_sequence_number: int

    # The key unwrapped from the commissioning payload with the default TC-LK
    key: bytes
    outgoing_counter: int

    # Further commissioning-derived attributes of the device
    attributes: dict[str, Any]

    frames: list[CapturedFrame]

    # Captured frames that are older than the commissioning
    stale_frames: list[CapturedFrame]
