"""Green Power helper functions."""

from __future__ import annotations

from typing import Any

import zigpy.types as t
from zigpy.zgp.types import (
    GP_PROTOCOL_VERSION,
    ApplicationID,
    CommunicationDirection,
    ExtendedNWKFrameControl,
    FrameType,
    GPDCommandID,
    NWKFrameControl,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SrcID,
)

# Marks a synthetic EUI64 built from a 32-bit GPD SrcID
GP_SYNTHETIC_IEEE_MARKER = b"\x00\x00\x00\x00"


def synthetic_ieee(src_id: int) -> t.EUI64:
    """Build the synthetic EUI64 under which a SrcID-addressed GPD is registered."""
    return t.EUI64(int(src_id).to_bytes(4, "little") + GP_SYNTHETIC_IEEE_MARKER)


def derive_alias(gpd_id: int | t.EUI64) -> t.NWK:
    """Derive the alias NWK source address from a GPD ID (spec A.3.6.3.3.1).

    The alias is the NWK short address that proxies use as the source address when
    sending frames on behalf of a GPD. The GPD ID is the SrcID for ApplicationID
    0b000 and the GPD IEEE address for 0b010; the GPD endpoint is never used.
    """
    if isinstance(gpd_id, t.EUI64):
        gpd_id = int.from_bytes(gpd_id.serialize(), "little")

    # Reserved addresses are 0x0000 (the coordinator) and >0xFFF7 (broadcasts)
    alias = gpd_id & 0xFFFF

    if 0x0000 < alias <= 0xFFF7:
        return t.NWK(alias)

    xored = alias ^ ((gpd_id >> 16) & 0xFFFF)

    if 0x0000 < xored <= 0xFFF7:
        return t.NWK(xored)

    if alias == 0x0000:
        return t.NWK(0x0007)

    return t.NWK(alias - 0x0008)


def parse_gpdf(data: bytes, **kwargs: Any) -> t.ZigbeeGpPacket:
    """Parse the NWK frame of a GPDF, from its frame control up to and including the MIC.

    The MAC header is not part of it, so the radio supplies what it carries through
    `kwargs`: the IEEE address of an IEEE-addressed GPD and, for an unprotected GPDF,
    the MAC sequence number as `frame_counter`. A protected GPDF is returned
    unprocessed, with its MIC, for the sink to verify and decrypt.
    """
    frame_control, data = NWKFrameControl.deserialize(data)

    if frame_control.protocol_version != GP_PROTOCOL_VERSION:
        raise ValueError(f"Unsupported protocol version: {frame_control}")

    if frame_control.extended:
        extended, data = ExtendedNWKFrameControl.deserialize(data)
    else:
        # The defaults to be used on reception (A.1.4.1.3)
        extended = ExtendedNWKFrameControl(
            application_id=ApplicationID.SrcID,
            security_level=SecurityLevel.NoSecurity,
            security_key=0,
            rx_after_tx=0,
            direction=CommunicationDirection.GPDtoGPP,
        )

    if extended.direction is CommunicationDirection.GPPtoGPD:
        # Sent by another proxy or sink to a GPD (A.3.9.1 steps 11 and 16)
        raise ValueError(f"GPDF is sent to a GPD, not by one: {extended}")

    src_id: SrcID | None = None
    endpoint: t.uint8_t | None = None

    if extended.application_id is ApplicationID.SrcID:
        # A Maintenance GPDF only carries the SrcID along with the Extended NWK Frame
        # Control (A.1.4.1.4), 0x00000000 is unspecified
        if frame_control.frame_type is FrameType.DataFrame or frame_control.extended:
            src_id, data = SrcID.deserialize(data)
        else:
            src_id = SrcID(0x00000000)
    elif extended.application_id is ApplicationID.IEEE:
        endpoint, data = t.uint8_t.deserialize(data)
    else:
        raise ValueError(f"Unsupported ApplicationID: {extended}")

    if extended.security_level is SecurityLevel.NoSecurity:
        frame_counter = None
        mic = None
        security_status = SecurityStatus.NoSecurity
        security_key_type: SecurityKeyType | None = SecurityKeyType.NoKey
    elif extended.security_level is SecurityLevel.Reserved:
        # No processing is defined for it, the GPDF is dropped (A.1.5.2.2)
        raise ValueError(f"Reserved security level: {extended}")
    else:
        frame_counter, data = t.uint32_t.deserialize(data)

        # The MIC trails the GPD command and its payload (A.1.4.1.8)
        if len(data) < 5:
            raise ValueError("GPDF is too short for a command ID and MIC")

        mic, _ = t.uint32_t.deserialize(data[-4:])
        data = data[:-4]
        security_status = SecurityStatus.Unprocessed
        # Only the SecurityKey sub-field is known until the sink finds the key
        security_key_type = None

    command_id, data = GPDCommandID.deserialize(data)

    return t.ZigbeeGpPacket(
        **{
            "application_id": extended.application_id,
            "src_id": src_id,
            "endpoint": endpoint,
            "command_id": command_id,
            "payload": t.SerializableBytes(data),
            "frame_counter": frame_counter,
            "security_level": extended.security_level,
            "security_key_type": security_key_type,
            "security_status": security_status,
            "mic": mic,
            "auto_commissioning": bool(frame_control.auto_commissioning),
            "rx_after_tx": bool(extended.rx_after_tx),
            "individual_key": (
                bool(extended.security_key)
                if security_status is SecurityStatus.Unprocessed
                else None
            ),
            **kwargs,
        }
    )
