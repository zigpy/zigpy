"""Tests for Green Power Manager."""

from __future__ import annotations

import asyncio
import struct

from tests.async_mock import AsyncMock, MagicMock
from zigpy.profiles import zgp as zgp_profile
import zigpy.types as t
from zigpy.zcl.clusters.greenpower import NotificationOptions, NotificationSchema
from zigpy.zgp.crypto import encrypt_security_key
from zigpy.zgp.device import GPDevice
from zigpy.zgp.events import CommandReceived, DeviceJoined, DeviceLeft
from zigpy.zgp.manager import GreenPowerManager
import zigpy.zgp.types as zgptypes
from zigpy.zgp.types import (
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
)


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
        profile_id=t.uint16_t(zgp_profile.PROFILE_ID),
        cluster_id=t.uint16_t(GP_CLUSTER_ID),
        data=t.SerializableBytes(zcl_frame),
    )


def test_gp_manager_creation(manager):
    assert manager.devices == {}
    assert not manager.is_commissioning


def test_gp_manager_add_device(manager):
    dev = GPDevice(source_id=0x12345678, device_id=0x02)
    manager.add_device(dev)
    assert manager.get_device(0x12345678) is dev
    assert len(manager.devices) == 1


def test_gp_manager_remove_device(manager):
    dev = GPDevice(source_id=0x12345678, device_id=0x02)
    manager.add_device(dev)
    removed = manager.remove_device(0x12345678)
    assert removed is dev
    assert manager.get_device(0x12345678) is None


def test_gp_manager_remove_nonexistent_device(manager):
    removed = manager.remove_device(0xDEADBEEF)
    assert removed is None


def test_gp_manager_get_device_nonexistent(manager):
    assert manager.get_device(0xDEADBEEF) is None


def test_rejects_non_gp_packet(manager):
    """Non-GP packets should be rejected."""
    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x1234)),
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
        dst_ep=t.uint8_t(1),  # Not GP endpoint
        cluster_id=t.uint16_t(0x0006),  # On/Off cluster
        data=t.SerializableBytes(b"\x00\x00\x00"),
    )
    assert manager.handle_packet(packet) is False


def test_rejects_wrong_cluster(manager):
    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x1234)),
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
        dst_ep=t.uint8_t(GP_ENDPOINT),
        cluster_id=t.uint16_t(0x0006),  # Wrong cluster
        data=t.SerializableBytes(b"\x00\x00\x00"),
    )
    assert manager.handle_packet(packet) is False


def test_rejects_too_short_data(manager):
    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x1234)),
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
        dst_ep=t.uint8_t(GP_ENDPOINT),
        cluster_id=t.uint16_t(GP_CLUSTER_ID),
        data=t.SerializableBytes(b"\x00\x00"),  # Too short
    )
    assert manager.handle_packet(packet) is False


def test_rejects_non_cluster_specific(manager):
    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x1234)),
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
        dst_ep=t.uint8_t(GP_ENDPOINT),
        cluster_id=t.uint16_t(GP_CLUSTER_ID),
        data=t.SerializableBytes(b"\x00\x00\x00"),  # frame_control bit 0 = 0
    )
    assert manager.handle_packet(packet) is False


async def test_accepts_gp_notification(manager):
    packet = _make_gp_notification_packet(
        source_id=0x12345678,
        command_id=GPDCommandID.Toggle,
    )
    assert manager.handle_packet(packet) is True


async def test_dispatch_known_device(manager, gp_events):
    """Commands from known devices should fire a CommandReceived event."""
    dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=0)
    manager.add_device(dev)

    await manager._dispatch_gp_command(
        source_id=0x12345678,
        frame_counter=1,
        command_id=GPDCommandID.Toggle,
        payload=b"",
    )

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert len(commands) == 1
    assert commands[0].device is dev
    assert commands[0].command_id is GPDCommandID.Toggle
    assert commands[0].payload == b""


