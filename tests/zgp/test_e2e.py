"""End-to-end tests for Green Power.

Tests the complete GP flow through the real ControllerApplication:
commissioning → command dispatch → decommissioning, verifying that
events fire correctly and state is maintained throughout.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from tests.zgp.fixtures.busch_jaeger_6716u import (
    BJ6716U_COMMISSIONING_PAYLOAD,
    BJ6716U_EXPECTED,
    BJ6716U_OPERATIONAL_FRAMES,
    BJ6716U_SOURCE_ID,
)
from zigpy.profiles import zgp as zgp_profile
import zigpy.types as t
from zigpy.zcl.clusters.greenpower import NotificationOptions, NotificationSchema
from zigpy.zgp.commands import GPNoPayload
from zigpy.zgp.device import GPDevice
from zigpy.zgp.events import CommandReceived, DeviceJoined, DeviceLeft
import zigpy.zgp.types as zgptypes
from zigpy.zgp.types import GP_CLUSTER_ID, GP_ENDPOINT, GPDCommandID, SecurityLevel

# Fake AES-CCM output so the test does not depend on the OOB key the
# Busch-Jaeger switch uses (which zigpy does not know).
_FAKE_DECRYPTED_KEY: bytes = bytes(range(16))


def _build_gp_notification_zcl(
    source_id: int,
    command_id: int,
    payload: bytes = b"",
    frame_counter: int = 1,
    security_level: zgptypes.SecurityLevel = zgptypes.SecurityLevel.NoSecurity,
) -> bytes:
    """Build raw ZCL bytes for a GP Notification (server command 0x00)."""
    options = NotificationOptions(
        application_id=zgptypes.ApplicationID.SrcID,
        also_unicast=0,
        also_derived_group=0,
        also_commissioned_group=0,
        security_level=security_level,
        security_key_type=zgptypes.SecurityKeyType.NoKey,
        appoint_temp_master=0,
        tx_queue_full=0,
        _reserved=0,
    )
    notification = NotificationSchema(
        options=options,
        gpd_id=zgptypes.DeviceID(source_id),
        frame_counter=t.uint32_t(frame_counter),
        command_id=t.uint8_t(command_id),
        payload=t.LVBytes(payload),
    )
    # ZCL: frame_control(cluster-specific) + seq + cmd_id(0x00) + payload
    return bytes([0x01, 0x00, 0x00]) + notification.serialize()


def _make_packet(
    zcl_data: bytes,
    src_nwk: int = 0x1234,
) -> t.ZigbeePacket:
    """Wrap ZCL data in a ZigbeePacket targeting the GP endpoint."""
    return t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(src_nwk)),
        src_ep=t.uint8_t(GP_ENDPOINT),
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
        dst_ep=t.uint8_t(GP_ENDPOINT),
        profile_id=t.uint16_t(zgp_profile.PROFILE_ID),
        cluster_id=t.uint16_t(GP_CLUSTER_ID),
        data=t.SerializableBytes(zcl_data),
    )


async def test_commission_receive_command_decommission(app, gp_events):
    """Full lifecycle: commission a GPD, receive a command, then decommission."""
    gp = app.green_power
    source_id = 0xAABBCCDD

    # --- Step 1: Open commissioning window ---
    await gp.permit_join(time_s=60)
    assert gp.is_commissioning

    # Verify ProxyCommissioningMode was broadcast
    assert app.send_packet.call_count >= 1
    sent = app.send_packet.call_args_list[0][0][0]
    assert sent.cluster_id == GP_CLUSTER_ID
    assert sent.dst_ep == GP_ENDPOINT
    app.send_packet.reset_mock()

    # --- Step 2: Receive commissioning command ---
    # Minimal commissioning: device_id=0x02, options=0x00 (no security)
    commissioning_payload = bytes([0x02, 0x00])
    await gp._process_commissioning(
        source_id=source_id,
        frame_counter=1,
        payload=commissioning_payload,
    )

    # Device should be registered
    dev = gp.get_device(source_id)
    assert dev is not None
    assert dev.device_id == 0x02
    assert dev.source_id == source_id

    joined = [e for _, e in gp_events if isinstance(e, DeviceJoined)]
    assert joined == [DeviceJoined(device_ieee=str(dev.ieee))]

    # GP Pairing should have been sent
    assert app.send_packet.call_count >= 1
    app.send_packet.reset_mock()
    gp_events.clear()

    # --- Step 3: Receive a Toggle command ---
    await gp._dispatch_gp_command(
        source_id=source_id,
        frame_counter=2,
        command_id=GPDCommandID.Toggle,
        payload=b"",
    )

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert commands == [
        CommandReceived(
            device_ieee=str(dev.ieee),
            command_id=GPDCommandID.Toggle,
            payload=GPNoPayload(),
        )
    ]

    # Frame counter should be updated
    assert dev.frame_counter == 2
    gp_events.clear()

    # --- Step 4: Decommission ---
    await gp._process_decommissioning(source_id)

    assert gp.get_device(source_id) is None
    left = [e for _, e in gp_events if isinstance(e, DeviceLeft)]
    assert left == [DeviceLeft(device_ieee=str(dev.ieee))]
    # GP Pairing (remove) should be sent
    assert app.send_packet.call_count >= 1


async def test_commission_with_security(app):
    """Commissioning with unencrypted security key."""
    gp = app.green_power
    source_id = 0x11223344

    await gp.permit_join(time_s=60)
    app.send_packet.reset_mock()

    security_key = bytes(range(16))
    # options: extended present = 0x80
    # extended: Encrypted + key_present = 0x03 | 0x20 = 0x23
    comm_payload = bytes([0x07, 0x80, 0x23]) + security_key

    await gp._process_commissioning(
        source_id=source_id,
        frame_counter=10,
        payload=comm_payload,
    )

    dev = gp.get_device(source_id)
    assert dev is not None
    assert dev.device_id == 0x07
    assert bytes(dev.security_key) == security_key
    assert dev.security_level == SecurityLevel.Encrypted


async def test_commissioning_rejected_when_window_closed(app):
    """Commissioning should be rejected if window is not open."""
    gp = app.green_power
    assert not gp.is_commissioning

    await gp._process_commissioning(
        source_id=0xDEADBEEF,
        frame_counter=1,
        payload=bytes([0x02, 0x00]),
    )

    assert gp.get_device(0xDEADBEEF) is None


async def test_gp_notification_through_app(app, gp_events):
    """GP Notification routed through packet_received to GP manager."""
    gp = app.green_power
    source_id = 0x55667788

    # Pre-register a device
    dev = GPDevice(source_id=source_id, device_id=0x02, frame_counter=0)
    gp.add_device(dev)

    # Build and deliver a GP Notification packet with Toggle command
    zcl_data = _build_gp_notification_zcl(
        source_id=source_id,
        command_id=GPDCommandID.Toggle,
        frame_counter=1,
    )
    packet = _make_packet(zcl_data, src_nwk=0x1234)

    app.packet_received(packet)

    # Let the async task run
    await asyncio.sleep(0.05)

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert commands == [
        CommandReceived(
            device_ieee=str(dev.ieee),
            command_id=GPDCommandID.Toggle,
            payload=GPNoPayload(),
        )
    ]

    # Frame counter should be updated
    assert dev.frame_counter == 1


async def test_gp_packet_from_unknown_proxy(app, gp_events):
    """GP packets from unknown NWK addresses should still be processed."""
    gp = app.green_power
    source_id = 0x99887766

    dev = GPDevice(source_id=source_id, device_id=0x02, frame_counter=0)
    gp.add_device(dev)

    zcl_data = _build_gp_notification_zcl(
        source_id=source_id,
        command_id=GPDCommandID.On,
        frame_counter=1,
    )
    # Use an NWK address not in app.devices - this is the key test
    packet = _make_packet(zcl_data, src_nwk=0x9999)

    app.packet_received(packet)

    await asyncio.sleep(0.05)

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert commands == [
        CommandReceived(
            device_ieee=str(dev.ieee),
            command_id=GPDCommandID.On,
            payload=GPNoPayload(),
        )
    ]


async def test_replay_rejected(app, gp_events):
    """Replayed frames should be silently dropped."""
    gp = app.green_power
    source_id = 0x12345678

    dev = GPDevice(source_id=source_id, device_id=0x02, frame_counter=10)
    gp.add_device(dev)

    # Send with counter=11 (accepted)
    await gp._dispatch_gp_command(source_id, 11, GPDCommandID.Toggle, b"")
    assert dev.frame_counter == 11
    assert any(isinstance(e, CommandReceived) for _, e in gp_events)
    gp_events.clear()

    # Send with counter=11 again (replay - rejected)
    await gp._dispatch_gp_command(source_id, 11, GPDCommandID.Toggle, b"")
    assert not any(isinstance(e, CommandReceived) for _, e in gp_events)

    # Send with counter=5 (old - rejected)
    gp_events.clear()
    await gp._dispatch_gp_command(source_id, 5, GPDCommandID.Toggle, b"")
    assert not any(isinstance(e, CommandReceived) for _, e in gp_events)

    # Counter should still be 11
    assert dev.frame_counter == 11


async def test_sequential_commands(app, gp_events):
    """Sequential commands with increasing counters should all be accepted."""
    gp = app.green_power
    source_id = 0xAAAABBBB

    dev = GPDevice(source_id=source_id, device_id=0x02, frame_counter=0)
    gp.add_device(dev)

    # Send 5 sequential commands
    for i in range(1, 6):
        await gp._dispatch_gp_command(source_id, i, GPDCommandID.Toggle, b"")

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert len(commands) == 5
    assert dev.frame_counter == 5


async def test_proxy_tracked_on_notification(app):
    """Proxy should be tracked when GP Notification is received."""
    gp = app.green_power
    source_id = 0xAABBCCDD
    proxy_nwk = 0x1234

    dev = GPDevice(source_id=source_id, device_id=0x02, frame_counter=0)
    gp.add_device(dev)

    # Simulate notification via the internal handler
    zcl_data = _build_gp_notification_zcl(
        source_id=source_id,
        command_id=GPDCommandID.Toggle,
        frame_counter=1,
    )
    packet = _make_packet(zcl_data, src_nwk=proxy_nwk)
    app.packet_received(packet)

    await asyncio.sleep(0.05)

    # Proxy should be tracked
    proxies = gp.proxy_table.get_proxies_for_device(source_id)
    assert proxy_nwk in proxies


async def test_proxy_table_cleaned_on_decommission(app):
    """Proxy table entries should be removed when device is decommissioned."""
    gp = app.green_power
    source_id = 0x55667788

    dev = GPDevice(source_id=source_id, device_id=0x02, frame_counter=0)
    gp.add_device(dev)

    # Add proxy entries manually
    gp.proxy_table.add_or_update(source_id, 0x1111)
    gp.proxy_table.add_or_update(source_id, 0x2222)
    assert len(gp.proxy_table) == 2

    # Decommission
    await gp._process_decommissioning(source_id)

    assert len(gp.proxy_table) == 0


async def test_commission_then_operational_full_flow(app, gp_events):
    """Commission the switch, then receive a button press."""
    gp = app.green_power

    await gp.permit_join(time_s=60)
    app.send_packet.reset_mock()

    with patch(
        "zigpy.zgp.manager.decrypt_security_key",
        return_value=_FAKE_DECRYPTED_KEY,
    ):
        await gp._process_commissioning(
            source_id=BJ6716U_SOURCE_ID,
            frame_counter=0xFFFFFFFF,
            payload=BJ6716U_COMMISSIONING_PAYLOAD,
        )

    dev = gp.get_device(BJ6716U_SOURCE_ID)
    assert dev is not None
    assert dev.device_id == BJ6716U_EXPECTED.device_id
    assert bytes(dev.security_key) == _FAKE_DECRYPTED_KEY
    assert dev.frame_counter == BJ6716U_EXPECTED.outgoing_counter
    joined = [e for _, e in gp_events if isinstance(e, DeviceJoined)]
    assert joined == [DeviceJoined(device_ieee=str(dev.ieee))]

    # Feed the first captured operational frame (counter 0x1DED, cmd 0x68).
    gp_events.clear()
    frame = BJ6716U_OPERATIONAL_FRAMES[0]
    await gp._dispatch_gp_command(
        source_id=BJ6716U_SOURCE_ID,
        frame_counter=frame.frame_counter,
        command_id=frame.command_id,
        payload=b"",
    )

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert len(commands) == 1
    assert commands[0].device_ieee == str(dev.ieee)
    assert commands[0].command_id == frame.command_id
    assert commands[0].payload == GPNoPayload()
    assert dev.frame_counter == frame.frame_counter


async def test_command_0x68_routing(app, gp_events):
    """Every captured 0x68 frame reaches listeners in order."""
    gp = app.green_power

    dev = GPDevice(
        source_id=BJ6716U_SOURCE_ID,
        device_id=BJ6716U_EXPECTED.device_id,
        frame_counter=BJ6716U_EXPECTED.outgoing_counter,
    )
    gp.add_device(dev)

    for frame in BJ6716U_OPERATIONAL_FRAMES:
        await gp._dispatch_gp_command(
            source_id=BJ6716U_SOURCE_ID,
            frame_counter=frame.frame_counter,
            command_id=frame.command_id,
            payload=b"",
        )

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert [int(c.command_id) for c in commands] == [0x68] * len(
        BJ6716U_OPERATIONAL_FRAMES
    )
    assert dev.frame_counter == BJ6716U_OPERATIONAL_FRAMES[-1].frame_counter
