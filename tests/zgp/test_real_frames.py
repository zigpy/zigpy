"""Commissioning and operational tests driven by frames from a real Busch-Jaeger 6716 U.

These pin behaviour against actual hardware. The frames were captured below the
bellows EZSP layer and are fed in as the `ZigbeeGpPacket`s a radio library delivers.
"""

from __future__ import annotations

from tests.zgp.conftest import wait_for_gp_processing
from tests.zgp.fixtures.busch_jaeger_6716u import (
    BJ6716U_COMMISSIONING_PAYLOAD,
    BJ6716U_DECRYPTED_KEY,
    BJ6716U_EXPECTED,
    BJ6716U_OPERATIONAL_FRAMES,
    BJ6716U_SOURCE_ID,
    OperationalFrame,
)
import zigpy.types as t
from zigpy.zgp.types import (
    ApplicationID,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SrcID,
)
from zigpy.zgp.util import synthetic_ieee

IEEE = synthetic_ieee(BJ6716U_SOURCE_ID)


async def commission(app) -> None:
    await app.green_power.permit_join(time_s=60)

    app.gp_packet_received(
        t.ZigbeeGpPacket(
            application_id=ApplicationID.SrcID,
            src_id=SrcID(BJ6716U_SOURCE_ID),
            command_id=GPDCommandID.CommissioningRequest,
            payload=t.SerializableBytes(BJ6716U_COMMISSIONING_PAYLOAD),
            frame_counter=t.uint32_t(0xFFFFFFFF),
            security_level=SecurityLevel.NoSecurity,
            security_key_type=SecurityKeyType.NoKey,
            security_status=SecurityStatus.NoSecurity,
        )
    )

    await wait_for_gp_processing()


def operational_packet(frame: OperationalFrame) -> t.ZigbeeGpPacket:
    return t.ZigbeeGpPacket(
        application_id=ApplicationID.SrcID,
        src_id=SrcID(BJ6716U_SOURCE_ID),
        command_id=GPDCommandID(frame.command_id),
        frame_counter=t.uint32_t(frame.frame_counter),
        security_level=SecurityLevel.FullFrameCounterAndMIC,
        security_key_type=SecurityKeyType.IndividualKey,
        security_status=SecurityStatus.SecuritySuccess,
    )


# -- Commissioning -----------------------------------------------------------


async def test_real_commissioning_succeeds(manager, app) -> None:
    """The captured 0xE0 frame unwraps its key and registers the device."""
    await commission(app)

    device = app.devices[IEEE]
    assert device.src_id == BJ6716U_SOURCE_ID
    assert device.device_id == BJ6716U_EXPECTED.device_id
    assert device.security_key == t.KeyData(BJ6716U_DECRYPTED_KEY)
    assert device.security_level == SecurityLevel.FullFrameCounterAndMIC
    assert device.security_key_type == SecurityKeyType.IndividualKey
    # The advertised OutgoingCounter wins over the notification frame counter.
    assert device.frame_counter == BJ6716U_EXPECTED.outgoing_counter
    assert device.commands == BJ6716U_EXPECTED.gpd_commands


# -- Operational frame handling ---------------------------------------------


async def test_accepts_monotonic_sequence(manager, app) -> None:
    """Four successive counters all produce a command event."""
    await commission(app)

    events = []
    app.devices[IEEE].on_event("gp_command_received", events.append)

    for frame in BJ6716U_OPERATIONAL_FRAMES:
        app.gp_packet_received(operational_packet(frame))

    assert [e.command_id for e in events] == [
        frame.command_id for frame in BJ6716U_OPERATIONAL_FRAMES
    ]
    assert (
        app.devices[IEEE].frame_counter == BJ6716U_OPERATIONAL_FRAMES[-1].frame_counter
    )


async def test_rejects_replayed_and_older_counters(manager, app) -> None:
    """Frames at or below the last accepted counter are dropped."""
    await commission(app)

    events = []
    app.devices[IEEE].on_event("gp_command_received", events.append)

    recent = BJ6716U_OPERATIONAL_FRAMES[-1]
    older = BJ6716U_OPERATIONAL_FRAMES[0]

    for frame in (recent, recent, older):
        app.gp_packet_received(operational_packet(frame))

    assert len(events) == 1
    assert app.devices[IEEE].frame_counter == recent.frame_counter
