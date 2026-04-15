"""Tests for Green Power Manager."""

from __future__ import annotations

import asyncio

from tests.async_mock import AsyncMock, MagicMock, Mock

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
    app.state.network_info.channel = 15
    app.send_packet = AsyncMock()
    app.listener_event = Mock()
    app.create_task = Mock(
        side_effect=lambda coro, name=None: asyncio.ensure_future(coro)
    )
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


class TestDeduplication:
    """Tests for GP duplicate filtering (spec A.3.6.1.2)."""

    def test_first_notification_passes(self, manager: GreenPowerManager) -> None:
        """First occurrence of (sourceID, frameCounter) should pass."""
        assert not manager._is_duplicate(0x12345678, 1)

    def test_second_notification_blocked(self, manager: GreenPowerManager) -> None:
        """Same (sourceID, frameCounter) within timeout should be blocked."""
        assert not manager._is_duplicate(0x12345678, 1)
        assert manager._is_duplicate(0x12345678, 1)

    def test_different_source_id_passes(self, manager: GreenPowerManager) -> None:
        """Different sourceID with same counter should pass."""
        assert not manager._is_duplicate(0x11111111, 1)
        assert not manager._is_duplicate(0x22222222, 1)

    def test_different_counter_passes(self, manager: GreenPowerManager) -> None:
        """Same sourceID with different counter should pass."""
        assert not manager._is_duplicate(0x12345678, 1)
        assert not manager._is_duplicate(0x12345678, 2)

    def test_expired_entry_passes(self, manager: GreenPowerManager) -> None:
        """Entries older than DEDUP_TIMEOUT_S should be purged."""
        manager._is_duplicate(0x12345678, 1)

        # Manually expire the entry
        for key in manager._dedup_cache:
            manager._dedup_cache[key] -= manager.DEDUP_TIMEOUT_S + 1

        # Should pass again after expiry
        assert not manager._is_duplicate(0x12345678, 1)


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
    async def test_commissioning_rejects_unspecified_source_id(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """SourceID 0x00000000 is unspecified per ZGP spec and must be rejected."""
        await manager.permit_join(time_s=60)
        mock_app.send_packet.reset_mock()
        mock_app.listener_event.reset_mock()

        await manager._process_commissioning(
            source_id=0x00000000,
            frame_counter=1,
            payload=bytes([0x02, 0x00]),
        )

        assert manager.get_device(0x00000000) is None
        # No gp_device_joined event should have fired
        for call in mock_app.listener_event.call_args_list:
            assert call[0][0] != "gp_device_joined"

    @pytest.mark.asyncio
    async def test_commissioning_with_security_key(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Commissioning with unencrypted security key.

        Extended options byte 0x23 = 0b00100011:
        - Bits 0-1 = 0b11 = SecurityLevel.Encrypted (Table 54)
        - Bits 2-4 = 0b000 = SecurityKeyType.NoKey (Table 54)
        - Bit 5 = 1 = key_present
        - Bits 6-7 = 0
        """
        await manager.permit_join(time_s=60)
        mock_app.send_packet.reset_mock()

        security_key = bytes(range(16))
        # options: bit 7 = extended present (Table 53) = 0x80
        # extended: Encrypted + key_present = 0x03 | 0x20 = 0x23 (Table 54)
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
        # Extended byte 0x23: bits 2-4 = 0b000 = NoKey (Table 54)
        assert dev.security_key_type == SecurityKeyType.NoKey

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

    @pytest.mark.asyncio
    async def test_commissioning_with_outgoing_counter_zero(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Outgoing counter of 0 must be used, not confused with None.

        Per the ZGP spec, outgoing_counter=0 is a valid initial frame
        counter. It must not be treated as absent (Python falsy).
        """
        await manager.permit_join(time_s=60)

        import struct

        # extended: outgoing_counter_present (bit 7) = 0x80
        comm_payload = bytes([0x02, 0x80, 0x80]) + struct.pack("<I", 0)

        await manager._process_commissioning(
            source_id=0x99887766,
            frame_counter=999,  # GP Notification frame counter
            payload=comm_payload,
        )

        dev = manager.get_device(0x99887766)
        assert dev is not None
        # Must use outgoing_counter=0 from payload, NOT frame_counter=999
        assert dev.frame_counter == 0


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


class TestSendPairingKeyEncryption:
    """Tests for security key encryption in GP Pairing."""

    @pytest.mark.asyncio
    async def test_pairing_encrypts_security_key(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """GP Pairing must encrypt the security key before sending.

        The key in the GP Pairing should NOT be the plaintext key.
        It should be encrypted via encrypt_security_key(sourceID, key)
        matching zigbee-herdsman's behavior.
        """
        from zigpy.zgp.crypto import encrypt_security_key

        source_id = 0x12345678
        plaintext_key = bytes(range(16))

        dev = GPDevice(
            source_id=source_id,
            device_id=0x02,
            security_key=plaintext_key,
            security_level=SecurityLevel.Encrypted,
            security_key_type=SecurityKeyType.NoKey,
        )
        manager.add_device(dev)

        await manager.send_pairing(dev, add_sink=True)

        assert mock_app.send_packet.call_count == 1
        sent_data = mock_app.send_packet.call_args[0][0].data.serialize()

        # The plaintext key must NOT appear in the sent packet
        assert plaintext_key not in sent_data

        # The encrypted key MUST appear instead
        encrypted_key, _ = encrypt_security_key(source_id, plaintext_key)
        assert bytes(encrypted_key) in sent_data


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
            command_id=0x02, is_client=True, payload=b"\xaa\xbb"
        )
        # frame_control: 0x01 (cluster-specific) | 0x10 (disable default resp) = 0x11
        assert frame[0] == 0x11
        assert frame[1] == 0x00  # seq_num
        assert frame[2] == 0x02  # command_id
        assert frame[3:] == b"\xaa\xbb"

    def test_server_frame(self) -> None:
        frame = GreenPowerManager._build_zcl_frame(
            command_id=0x00, is_client=False, payload=b"\xcc"
        )
        # frame_control: 0x01 | 0x08 (direction) | 0x10 = 0x19
        assert frame[0] == 0x19
        assert frame[2] == 0x00

    def test_empty_payload(self) -> None:
        frame = GreenPowerManager._build_zcl_frame(
            command_id=0x06, is_client=True, payload=b""
        )
        assert len(frame) == 3


class TestChannelConfigResponse:
    """Tests for GP Channel Configuration response."""

    @pytest.mark.asyncio
    async def test_channel_request_sends_response(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Channel Request should trigger a GP Response with Channel Config."""
        # Channel Request payload: next_channel=15 (offset 4), second=20 (offset 9)
        channel_req_payload = bytes([4 | (9 << 4)])

        await manager._process_channel_request(
            source_id=0x12345678,
            payload=channel_req_payload,
            proxy_nwk=0x1234,
        )

        # Should have sent a GP Response
        assert mock_app.send_packet.call_count == 1
        sent = mock_app.send_packet.call_args[0][0]
        assert sent.dst_ep == GP_ENDPOINT
        assert sent.cluster_id == GP_CLUSTER_ID

    @pytest.mark.asyncio
    async def test_channel_config_contains_correct_channel(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Channel Config payload must contain the coordinator's channel.

        Per ZGP spec, GP Channel Configuration (0xF3) payload is 1 byte:
        bits 0-3 = operational channel offset (channel - 11),
        bit 4 = basic (1).
        For channel 20: offset = 9, basic = 1 => byte = 0x19.
        """
        mock_app.state.network_info.channel = 20

        await manager._process_channel_request(
            source_id=0x12345678,
            payload=bytes([0x00]),
            proxy_nwk=0x1234,
        )

        assert mock_app.send_packet.call_count == 1
        sent = mock_app.send_packet.call_args[0][0]
        zcl_data = sent.data.serialize()
        # The GP Response wraps the Channel Config payload.
        # Channel 20 => offset 9, basic=1 => 0x09 | 0x10 = 0x19
        # This byte must appear in the serialized ZCL frame.
        assert bytes([0x19]) in zcl_data

    @pytest.mark.asyncio
    async def test_channel_request_without_proxy(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Channel Request without proxy_nwk should use coordinator NWK."""
        await manager._process_channel_request(
            source_id=0x12345678,
            payload=bytes([0x00]),
            proxy_nwk=None,
        )

        assert mock_app.send_packet.call_count == 1

    @pytest.mark.asyncio
    async def test_invalid_channel_request_ignored(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Invalid channel request payload should be ignored."""
        await manager._process_channel_request(
            source_id=0x12345678,
            payload=b"",
            proxy_nwk=0x1234,
        )

        mock_app.send_packet.assert_not_called()


class TestCommissioningReply:
    """Tests for GP Commissioning Reply to RX-capable GPDs."""

    @pytest.mark.asyncio
    async def test_rx_capable_gets_commissioning_reply(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """RX-capable GPD commissioning should send a Commissioning Reply."""
        await manager.permit_join(time_s=60)
        mock_app.send_packet.reset_mock()

        # Commissioning with rx_on_capability=True (bit 1 of options)
        # options: extended (bit 7) + rx_on (bit 1) = 0x82
        comm_payload = bytes([0x02, 0x82, 0x00])

        await manager._process_commissioning(
            source_id=0xAABBCCDD,
            frame_counter=1,
            payload=comm_payload,
            proxy_nwk=0x1234,
        )

        # Should have sent: Commissioning Reply + GP Pairing = 2 packets
        assert mock_app.send_packet.call_count == 2

        dev = manager.get_device(0xAABBCCDD)
        assert dev is not None
        assert dev.rx_on_capability is True

    @pytest.mark.asyncio
    async def test_non_rx_skips_commissioning_reply(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Non-RX GPD should NOT get a Commissioning Reply."""
        await manager.permit_join(time_s=60)
        mock_app.send_packet.reset_mock()

        # options: extended (bit 7) only, no rx_on = 0x80
        comm_payload = bytes([0x02, 0x80, 0x00])

        await manager._process_commissioning(
            source_id=0x11223344,
            frame_counter=1,
            payload=comm_payload,
            proxy_nwk=0x1234,
        )

        # Should have sent: GP Pairing only = 1 packet
        assert mock_app.send_packet.call_count == 1

    @pytest.mark.asyncio
    async def test_commissioning_reply_uses_proxy_as_temp_master(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Commissioning Reply should be a GP Response (cmd 0x06) with 0xF0.

        Per ZGP spec, the GP Commissioning Reply (0xF0) is sent via
        GP Response (client cmd 0x06) through the temp master proxy.
        The ZCL frame must contain:
        - command_id 0x06 (GP Response) in byte 2
        - gpd_command_id 0xF0 (Commissioning Reply) in the payload
        """
        await manager.permit_join(time_s=60)
        mock_app.send_packet.reset_mock()

        comm_payload = bytes([0x02, 0x82, 0x00])  # rx_on=True (bit 1, Table 53)

        await manager._process_commissioning(
            source_id=0xAABBCCDD,
            frame_counter=1,
            payload=comm_payload,
            proxy_nwk=0x5678,
        )

        # First packet = Commissioning Reply, second = GP Pairing
        assert mock_app.send_packet.call_count == 2

        # Verify first packet is GP Response (cmd 0x06) with gpd_cmd 0xF0
        reply_packet = mock_app.send_packet.call_args_list[0][0][0]
        reply_data = reply_packet.data.serialize()
        # ZCL byte 2 = command_id = 0x06 (GP Response)
        assert reply_data[2] == 0x06
        # The payload must contain 0xF0 (GP Commissioning Reply command)
        assert bytes([0xF0]) in reply_data


class TestSendGPResponse:
    """Tests for the generic GP Response sender."""

    @pytest.mark.asyncio
    async def test_gp_response_packet_structure(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """GP Response should be sent with correct endpoint/cluster/profile."""
        await manager._send_gp_response(
            source_id=0x12345678,
            gpd_command_id=0xF3,
            gpd_command_payload=bytes([0x14]),
            proxy_nwk=0x1234,
        )

        assert mock_app.send_packet.call_count == 1
        sent = mock_app.send_packet.call_args[0][0]
        assert sent.dst_ep == GP_ENDPOINT
        assert sent.src_ep == GP_ENDPOINT
        assert sent.cluster_id == GP_CLUSTER_ID
        assert sent.profile_id == 0xA1E0

    @pytest.mark.asyncio
    async def test_gp_response_without_proxy(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """GP Response without proxy should use coordinator as temp master."""
        await manager._send_gp_response(
            source_id=0x12345678,
            gpd_command_id=0xF0,
            gpd_command_payload=bytes([0x00]),
            proxy_nwk=None,
        )

        assert mock_app.send_packet.call_count == 1

    @pytest.mark.asyncio
    async def test_gp_response_send_failure(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """GP Response send failure should be handled gracefully."""
        mock_app.send_packet = AsyncMock(side_effect=TimeoutError)

        await manager._send_gp_response(
            source_id=0x12345678,
            gpd_command_id=0xF3,
            gpd_command_payload=bytes([0x14]),
            proxy_nwk=0x1234,
        )

        # Should not raise, just log warning


class TestMissingPathCoverage:
    """Tests for previously untested code paths."""

    @pytest.mark.asyncio
    async def test_dispatch_with_encrypted_payload(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Command dispatch should decrypt payload when security is active.

        Tests the decryption path in _dispatch_gp_command that was
        previously uncovered (SecurityLevel != NoSecurity).
        """
        from zigpy.zgp.crypto import encrypt_payload

        source_id = 0xAABBCCDD
        security_key = bytes(range(16))
        plaintext = bytes([0x20])  # Toggle command
        frame_counter = 5

        # Encrypt the payload to simulate what a GPD would send
        encrypted, mic = encrypt_payload(
            source_id,
            frame_counter,
            security_key,
            plaintext,
            SecurityLevel.Encrypted,
        )

        dev = GPDevice(
            source_id=source_id,
            device_id=0x02,
            security_key=security_key,
            security_level=SecurityLevel.Encrypted,
            frame_counter=0,
        )
        manager.add_device(dev)

        # Dispatch with encrypted payload + MIC concatenated
        await manager._dispatch_gp_command(
            source_id=source_id,
            frame_counter=frame_counter,
            command_id=GPDCommandID.Toggle,
            payload=encrypted + mic,
        )

        # Should fire event with DECRYPTED payload
        mock_app.listener_event.assert_called_with(
            "gp_command_received",
            dev,
            GPDCommandID.Toggle,
            plaintext,
        )

    @pytest.mark.asyncio
    async def test_commissioning_with_encrypted_key(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Commissioning with key_encrypted=True should decrypt the key.

        Tests the path in _process_commissioning where the GPD provides
        its security key encrypted with the GP link key.
        """
        import struct

        from zigpy.zgp.crypto import encrypt_security_key

        await manager.permit_join(time_s=60)
        mock_app.send_packet.reset_mock()

        source_id = 0x11223344
        original_key = bytes(range(16))

        # Encrypt the key as a GPD would during commissioning
        encrypted_key, key_mic_bytes = encrypt_security_key(source_id, original_key)
        key_mic_int = struct.unpack("<I", key_mic_bytes)[0]

        # Extended: Encrypted(0b11) + key_present(bit5) + key_encrypted(bit6)
        # = 0x03 | 0x20 | 0x40 = 0x63  (Table 54)
        comm_payload = (
            bytes([0x02, 0x80, 0x63]) + encrypted_key + struct.pack("<I", key_mic_int)
        )

        await manager._process_commissioning(
            source_id=source_id,
            frame_counter=1,
            payload=comm_payload,
        )

        dev = manager.get_device(source_id)
        assert dev is not None
        # The key must be DECRYPTED to the original
        assert dev.security_key == original_key
        assert dev.security_level == SecurityLevel.Encrypted

    # NOTE: _handle_commissioning_notification (server cmd 0x04) cannot be
    # tested because CommissioningNotificationOptions in greenpower.py has
    # a bit-field alignment issue (18 bits instead of 16), preventing the
    # schema from serializing/deserializing. The fix belongs in the cluster
    # definition (PR #1659), not in the GP manager module.

    @pytest.mark.asyncio
    async def test_shutdown_cancels_commissioning(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Shutdown should cancel the commissioning timer and reset state."""
        await manager.permit_join(time_s=300)
        assert manager.is_commissioning

        await manager.shutdown()

        assert not manager.is_commissioning
        assert manager._commissioning_task is None

    @pytest.mark.asyncio
    async def test_dedup_in_notification_flow(
        self, manager: GreenPowerManager, mock_app: MagicMock
    ) -> None:
        """Duplicate filtering should work within _handle_gp_notification.

        When two proxies forward the same GPD frame, only the first
        should dispatch a command.
        """
        source_id = 0x12345678
        dev = GPDevice(source_id=source_id, device_id=0x02, frame_counter=0)
        manager.add_device(dev)

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
            frame_counter=t.uint32_t(1),
            command_id=t.uint8_t(GPDCommandID.Toggle),
            payload=t.LVBytes(b""),
        )
        payload = notification.serialize()

        # First proxy delivers
        await manager._handle_gp_notification(payload, proxy_nwk=0x1111)
        # Second proxy delivers same frame
        await manager._handle_gp_notification(payload, proxy_nwk=0x2222)

        # Only ONE gp_command_received should fire
        command_events = [
            c
            for c in mock_app.listener_event.call_args_list
            if c[0][0] == "gp_command_received"
        ]
        assert len(command_events) == 1