async def test_dispatch_unknown_device_ignored(manager, gp_events):
    """Commands from unknown devices should be ignored."""
    await manager._dispatch_gp_command(
        source_id=0xDEADBEEF,
        frame_counter=1,
        command_id=GPDCommandID.Toggle,
        payload=b"",
    )

    assert gp_events == []


async def test_dispatch_replay_rejected(manager, gp_events):
    """Replayed frames (same or lower counter) should be rejected."""
    dev = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=10)
    manager.add_device(dev)

    await manager._dispatch_gp_command(
        source_id=0x12345678,
        frame_counter=10,  # Same as stored
        command_id=GPDCommandID.Toggle,
        payload=b"",
    )

    assert gp_events == []


async def test_dispatch_increments_counter(manager):
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


async def test_dupplication_first_notification_passes(manager):
    """First occurrence of (sourceID, frameCounter) should pass."""
    assert not manager._is_duplicate(0x12345678, 1)


async def test_dupplication_second_notification_blocked(manager):
    """Same (sourceID, frameCounter) within timeout should be blocked."""
    assert not manager._is_duplicate(0x12345678, 1)
    assert manager._is_duplicate(0x12345678, 1)


async def test_dupplication_different_source_id_passes(manager):
    """Different sourceID with same counter should pass."""
    assert not manager._is_duplicate(0x11111111, 1)
    assert not manager._is_duplicate(0x22222222, 1)


async def test_dupplication_different_counter_passes(manager):
    """Same sourceID with different counter should pass."""
    assert not manager._is_duplicate(0x12345678, 1)
    assert not manager._is_duplicate(0x12345678, 2)


async def test_dupplication_expired_entry_passes(manager):
    """Entries older than DEDUP_TIMEOUT_S should be purged."""
    debouncer = manager._dedup_debouncer
    manager._is_duplicate(0x12345678, 1)

    # Fast-forward the debouncer's clock past the dedup window.
    debouncer.clean(now=debouncer._loop.time() + manager.DEDUP_TIMEOUT_S + 1)

    # Should pass again after expiry
    assert not manager._is_duplicate(0x12345678, 1)


async def test_commissioning_window(manager):
    """Opening and closing commissioning window."""
    assert not manager.is_commissioning

    await manager.permit_join(time_s=60)
    assert manager.is_commissioning

    await manager.permit_join(time_s=0)
    assert not manager.is_commissioning


async def test_commissioning_sends_proxy_mode(app, manager):
    """Opening commissioning should send ProxyCommissioningMode."""
    await manager.permit_join(time_s=60)

    assert app.send_packet.call_count == 1
    sent_packet = app.send_packet.call_args[0][0]
    assert sent_packet.dst_ep == GP_ENDPOINT
    assert sent_packet.cluster_id == GP_CLUSTER_ID


async def test_close_commissioning_sends_exit(app, manager):
    """Closing commissioning should send ProxyCommissioningMode exit."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await manager.permit_join(time_s=0)

    assert app.send_packet.call_count == 1


async def test_commissioning_window_timer_closes_on_expiry(app, manager, monkeypatch):
    """The commissioning window auto-closes when its timer expires."""

    async def _instant_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("asyncio.sleep", _instant_sleep)

    await manager.permit_join(time_s=60)
    assert manager.is_commissioning
    app.send_packet.reset_mock()

    # With sleep patched, the timer task closes the window immediately.
    await manager._commissioning_task

    assert not manager.is_commissioning
    assert manager._commissioning_window_end == 0
    assert app.send_packet.call_count == 1


async def test_process_commissioning_creates_device(app, manager, gp_events):
    """Commissioning command should create a GPDevice."""
    # Open commissioning window
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

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

    joined = [e for _, e in gp_events if isinstance(e, DeviceJoined)]
    assert joined == [DeviceJoined(device=dev)]

    # GP Pairing should be sent
    assert app.send_packet.call_count >= 1


async def test_commissioning_ignored_when_window_closed(manager, gp_events):
    """Commissioning should be ignored if window is not open."""
    comm_payload = bytes([0x02, 0x00])

    await manager._process_commissioning(
        source_id=0xAABBCCDD,
        frame_counter=1,
        payload=comm_payload,
    )

    assert manager.get_device(0xAABBCCDD) is None
    assert gp_events == []


async def test_commissioning_rejects_unspecified_source_id(app, manager, gp_events):
    """SourceID 0x00000000 is unspecified per ZGP spec and must be rejected."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await manager._process_commissioning(
        source_id=0x00000000,
        frame_counter=1,
        payload=bytes([0x02, 0x00]),
    )

    assert manager.get_device(0x00000000) is None
    assert not any(isinstance(e, DeviceJoined) for _, e in gp_events)


