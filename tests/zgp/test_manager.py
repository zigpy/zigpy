"""Tests for Green Power Manager."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

import zigpy.types as t

from zigpy.zgp.device import GPDevice
from zigpy.zgp.manager import GreenPowerManager
from zigpy.zgp.types import (
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
)


@pytest.fixture
def mock_app() -> MagicMock:
    """Create a mock ControllerApplication."""
    app = MagicMock()
    app.state.node_info.ieee = t.EUI64.convert("00:11:22:33:44:55:66:77")
    app.state.node_info.nwk = t.NWK(0x0000)
    app.send_packet = AsyncMock()
    app.listener_event = Mock()
    app.create_task = Mock(side_effect=lambda coro, name=None: asyncio.ensure_future(coro))
    return app


@pytest.fixture
def manager(mock_app: MagicMock) -> GreenPowerManager:
    """Create a GreenPowerManager with mock app."""
    return GreenPowerManager(mock_app)


def _make_gp_notification_packet(
    source_id: int,
    command_id: int,
    payload: bytes = b"",
    frame_counter: int = 1,
    proxy_nwk: int = 0x1234,
) -> t.ZigbeePacket:
    """Build a ZigbeePacket containing a GP Notification.

    Constructs a minimal ZCL cluster-specific server command (0x00)
    wrapping a GP Notification with the given GPD command.
    """
    from zigpy.zcl.clusters.greenpower import (
        NotificationOptions,
        NotificationSchema,
    )
    import zigpy.zgp.types as zgptypes

    options = NotificationOptions(
        application_id=zgptypes.ApplicationID.SrcID,
        also_unicast=0,
        also_derived_group=0,
        also_commissioned_group=0,
        security_level=zgptypes.SecurityLevel.NoSecurity,
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

    # ZCL frame: frame_control + seq_num + command_id(0x00) + notification payload
    zcl_frame = bytes([0x01, 0x00, 0x00]) + notification.serialize()

    return t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(proxy_nwk)),
        src_ep=t.uint8_t(GP_ENDPOINT),
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
        dst_ep=t.uint8_t(GP_ENDPOINT),
        profile_id=t.uint16_t(0xA1E0),
        cluster_id=t.uint16_t(GP_CLUSTER_ID),
        data=t.SerializableBytes(zcl_frame),
    )


class TestGreenPowerManagerBasics:
    """Basic manager tests."""

    def test_creation(self, manager: GreenPowerManager) -> None:
        assert manager.devices == {}
        assert not manager.is_commissioning

    def test_add_device(self, manager: GreenPowerManager) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02)
        manager.add_device(dev)
        assert manager.get_device(0x12345678) is dev
        assert len(manager.devices) == 1

    def test_remove_device(self, manager: GreenPowerManager) -> None:
        dev = GPDevice(source_id=0x12345678, device_id=0x02)
        manager.add_device(dev)
        removed = manager.remove_device(0x12345678)
        assert removed is dev
        assert manager.get_device(0x12345678) is None

    def test_remove_nonexistent_device(self, manager: GreenPowerManager) -> None:
        removed = manager.remove_device(0xDEADBEEF)
        assert removed is None

    def test_get_device_nonexistent(self, manager: GreenPowerManager) -> None:
        assert manager.get_device(0xDEADBEEF) is None


class TestHandlePacket:
    """Tests for packet handling."""

    def test_rejects_non_gp_packet(self, manager: GreenPowerManager) -> None:
        """Non-GP packets should be rejected."""
        packet = t.ZigbeePacket(
            src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x1234)),
            dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
            dst_ep=t.uint8_t(1),  # Not GP endpoint
            cluster_id=t.uint16_t(0x0006),  # On/Off cluster
            data=t.SerializableBytes(b"\x00\x00\x00"),
        )
        assert manager.handle_packet(packet) is False

    def test_rejects_wrong_cluster(self, manager: GreenPowerManager) -> None:
        packet = t.ZigbeePacket(
            src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x1234)),
            dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
            dst_ep=t.uint8_t(GP_ENDPOINT),
            cluster_id=t.uint16_t(0x0006),  # Wrong cluster
            data=t.SerializableBytes(b"\x00\x00\x00"),
        )
        assert manager.handle_packet(packet) is False

    def test_rejects_too_short_data(self, manager: GreenPowerManager) -> None:
        packet = t.ZigbeePacket(
            src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x1234)),
            dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
            dst_ep=t.uint8_t(GP_ENDPOINT),
            cluster_id=t.uint16_t(GP_CLUSTER_ID),
            data=t.SerializableBytes(b"\x00\x00"),  # Too short
        )
        assert manager.handle_packet(packet) is False

    def test_rejects_non_cluster_specific(self, manager: GreenPowerManager) -> None:
        packet = t.ZigbeePacket(
            src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x1234)),
            dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
            dst_ep=t.uint8_t(GP_ENDPOINT),
            cluster_id=t.uint16_t(GP_CLUSTER_ID),
            data=t.SerializableBytes(b"\x00\x00\x00"),  # frame_control bit 0 = 0
        )
        assert manager.handle_packet(packet) is False

    @pytest.mark.asyncio
    async def test_accepts_gp_notification(self, manager: GreenPowerManager) -> None:
        packet = _make_gp_notification_packet(
            source_id=0x12345678,
            command_id=GPDCommandID.Toggle,
        )
        assert manager.handle_packet(packet) is True


class TestGPCommandDispatch:
    """Tests for GP command dispatching."""

    @pytest.mark.asyncio
    async def test_dispatch_known_device(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Commands from known devices should fire listener_event."""
        dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=0)
        manager.add_device(dev)

        await manager._dispatch_gp_command(
            source_id=0x12345678,
            frame_counter=1,
            command_id=GPDCommandID.Toggle,
            payload=b"",
        )

        mock_app.listener_event.assert_called_with(
            "gp_command_received",
            dev,
            GPDCommandID.Toggle,
            b"",
        )

    @pytest.mark.asyncio
    async def test_dispatch_unknown_device_ignored(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Commands from unknown devices should be ignored."""
        await manager._dispatch_gp_command(
            source_id=0xDEADBEEF,
            frame_counter=1,
            command_id=GPDCommandID.Toggle,
            payload=b"",
        )

        mock_app.listener_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_replay_rejected(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Replayed frames (same or lower counter) should be rejected."""
        dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=10)
        manager.add_device(dev)

        await manager._dispatch_gp_command(
            source_id=0x12345678,
            frame_counter=10,  # Same as stored
            command_id=GPDCommandID.Toggle,
            payload=b"",
        )

        mock_app.listener_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_increments_counter(
        self, manager: GreenPowerManager
    ) -> None:
        """Successful dispatch should update the frame counter."""
        dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=0)
        manager.add_device(dev)

        await manager._dispatch_gp_command(
            source_id=0x12345678,
            frame_counter=42,
            command_id=GPDCommandID.Toggle,
            payload=b"",
        )

        assert dev.frame_counter == 42


