"""End-to-end tests for Green Power.

Tests the complete GP flow through the real ControllerApplication:
commissioning → command dispatch → decommissioning, with every GPDF tunneled by a
proxy: in a GP Commissioning Notification while in commissioning mode, then in GP
Notifications once paired.
"""

from __future__ import annotations

from unittest.mock import call

from tests.zgp.conftest import (
    COMMISSIONING_NOTIFICATION_ID,
    NOTIFICATION_ID,
    commissioning_payload,
    make_commissioning_options,
    make_notification_options,
    make_tunnel_packet,
    wait_for_gp_processing,
)
import zigpy.types as t
from zigpy.zcl.clusters.greenpower import (
    CommissioningNotificationSchema,
    NotificationSchema,
)
from zigpy.zgp.commands import GPNoPayload
from zigpy.zgp.types import (
    DeviceID,
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


def make_commissioning_notification_packet(
    source_id: int, payload: bytes, frame_counter: int = 1
) -> t.ZigbeePacket:
    command = CommissioningNotificationSchema(
        options=make_commissioning_options(),
        gpd_id=source_id,
        frame_counter=frame_counter,
        command_id=GPDCommandID.CommissioningRequest,
        payload=GPDCommandPayload(payload),
        gpp_short_addr=0x1234,
        gpp_gpd_link=GPPGPDLink(rssi=20, link_quality=GPLinkQuality.High),
    )

    return make_tunnel_packet(
        COMMISSIONING_NOTIFICATION_ID, command.serialize(), src=SRC, dst=DST
    )


async def test_commission_receive_command_decommission(app, manager):
    """Full lifecycle: commission a GPD, receive a command, then decommission."""
    source_id = 0xAABBCCDD
    ieee = synthetic_ieee(source_id)

    # --- Step 1: Open commissioning window ---
    await app.permit_gp(time_s=60)
    assert manager.is_commissioning
    app.send_packet.reset_mock()

    # --- Step 2: Receive commissioning command ---
    # Minimal commissioning of an unprotected On/Off switch
    app.packet_received(
        make_commissioning_notification_packet(
            source_id, commissioning_payload(DeviceID.OnOffSwitch)
        )
    )
    await wait_for_gp_processing()

    dev = app.devices[ieee]
    assert dev.device_id == DeviceID.OnOffSwitch
    assert app.device_initialized.mock_calls == [call(dev)]

    # Device_annce for the alias and GP Pairing should have been sent
    assert len(app.send_packet.mock_calls) == 2
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
    assert len(app.send_packet.mock_calls) == 1