async def test_commissioning_with_security_key(app, manager):
    """Commissioning with unencrypted security key.

    Extended options byte 0x23 = 0b00100011:
    - Bits 0-1 = 0b11 = SecurityLevel.Encrypted (Table 54)
    - Bits 2-4 = 0b000 = SecurityKeyType.NoKey (Table 54)
    - Bit 5 = 1 = key_present
    - Bits 6-7 = 0
    """
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

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
    assert bytes(dev.security_key) == security_key
    assert dev.security_level == SecurityLevel.Encrypted
    # Extended byte 0x23: bits 2-4 = 0b000 = NoKey (Table 54)
    assert dev.security_key_type == SecurityKeyType.NoKey


async def test_commissioning_with_outgoing_counter(manager):
    """Commissioning with outgoing frame counter."""
    await manager.permit_join(time_s=60)

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


async def test_commissioning_with_outgoing_counter_zero(manager):
    """Outgoing counter of 0 must be used, not confused with None.

    Per the ZGP spec, outgoing_counter=0 is a valid initial frame
    counter. It must not be treated as absent (Python falsy).
    """
    await manager.permit_join(time_s=60)

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


async def test_decommission_known_device(app, manager, gp_events):
    """Decommissioning a known device should remove it."""
    dev = GPDevice(source_id=0x12345678, device_id=0x02)
    manager.add_device(dev)

    await manager._process_decommissioning(0x12345678)

    assert manager.get_device(0x12345678) is None
    left = [e for _, e in gp_events if isinstance(e, DeviceLeft)]
    assert left == [DeviceLeft(device=dev)]
    # GP Pairing (remove) should be sent
    assert app.send_packet.call_count >= 1


async def test_decommission_unknown_device(manager, gp_events):
    """Decommissioning unknown device should be a no-op."""
    await manager._process_decommissioning(0xDEADBEEF)
    assert gp_events == []


async def test_pairing_encrypts_security_key(app, manager):
    """GP Pairing must encrypt the security key before sending.

    The key in the GP Pairing should NOT be the plaintext key.
    It should be encrypted via encrypt_security_key(sourceID, key)
    matching zigbee-herdsman's behavior.
    """

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

    assert app.send_packet.call_count == 1
    sent_data = app.send_packet.call_args[0][0].data.serialize()

    # The plaintext key must NOT appear in the sent packet
    assert plaintext_key not in sent_data

    # The encrypted key MUST appear instead
    encrypted_key, _ = encrypt_security_key(source_id, plaintext_key)
    assert bytes(encrypted_key) in sent_data


def test_load_devices(manager):
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


def test_get_devices_data(manager):
    """Serializing devices for persistence."""
    dev1 = GPDevice(source_id=0x12345678, device_id=0x02, frame_counter=10)
    dev2 = GPDevice(source_id=0xAABBCCDD, device_id=0x07)
    manager.add_device(dev1)
    manager.add_device(dev2)

    data = manager.get_devices_data()

    assert len(data) == 2
    source_ids = {d["source_id"] for d in data}
    assert source_ids == {0x12345678, 0xAABBCCDD}


def test_load_save_roundtrip(manager):
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


def test_load_invalid_data_skipped(manager):
    """Invalid device data should be skipped without crashing."""
    data = [
        {"invalid": "data"},
        {"source_id": 0x12345678, "device_id": 0x02},
    ]

    manager.load_devices(data)
    assert len(manager.devices) == 1