class TestCommissioning:
    """Tests for GP commissioning."""

    @pytest.mark.asyncio
    async def test_commissioning_window(self, manager: GreenPowerManager) -> None:
        """Opening and closing commissioning window."""
        assert not manager.is_commissioning

        await manager.permit_join(time_s=60)
        assert manager.is_commissioning

        await manager.permit_join(time_s=0)
        assert not manager.is_commissioning

    @pytest.mark.asyncio
    async def test_commissioning_sends_proxy_mode(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Opening commissioning should send ProxyCommissioningMode."""
        await manager.permit_join(time_s=60)

        assert mock_app.send_packet.call_count == 1
        sent_packet = mock_app.send_packet.call_args[0][0]
        assert sent_packet.dst_ep == GP_ENDPOINT
        assert sent_packet.cluster_id == GP_CLUSTER_ID

    @pytest.mark.asyncio
    async def test_close_commissioning_sends_exit(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Closing commissioning should send ProxyCommissioningMode exit."""
        await manager.permit_join(time_s=60)
        mock_app.send_packet.reset_mock()

        await manager.permit_join(time_s=0)

        assert mock_app.send_packet.call_count == 1

    @pytest.mark.asyncio
    async def test_process_commissioning_creates_device(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Commissioning command should create a GPDevice."""
        # Open commissioning window
        await manager.permit_join(time_s=60)
        mock_app.send_packet.reset_mock()

        # Minimal commissioning payload: device_id=0x02, options=0x00
        comm_payload = bytes([0x02, 0x00])

        await manager._process_commissioning(
            source_id=0xAABBCCDD,
            frame_counter=1,
            payload=comm_payload,
        )

        # Device should be registered
        dev = manager.get_device(0xAABBCCDD)
        assert dev is not None
        assert dev.device_id == 0x02
        assert dev.source_id == 0xAABBCCDD

        # Listener event should fire
        mock_app.listener_event.assert_any_call("gp_device_joined", dev)

        # GP Pairing should be sent
        assert mock_app.send_packet.call_count >= 1

    @pytest.mark.asyncio
    async def test_commissioning_ignored_when_window_closed(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Commissioning should be ignored if window is not open."""
        comm_payload = bytes([0x02, 0x00])

        await manager._process_commissioning(
            source_id=0xAABBCCDD,
            frame_counter=1,
            payload=comm_payload,
        )

        assert manager.get_device(0xAABBCCDD) is None
        mock_app.listener_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_commissioning_with_security_key(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Commissioning with unencrypted security key."""
        await manager.permit_join(time_s=60)
        mock_app.send_packet.reset_mock()

        security_key = bytes(range(16))
        # options: extended present = 0x80
        # extended: Encrypted level + key_present = 0x03 | 0x20 = 0x23
        comm_payload = bytes([0x02, 0x80, 0x23]) + security_key

        await manager._process_commissioning(
            source_id=0x11223344,
            frame_counter=5,
            payload=comm_payload,
        )

        dev = manager.get_device(0x11223344)
        assert dev is not None
        assert dev.security_key == security_key
        assert dev.security_level == SecurityLevel.Encrypted

    @pytest.mark.asyncio
    async def test_commissioning_with_outgoing_counter(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Commissioning with outgoing frame counter."""
        await manager.permit_join(time_s=60)

        import struct

        # extended: outgoing_counter_present = 0x80
        comm_payload = bytes([0x02, 0x80, 0x80]) + struct.pack("<I", 42)

        await manager._process_commissioning(
            source_id=0x55667788,
            frame_counter=1,
            payload=comm_payload,
        )

        dev = manager.get_device(0x55667788)
        assert dev is not None
        assert dev.frame_counter == 42


class TestDecommissioning:
    """Tests for GP decommissioning."""

    @pytest.mark.asyncio
    async def test_decommission_known_device(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Decommissioning a known device should remove it."""
        dev = GPDevice(source_id=0x12345678, device_id=0x02)
        manager.add_device(dev)

        await manager._process_decommissioning(0x12345678)

        assert manager.get_device(0x12345678) is None
        mock_app.listener_event.assert_any_call("gp_device_left", dev)
        # GP Pairing (remove) should be sent
        assert mock_app.send_packet.call_count >= 1

    @pytest.mark.asyncio
    async def test_decommission_unknown_device(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Decommissioning unknown device should be a no-op."""
        await manager._process_decommissioning(0xDEADBEEF)
        mock_app.listener_event.assert_not_called()


class TestPersistence:
    """Tests for device persistence."""

    def test_load_devices(self, manager: GreenPowerManager) -> None:
        """Loading persisted device data."""
        data = [
            {
                "source_id": 0x12345678,
                "device_id": 0x02,
                "security_key": "00" * 16,
                "security_level": 3,
                "security_key_type": 4,
                "frame_counter": 100,
            },
            {
                "source_id": 0xAABBCCDD,
                "device_id": 0x07,
            },
        ]

        manager.load_devices(data)

        assert len(manager.devices) == 2
        dev1 = manager.get_device(0x12345678)
        assert dev1 is not None
        assert dev1.device_id == 0x02
        assert dev1.frame_counter == 100
        assert dev1.security_level == SecurityLevel.Encrypted

        dev2 = manager.get_device(0xAABBCCDD)
        assert dev2 is not None
        assert dev2.device_id == 0x07

    def test_get_devices_data(self, manager: GreenPowerManager) -> None:
        """Serializing devices for persistence."""
        dev1 = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=10)
        dev2 = GPDevice(source_id=0xAABBCCDD, device_id=0x07)
        manager.add_device(dev1)
        manager.add_device(dev2)

        data = manager.get_devices_data()

        assert len(data) == 2
        source_ids = {d["source_id"] for d in data}
        assert source_ids == {0x12345678, 0xAABBCCDD}

    def test_load_save_roundtrip(self, manager: GreenPowerManager) -> None:
        """Saving and loading should preserve all data."""
        dev = GPDevice(
            source_id=0x12345678,
            device_id=0x02,
            security_key=bytes(range(16)),
            security_level=SecurityLevel.Encrypted,
            security_key_type=SecurityKeyType.IndividualKey,
            frame_counter=42,
            gpd_commands=[0x20, 0x21, 0x22],
        )
        manager.add_device(dev)

        data = manager.get_devices_data()

        manager2 = GreenPowerManager(MagicMock())
        manager2.load_devices(data)

        restored = manager2.get_device(0x12345678)
        assert restored is not None
        assert restored.source_id == dev.source_id
        assert restored.device_id == dev.device_id
        assert restored.security_key == dev.security_key
        assert restored.security_level == dev.security_level
        assert restored.frame_counter == dev.frame_counter
        assert restored.gpd_commands == dev.gpd_commands

    def test_load_invalid_data_skipped(self, manager: GreenPowerManager) -> None:
        """Invalid device data should be skipped without crashing."""
        data = [
            {"invalid": "data"},
            {"source_id": 0x12345678, "device_id": 0x02},
        ]

        manager.load_devices(data)
        assert len(manager.devices) == 1


class TestBuildZclFrame:
    """Tests for ZCL frame construction."""

    def test_client_frame(self) -> None:
        frame = GreenPowerManager._build_zcl_frame(
            command_id=0x02, is_client=True, payload=b"\xAA\xBB"
        )
        # frame_control: 0x01 (cluster-specific) | 0x10 (disable default resp) = 0x11
        assert frame[0] == 0x11
        assert frame[1] == 0x00  # seq_num
        assert frame[2] == 0x02  # command_id
        assert frame[3:] == b"\xAA\xBB"

    def test_server_frame(self) -> None:
        frame = GreenPowerManager._build_zcl_frame(
            command_id=0x00, is_client=False, payload=b"\xCC"
        )
        # frame_control: 0x01 | 0x08 (direction) | 0x10 = 0x19
        assert frame[0] == 0x19
        assert frame[2] == 0x00

    def test_empty_payload(self) -> None:
        frame = GreenPowerManager._build_zcl_frame(
            command_id=0x06, is_client=True, payload=b""
        )
        assert len(frame) == 3
