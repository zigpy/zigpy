"""End-to-end tests for Green Power.

Tests the complete GP flow through the real ControllerApplication:
commissioning → command dispatch → decommissioning, with every GPDF tunneled by a
proxy as a GP Notification.
"""

from __future__ import annotations

from unittest.mock import call

from tests.zgp.conftest import wait_for_gp_processing
from tests.zgp.test_tunneling import (
    NOTIFICATION_ID,
    make_notification_options,
    make_tunnel_packet,
)
import zigpy.types as t
from zigpy.zcl.clusters.greenpower import NotificationSchema
from zigpy.zgp.commands import GPNoPayload
from zigpy.zgp.types import (
    GPDCommandID,
    GPDCommandPayload,
    GPLinkQuality,
    GPPGPDLink,
    SecurityKeyType,
    SecurityLevel,
)
from zigpy.zgp.util import synthetic_ieee

SRC = t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234)
DST = t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000)


def make_notification_packet(
    source_id: int,
    command_id: GPDCommandID,
    payload: bytes = b"",
    frame_counter: int = 1,
) -> t.ZigbeePacket:
    command = NotificationSchema(
        options=make_notification_options(
            security_level=SecurityLevel.NoSecurity,
            security_key_type=SecurityKeyType.NoKey,
        ),
        gpd_id=source_id,
        frame_counter=frame_counter,
        command_id=command_id,
        payload=GPDCommandPayload(payload),
        gpp_short_addr=0x1234,
        gpp_gpd_link=GPPGPDLink(rssi=20, link_quality=GPLinkQuality.High),
    )

    return make_tunnel_packet(NOTIFICATION_ID, command.serialize(), src=SRC, dst=DST)


async def test_commission_receive_command_decommission(app, manager):
    """Full lifecycle: commission a GPD, receive a command, then decommission."""
    source_id = 0xAABBCCDD
    ieee = synthetic_ieee(source_id)

    # --- Step 1: Open commissioning window ---
    await app.permit_gp(time_s=60)
    assert manager.is_commissioning
    app.send_packet.reset_mock()

    # --- Step 2: Receive commissioning command ---
    # Minimal commissioning: device_id=0x02, options=0x00 (no security)
    app.packet_received(
        make_notification_packet(
            source_id, GPDCommandID.CommissioningRequest, bytes([0x02, 0x00])
        )
    )
    await wait_for_gp_processing()

    dev = app.devices[ieee]
    assert dev.device_id == 0x02
    assert app.device_initialized.mock_calls == [call(dev)]

    # Device_annce for the alias and GP Pairing should have been sent
    assert app.send_packet.call_count == 2
    app.send_packet.reset_mock()

    # --- Step 3: Receive a Toggle command ---
    events = []
    dev.on_event("gp_command_received", events.append)

    app.packet_received(
        make_notification_packet(source_id, GPDCommandID.Toggle, frame_counter=2)
    )

    assert [(e.command_id, e.command) for e in events] == [
        (GPDCommandID.Toggle, GPNoPayload())
    ]
    assert dev.frame_counter == 2

    # --- Step 4: Decommission ---
    app.packet_received(
        make_notification_packet(
            source_id, GPDCommandID.DecommissioningRequest, frame_counter=3
        )
    )
    await wait_for_gp_processing()

    assert ieee not in app.devices
    assert call("device_removed", dev) in app.listener_event.mock_calls
    # GP Pairing (remove) should be sent
    assert app.send_packet.call_count == 1


async def test_permit_gp(app, manager):
    """permit_gp opens the GP commissioning window, permit_gp(0) closes it."""
    await app.permit_gp(time_s=120)
    assert manager.is_commissioning

    await app.permit_gp(time_s=0)
    assert not manager.is_commissioning