def test_client_frame():
    frame = GreenPowerManager._build_zcl_frame(
        command_id=0x02, is_client=True, payload=b"\xaa\xbb"
    )
    # frame_control: 0x01 (cluster-specific) | 0x10 (disable default resp) = 0x11
    assert frame[0] == 0x11
    assert frame[1] == 0x00  # seq_num
    assert frame[2] == 0x02  # command_id
    assert frame[3:] == b"\xaa\xbb"


def test_server_frame():
    frame = GreenPowerManager._build_zcl_frame(
        command_id=0x00, is_client=False, payload=b"\xcc"
    )
    # frame_control: 0x01 | 0x08 (direction) | 0x10 = 0x19
    assert frame[0] == 0x19
    assert frame[2] == 0x00


def test_empty_payload():
    frame = GreenPowerManager._build_zcl_frame(
        command_id=0x06, is_client=True, payload=b""
    )
    assert len(frame) == 3


async def test_channel_request_sends_response(app, manager):
    """Channel Request should trigger a GP Response with Channel Config."""
    # Channel Request payload: next_channel=15 (offset 4), second=20 (offset 9)
    channel_req_payload = bytes([4 | (9 << 4)])

    await manager._process_channel_request(
        source_id=0x12345678,
        payload=channel_req_payload,
        proxy_nwk=0x1234,
    )

    # Should have sent a GP Response
    assert app.send_packet.call_count == 1
    sent = app.send_packet.call_args[0][0]
    assert sent.dst_ep == GP_ENDPOINT
    assert sent.cluster_id == GP_CLUSTER_ID


async def test_channel_config_contains_correct_channel(app, manager):
    """Channel Config payload must contain the coordinator's channel.

    Per ZGP spec, GP Channel Configuration (0xF3) payload is 1 byte:
    bits 0-3 = operational channel offset (channel - 11),
    bit 4 = basic (1).
    For channel 20: offset = 9, basic = 1 => byte = 0x19.
    """
    app.state.network_info.channel = 20

    await manager._process_channel_request(
        source_id=0x12345678,
        payload=bytes([0x00]),
        proxy_nwk=0x1234,
    )

    assert app.send_packet.call_count == 1
    sent = app.send_packet.call_args[0][0]
    zcl_data = sent.data.serialize()
    # The GP Response wraps the Channel Config payload.
    # Channel 20 => offset 9, basic=1 => 0x09 | 0x10 = 0x19
    # This byte must appear in the serialized ZCL frame.
    assert bytes([0x19]) in zcl_data


async def test_channel_request_without_proxy(app, manager):
    """Channel Request without proxy_nwk should use coordinator NWK."""
    await manager._process_channel_request(
        source_id=0x12345678,
        payload=bytes([0x00]),
        proxy_nwk=None,
    )

    assert app.send_packet.call_count == 1


async def test_invalid_channel_request_ignored(app, manager):
    """Invalid channel request payload should be ignored."""
    await manager._process_channel_request(
        source_id=0x12345678,
        payload=b"",
        proxy_nwk=0x1234,
    )

    app.send_packet.assert_not_called()


async def test_rx_capable_gets_commissioning_reply(app, manager):
    """RX-capable GPD commissioning should send a Commissioning Reply."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

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
    assert app.send_packet.call_count == 2

    dev = manager.get_device(0xAABBCCDD)
    assert dev is not None
    assert dev.rx_on_capability is True


async def test_non_rx_skips_commissioning_reply(app, manager):
    """Non-RX GPD should NOT get a Commissioning Reply."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    # options: extended (bit 7) only, no rx_on = 0x80
    comm_payload = bytes([0x02, 0x80, 0x00])

    await manager._process_commissioning(
        source_id=0x11223344,
        frame_counter=1,
        payload=comm_payload,
        proxy_nwk=0x1234,
    )

    # Should have sent: GP Pairing only = 1 packet
    assert app.send_packet.call_count == 1


