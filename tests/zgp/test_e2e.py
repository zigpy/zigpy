"""End-to-end tests for Green Power.

Tests the complete GP flow through the real ControllerApplication:
commissioning → command dispatch → decommissioning, verifying that
events fire correctly and state is maintained throughout.
"""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, Mock

import pytest

import zigpy.types as t
from zigpy.zcl.clusters.greenpower import (
    NotificationOptions,
    NotificationSchema,
)
import zigpy.zgp.types as zgptypes
from zigpy.zgp.device import GPDevice, source_id_to_ieee
from zigpy.zgp.manager import GreenPowerManager
from zigpy.zgp.types import (
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    GPDCommandID,
    SecurityLevel,
)

from tests.conftest import make_app


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
        profile_id=t.uint16_t(0xA1E0),
        cluster_id=t.uint16_t(GP_CLUSTER_ID),
        data=t.SerializableBytes(zcl_data),
    )


@pytest.fixture
def app():
    """Real ControllerApplication with GP manager."""
    return make_app({})


class TestFullCommissioningFlow:
    """Test complete commissioning → command → decommissioning lifecycle."""

    @pytest.mark.asyncio
    async def test_commission_receive_command_decommission(self, app) -> None:
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
        assert dev.model_identifier == "GreenPower_2"

        # gp_device_joined event should have fired
        app.listener_event.assert_any_call("gp_device_joined", dev)

        # GP Pairing should have been sent
        assert app.send_packet.call_count >= 1
        app.send_packet.reset_mock()
        app.listener_event.reset_mock()

        # --- Step 3: Receive a Toggle command ---
        await gp._dispatch_gp_command(
            source_id=source_id,
            frame_counter=2,
            command_id=GPDCommandID.Toggle,
            payload=b"",
        )

        app.listener_event.assert_called_with(
            "gp_command_received",
            dev,
            GPDCommandID.Toggle,
            b"",
        )

        # Frame counter should be updated
        assert dev.frame_counter == 2
        app.listener_event.reset_mock()

        # --- Step 4: Decommission ---
        await gp._process_decommissioning(source_id)

        assert gp.get_device(source_id) is None
        app.listener_event.assert_any_call("gp_device_left", dev)
        # GP Pairing (remove) should be sent
        assert app.send_packet.call_count >= 1

    @pytest.mark.asyncio
    async def test_commission_with_security(self, app) -> None:
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
        assert dev.security_key == security_key
        assert dev.security_level == SecurityLevel.Encrypted
        assert dev.model_identifier == "GreenPower_7"

    @pytest.mark.asyncio
    async def test_commissioning_rejected_when_window_closed(self, app) -> None:
        """Commissioning should be rejected if window is not open."""
        gp = app.green_power
        assert not gp.is_commissioning

        await gp._process_commissioning(
            source_id=0xDEADBEEF,
            frame_counter=1,
            payload=bytes([0x02, 0x00]),
        )

        assert gp.get_device(0xDEADBEEF) is None


class TestPacketReceivedE2E:
    """Test GP packets flowing through ControllerApplication.packet_received()."""

    @pytest.mark.asyncio
    async def test_gp_notification_through_app(self, app) -> None:
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
        import asyncio
        await asyncio.sleep(0.05)

        # gp_command_received should have been fired
        app.listener_event.assert_any_call(
            "gp_command_received",
            dev,
            GPDCommandID.Toggle,
            b"",
        )

        # Frame counter should be updated
        assert dev.frame_counter == 1

    @pytest.mark.asyncio
    async def test_gp_packet_from_unknown_proxy(self, app) -> None:
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

        import asyncio
        await asyncio.sleep(0.05)

        app.listener_event.assert_any_call(
            "gp_command_received",
            dev,
            GPDCommandID.On,
            b"",
        )


class TestReplayProtectionE2E:
    """Test replay protection across the full stack."""

    @pytest.mark.asyncio
    async def test_replay_rejected(self, app) -> None:
        """Replayed frames should be silently dropped."""
        gp = app.green_power
        source_id = 0x12345678

        dev = GPDevice(source_id=source_id, device_id=0x02, frame_counter=10)
        gp.add_device(dev)

        # Send with counter=11 (accepted)
        await gp._dispatch_gp_command(source_id, 11, GPDCommandID.Toggle, b"")
        assert dev.frame_counter == 11
        app.listener_event.assert_called()
        app.listener_event.reset_mock()

        # Send with counter=11 again (replay - rejected)
        await gp._dispatch_gp_command(source_id, 11, GPDCommandID.Toggle, b"")
        # listener should NOT have been called for gp_command_received
        for call in app.listener_event.call_args_list:
            assert call[0][0] != "gp_command_received"

        # Send with counter=5 (old - rejected)
        app.listener_event.reset_mock()
        await gp._dispatch_gp_command(source_id, 5, GPDCommandID.Toggle, b"")
        for call in app.listener_event.call_args_list:
            assert call[0][0] != "gp_command_received"

        # Counter should still be 11
        assert dev.frame_counter == 11

    @pytest.mark.asyncio
    async def test_sequential_commands(self, app) -> None:
        """Sequential commands with increasing counters should all be accepted."""
        gp = app.green_power
        source_id = 0xAAAABBBB

        dev = GPDevice(source_id=source_id, device_id=0x02, frame_counter=0)
        gp.add_device(dev)

        commands_received = []

        def track_event(event_name, *args):
            if event_name == "gp_command_received":
                commands_received.append(args)

        app.listener_event.side_effect = track_event

        # Send 5 sequential commands
        for i in range(1, 6):
            await gp._dispatch_gp_command(
                source_id, i, GPDCommandID.Toggle, b""
            )

        assert len(commands_received) == 5
        assert dev.frame_counter == 5


class TestProxyTableE2E:
    """Test proxy table tracking through the full flow."""

    @pytest.mark.asyncio
    async def test_proxy_tracked_on_notification(self, app) -> None:
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

        import asyncio
        await asyncio.sleep(0.05)

        # Proxy should be tracked
        proxies = gp.proxy_table.get_proxies_for_device(source_id)
        assert proxy_nwk in proxies

    @pytest.mark.asyncio
    async def test_proxy_table_cleaned_on_decommission(self, app) -> None:
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


class TestPersistenceE2E:
    """Test device persistence across save/load cycle."""

    def test_persist_and_restore(self, app) -> None:
        """Devices should survive a save/load cycle."""
        gp = app.green_power

        # Commission two devices
        dev1 = GPDevice(
            source_id=0x11111111,
            device_id=0x02,
            security_key=bytes(range(16)),
            security_level=SecurityLevel.Encrypted,
            frame_counter=42,
            gpd_commands=[0x20, 0x21, 0x22],
        )
        dev2 = GPDevice(
            source_id=0x22222222,
            device_id=0x07,
            frame_counter=100,
        )
        gp.add_device(dev1)
        gp.add_device(dev2)

        # Save
        data = gp.get_devices_data()
        assert len(data) == 2

        # Create new manager (simulating restart)
        app2 = make_app({})
        gp2 = app2.green_power

        # Load
        gp2.load_devices(data)

        # Verify
        restored1 = gp2.get_device(0x11111111)
        assert restored1 is not None
        assert restored1.device_id == 0x02
        assert restored1.security_key == bytes(range(16))
        assert restored1.security_level == SecurityLevel.Encrypted
        assert restored1.frame_counter == 42
        assert restored1.gpd_commands == [0x20, 0x21, 0x22]

        restored2 = gp2.get_device(0x22222222)
        assert restored2 is not None
        assert restored2.device_id == 0x07
        assert restored2.frame_counter == 100
