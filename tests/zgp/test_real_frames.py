"""Commissioning and operational tests driven by frames captured from real GPDs.

The coordinator's radio received every GPDF directly, without the security processing
it lacks the keys for, so the sink has to verify (and decrypt) each one itself.
"""

from __future__ import annotations

import pytest

from tests.zgp.conftest import wait_for_gp_processing
from tests.zgp.fixtures import CapturedFrame, CapturedGPD
from tests.zgp.fixtures.enocean_ptm215z import PTM215Z
from tests.zgp.fixtures.enocean_ptm216z import PTM216Z
from tests.zgp.fixtures.moes_3_gang import MOES_3_GANG
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

pytestmark = pytest.mark.parametrize(
    "gpd",
    [
        pytest.param(PTM215Z, id="enocean_ptm215z"),
        pytest.param(PTM216Z, id="enocean_ptm216z"),
        pytest.param(MOES_3_GANG, id="moes_3_gang"),
    ],
)


async def commission(app, gpd: CapturedGPD) -> None:
    await app.green_power.permit_join(time_s=60)

    app.gp_packet_received(
        t.ZigbeeGpPacket(
            application_id=ApplicationID.SrcID,
            src_id=SrcID(gpd.src_id),
            command_id=GPDCommandID.CommissioningRequest,
            payload=t.SerializableBytes(gpd.commissioning_payload),
            frame_counter=t.uint32_t(gpd.commissioning_sequence_number),
            security_level=SecurityLevel.NoSecurity,
            security_status=SecurityStatus.NoSecurity,
        )
    )
    await wait_for_gp_processing(app)


def unprocessed_packet(gpd: CapturedGPD, frame: CapturedFrame) -> t.ZigbeeGpPacket:
    return t.ZigbeeGpPacket(
        application_id=ApplicationID.SrcID,
        src_id=SrcID(gpd.src_id),
        command_id=GPDCommandID(frame.command_id),
        payload=t.SerializableBytes(frame.payload),
        frame_counter=t.uint32_t(frame.frame_counter),
        security_level=gpd.security_level,
        security_status=SecurityStatus.Unprocessed,
        mic=t.uint32_t(frame.mic),
        auto_commissioning=False,
        rx_after_tx=False,
        individual_key=True,
    )


async def test_commissioning(manager, app, gpd) -> None:
    """The commissioning payload's key is unwrapped and the device registered."""
    await commission(app, gpd)

    device = app.devices[synthetic_ieee(gpd.src_id)]
    assert device.device_id == gpd.device_id
    assert device.security_level == gpd.security_level
    assert device.security_key_type == SecurityKeyType.IndividualKey
    assert device.security_key == t.KeyData(gpd.key)
    assert device.frame_counter == gpd.outgoing_counter

    for name, value in gpd.attributes.items():
        assert getattr(device, name) == value


async def test_frames(manager, app, gpd) -> None:
    """Every captured GPDF verifies with the unwrapped key and is delivered."""
    await commission(app, gpd)

    device = app.devices[synthetic_ieee(gpd.src_id)]
    events = []
    device.on_event("gp_command_received", events.append)

    for frame in gpd.frames:
        app.gp_packet_received(unprocessed_packet(gpd, frame))

    assert [(e.command_id, e.command) for e in events] == [
        (frame.expected_command_id, frame.expected_command) for frame in gpd.frames
    ]
    assert device.frame_counter == gpd.frames[-1].frame_counter


async def test_replayed_frames_dropped(manager, app, gpd) -> None:
    """A repeated GPDF and GPDFs older than the commissioning fail the freshness check."""
    await commission(app, gpd)
    app.gp_packet_received(unprocessed_packet(gpd, gpd.frames[0]))

    device = app.devices[synthetic_ieee(gpd.src_id)]
    events = []
    device.on_event("gp_command_received", events.append)

    for frame in [gpd.frames[0], *gpd.stale_frames]:
        app.gp_packet_received(unprocessed_packet(gpd, frame))

    assert events == []
    assert device.frame_counter == gpd.frames[0].frame_counter