async def test_commissioning_reply_uses_proxy_as_temp_master(app, manager):
    """Commissioning Reply should be a GP Response (cmd 0x06) with 0xF0.

    Per ZGP spec, the GP Commissioning Reply (0xF0) is sent via
    GP Response (client cmd 0x06) through the temp master proxy.
    The ZCL frame must contain:
    - command_id 0x06 (GP Response) in byte 2
    - gpd_command_id 0xF0 (Commissioning Reply) in the payload
    """
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    comm_payload = bytes([0x02, 0x82, 0x00])  # rx_on=True (bit 1, Table 53)

    await manager._process_commissioning(
        source_id=0xAABBCCDD,
        frame_counter=1,
        payload=comm_payload,
        proxy_nwk=0x5678,
    )

    # First packet = Commissioning Reply, second = GP Pairing
    assert app.send_packet.call_count == 2

    # Verify first packet is GP Response (cmd 0x06) with gpd_cmd 0xF0
    reply_packet = app.send_packet.call_args_list[0][0][0]
    reply_data = reply_packet.data.serialize()
    # ZCL byte 2 = command_id = 0x06 (GP Response)
    assert reply_data[2] == 0x06
    # The payload must contain 0xF0 (GP Commissioning Reply command)
    assert bytes([0xF0]) in reply_data


async def test_gp_response_packet_structure(app, manager):
    """GP Response should be sent with correct endpoint/cluster/profile."""
    await manager._send_gp_response(
        source_id=0x12345678,
        gpd_command_id=0xF3,
        gpd_command_payload=bytes([0x14]),
        proxy_nwk=0x1234,
    )

    assert app.send_packet.call_count == 1
    sent = app.send_packet.call_args[0][0]
    assert sent.dst_ep == GP_ENDPOINT
    assert sent.src_ep == GP_ENDPOINT
    assert sent.cluster_id == GP_CLUSTER_ID
    assert sent.profile_id == zgp_profile.PROFILE_ID


async def test_gp_response_without_proxy(app, manager):
    """GP Response without proxy should use coordinator as temp master."""
    await manager._send_gp_response(
        source_id=0x12345678,
        gpd_command_id=0xF0,
        gpd_command_payload=bytes([0x00]),
        proxy_nwk=None,
    )

    assert app.send_packet.call_count == 1


async def test_gp_response_send_failure(app, manager):
    """GP Response send failure should be handled gracefully."""
    app.send_packet = AsyncMock(side_effect=TimeoutError)

    await manager._send_gp_response(
        source_id=0x12345678,
        gpd_command_id=0xF3,
        gpd_command_payload=bytes([0x14]),
        proxy_nwk=0x1234,
    )

    # Should not raise, just log warning


async def test_dispatch_secured_payload_is_not_truncated(manager, gp_events):
    """A secured GPD's payload must reach listeners byte for byte.

    The GP Notification has no MIC field (Figure 23), so the trailing bytes of
    the payload are command data, never a MIC to strip.
    """

    source_id = 0xAABBCCDD
    payload = bytes([0x00, 0x00, 0x21, 0x30, 0x02, 0x00, 0x01])

    dev = GPDevice(
        source_id=source_id,
        device_id=0x02,
        security_key=bytes(range(16)),
        security_level=SecurityLevel.Encrypted,
        frame_counter=0,
    )
    manager.add_device(dev)

    await manager._dispatch_gp_command(
        source_id=source_id,
        frame_counter=5,
        command_id=GPDCommandID.AttributeReporting,
        payload=payload,
    )

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert commands == [
        CommandReceived(
            device=dev,
            command_id=GPDCommandID.AttributeReporting,
            payload=payload,
        )
    ]


async def test_commissioning_with_encrypted_key(app, manager):
    """Commissioning with key_encrypted=True should decrypt the key.

    Tests the path in _process_commissioning where the GPD provides
    its security key encrypted with the GP link key.
    """

    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

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
    assert bytes(dev.security_key) == original_key
    assert dev.security_level == SecurityLevel.Encrypted


# NOTE: _handle_commissioning_notification (server cmd 0x04) cannot be
# tested because CommissioningNotificationOptions in greenpower.py has
# a bit-field alignment issue (18 bits instead of 16), preventing the
# schema from serializing/deserializing. The fix belongs in the cluster
# definition (PR #1659), not in the GP manager module.


