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
    BJ6716U_OPERATIONAL_FRAME,
    BJ6716U_SOURCE_ID,
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


async def test_real_unprocessed_frame_verified(manager, app) -> None:
    """The radio could not process the captured press, the sink verifies its MIC."""
    await commission(app)

    events = []
    app.devices[IEEE].on_event("gp_command_received", events.append)

    frame = BJ6716U_OPERATIONAL_FRAME
    packet = t.ZigbeeGpPacket(
        application_id=ApplicationID.SrcID,
        src_id=SrcID(BJ6716U_SOURCE_ID),
        command_id=GPDCommandID(frame.command_id),
        frame_counter=t.uint32_t(frame.frame_counter),
        security_level=SecurityLevel.FullFrameCounterAndMIC,
        security_status=SecurityStatus.Unprocessed,
        mic=t.uint32_t.deserialize(frame.mic)[0],
        auto_commissioning=False,
        rx_after_tx=False,
        individual_key=True,
    )

    # The replayed copy fails the freshness check
    app.gp_packet_received(packet)
    app.gp_packet_received(packet)

    assert [e.command_id for e in events] == [GPDCommandID.ShortPress2of2]
    assert app.devices[IEEE].frame_counter == frame.frame_counter