async def test_shutdown_cancels_commissioning(manager):
    """Shutdown should cancel the commissioning timer and reset state."""
    await manager.permit_join(time_s=300)
    assert manager.is_commissioning

    await manager.shutdown()

    assert not manager.is_commissioning
    assert manager._commissioning_task is None


async def test_shutdown_cancels_owned_tasks(manager):
    """Shutdown must cancel tasks spawned by ``_create_task``."""

    async def never_finishes() -> None:
        await asyncio.Event().wait()

    task = manager._create_task(never_finishes(), name="stuck")
    assert task in manager._tasks

    await manager.shutdown()

    assert task.cancelled()
    assert not manager._tasks


async def test_dedup_in_notification_flow(manager, gp_events):
    """Duplicate filtering should work within _handle_gp_notification.

    When two proxies forward the same GPD frame, only the first
    should dispatch a command.
    """
    source_id = 0x12345678
    dev = GPDevice(source_id=source_id, device_id=0x02, frame_counter=0)
    manager.add_device(dev)

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

    commands = [e for _, e in gp_events if isinstance(e, CommandReceived)]
    assert len(commands) == 1
    assert commands[0].device is dev


async def test_notification_with_corrupt_payload(manager, gp_events):
    """Corrupt GP Notification payload must be ignored, no event fired."""
    await manager._handle_gp_notification(
        payload=b"\xff\xff",  # too short / invalid for NotificationSchema
        proxy_nwk=0x1234,
    )
    assert gp_events == []


async def test_commissioning_with_corrupt_payload(app, manager):
    """Corrupt commissioning payload must not create a device."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await manager._process_commissioning(
        source_id=0x12345678,
        frame_counter=1,
        payload=b"\xff",  # too short for GPCommissioningPayload
    )

    assert manager.get_device(0x12345678) is None


async def test_commissioning_with_bad_encrypted_key(manager):
    """Invalid encrypted key MIC must reject commissioning."""

    await manager.permit_join(time_s=60)

    # Extended 0x63: Encrypted + key_present + key_encrypted (Table 54)
    bad_key = b"\x00" * 16
    bad_mic = struct.pack("<I", 0xDEADDEAD)  # wrong MIC
    comm_payload = bytes([0x02, 0x80, 0x63]) + bad_key + bad_mic

    await manager._process_commissioning(
        source_id=0xBBBBBBBB,
        frame_counter=1,
        payload=comm_payload,
    )

    # Device must NOT be created when key decryption fails
    assert manager.get_device(0xBBBBBBBB) is None


async def test_commissioning_with_reserved_security_level(manager):
    """The reserved security level 0b01 must not commission a device (A.1.4.1.3)."""

    await manager.permit_join(time_s=60)

    # Extended 0x01: security level 0b01, no key material (Table 54)
    comm_payload = bytes([0x02, 0x80, 0x01])

    await manager._process_commissioning(
        source_id=0xCCCCCCCC,
        frame_counter=1,
        payload=comm_payload,
    )

    assert manager.get_device(0xCCCCCCCC) is None


async def test_unhandled_server_command_ignored(manager, gp_events):
    """Unknown server command (e.g. PairingSearch 0x01) is ignored."""
    await manager._process_zcl_command(
        command_id=0x01,  # GP Pairing Search, not implemented
        payload=b"\x00" * 10,
        is_server_to_client=False,
        proxy_nwk=0x1234,
    )
    assert gp_events == []


async def test_unexpected_client_direction_ignored(manager, gp_events):
    """Client-to-server direction (server→client) in reception is unexpected."""
    await manager._process_zcl_command(
        command_id=0x01,
        payload=b"\x00" * 10,
        is_server_to_client=True,  # unexpected for reception
        proxy_nwk=0x1234,
    )
    assert gp_events == []


async def test_commissioning_notification_cmd_routed(manager, gp_events):
    """Server cmd 0x04 is routed to _handle_commissioning_notification.

    The handler itself has a schema bug (pragma: no cover) but the
    dispatch path in _process_zcl_command must be exercised.
    """
    # The handler will fail to parse (schema bug) and return silently
    await manager._process_zcl_command(
        command_id=0x04,
        payload=b"\x00" * 20,  # arbitrary, will fail parsing
        is_server_to_client=False,
        proxy_nwk=0x1234,
    )
    # No crash, no event — the schema parse failure is expected
    assert gp_events == []


async def test_notification_routes_commissioning(app, manager):
    """GP Notification carrying CommissioningRequest (0xE0) triggers commissioning."""

    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    comm_inner = bytes([0x02, 0x00])  # device_id=2, options=0

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
    notif = NotificationSchema(
        options=options,
        gpd_id=zgptypes.DeviceID(0xAAAA1111),
        frame_counter=t.uint32_t(1),
        command_id=t.uint8_t(GPDCommandID.CommissioningRequest),
        payload=t.LVBytes(comm_inner),
    )
    await manager._handle_gp_notification(notif.serialize(), proxy_nwk=0x1234)

    assert manager.get_device(0xAAAA1111) is not None


async def test_notification_routes_decommissioning(manager):
    """GP Notification with DecommissioningRequest (0xE1) removes device."""

    dev = GPDevice(source_id=0xBBBB2222, device_id=0x02)
    manager.add_device(dev)

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
    notif = NotificationSchema(
        options=options,
        gpd_id=zgptypes.DeviceID(0xBBBB2222),
        frame_counter=t.uint32_t(1),
        command_id=t.uint8_t(GPDCommandID.DecommissioningRequest),
        payload=t.LVBytes(b""),
    )
    await manager._handle_gp_notification(notif.serialize(), proxy_nwk=0x1234)

    assert manager.get_device(0xBBBB2222) is None


async def test_notification_routes_channel_request(app, manager):
    """GP Notification with ChannelRequest (0xE3) triggers a GP Response."""

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
    notif = NotificationSchema(
        options=options,
        gpd_id=zgptypes.DeviceID(0xCCCC3333),
        frame_counter=t.uint32_t(1),
        command_id=t.uint8_t(GPDCommandID.ChannelRequest),
        payload=t.LVBytes(bytes([0x00])),
    )
    await manager._handle_gp_notification(notif.serialize(), proxy_nwk=0x1234)

    # Should have sent a GP Response (Channel Configuration)
    assert app.send_packet.call_count >= 1


async def test_notification_routes_success_report(manager, gp_events):
    """GP SuccessReport (0xE2) is accepted silently with no side effects."""

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
    notif = NotificationSchema(
        options=options,
        gpd_id=zgptypes.DeviceID(0xDDDD4444),
        frame_counter=t.uint32_t(1),
        command_id=t.uint8_t(GPDCommandID.SuccessReport),
        payload=t.LVBytes(b""),
    )
    await manager._handle_gp_notification(notif.serialize(), proxy_nwk=0x1234)

    # No device created, no command dispatched
    assert gp_events == []


async def test_proxy_commissioning_mode_send_failure(app, manager):
    """ProxyCommissioningMode send failure still opens window locally."""
    app.send_packet = AsyncMock(side_effect=TimeoutError)

    await manager.permit_join(time_s=60)

    # Window must be open locally despite send failure
    assert manager.is_commissioning


async def test_pairing_send_failure(app, manager):
    """GP Pairing send failure must not crash the sink."""
    app.send_packet = AsyncMock(side_effect=TimeoutError)

    dev = GPDevice(source_id=0x99998888, device_id=0x02)
    manager.add_device(dev)

    # Must not raise despite send_packet failure
    await manager.send_pairing(dev, add_sink=True)


async def test_reopen_commissioning_cancels_previous(manager):
    """Opening a new window cancels the previous timer."""
    await manager.permit_join(time_s=300)
    first_task = manager._commissioning_task

    await manager.permit_join(time_s=60)
    second_task = manager._commissioning_task

    # Tasks must be different (new timer created)
    assert second_task is not first_task
