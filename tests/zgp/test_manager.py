"""Tests for Green Power Manager."""

from __future__ import annotations

import asyncio
import struct
from unittest.mock import call

import pytest

from tests.async_mock import AsyncMock
from tests.zgp.conftest import wait_for_gp_processing
from zigpy.device import GreenPowerDevice
from zigpy.profiles import zgp as zgp_profile
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.greenpower import GreenPowerProxy, PairingSchema, ResponseSchema
from zigpy.zgp.commands import GPGenericSwitchConfiguration
from zigpy.zgp.crypto import encrypt_security_key
from zigpy.zgp.types import (
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    ApplicationID,
    CommunicationMode,
    DeviceID,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SrcID,
    SwitchType,
)
from zigpy.zgp.util import synthetic_ieee


def make_gp_packet(
    src_id: int,
    command_id: GPDCommandID,
    payload: bytes = b"",
    frame_counter: int = 1,
    gpp_short_addr: int | None = None,
) -> t.ZigbeeGpPacket:
    return t.ZigbeeGpPacket(
        application_id=ApplicationID.SrcID,
        src_id=SrcID(src_id),
        command_id=command_id,
        payload=t.SerializableBytes(payload),
        frame_counter=t.uint32_t(frame_counter),
        security_level=SecurityLevel.NoSecurity,
        security_key_type=SecurityKeyType.NoKey,
        security_status=SecurityStatus.NoSecurity,
        gpp_short_addr=None if gpp_short_addr is None else t.NWK(gpp_short_addr),
    )


def test_gp_manager_creation(manager):
    assert not manager.is_commissioning


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


async def test_process_commissioning_creates_device(app, manager):
    """Commissioning command should create a GreenPowerDevice."""
    # Open commissioning window
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    # Minimal commissioning payload: device_id=0x02, options=0x00
    comm_payload = bytes([0x02, 0x00])

    await manager._process_commissioning(
        make_gp_packet(
            0xAABBCCDD, GPDCommandID.CommissioningRequest, comm_payload, frame_counter=1
        ),
    )

    # Device should be registered
    dev = app.devices[synthetic_ieee(0xAABBCCDD)]
    assert dev.device_id == 0x02
    assert dev.src_id == 0xAABBCCDD

    assert call("device_joined", dev) in app.listener_event.mock_calls
    assert app.device_initialized.mock_calls == [call(dev)]

    # GP Pairing should be sent
    assert app.send_packet.call_count >= 1


async def test_commissioning_ignored_when_window_closed(app, manager):
    """Commissioning should be ignored if window is not open."""
    comm_payload = bytes([0x02, 0x00])

    await manager._process_commissioning(
        make_gp_packet(
            0xAABBCCDD, GPDCommandID.CommissioningRequest, comm_payload, frame_counter=1
        ),
    )

    assert synthetic_ieee(0xAABBCCDD) not in app.devices
    assert len(app.device_initialized.mock_calls) == 0


async def test_commissioning_rejects_unspecified_source_id(app, manager):
    """SourceID 0x00000000 is unspecified per ZGP spec and must be rejected."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await manager._process_commissioning(
        make_gp_packet(
            0x00000000,
            GPDCommandID.CommissioningRequest,
            bytes([0x02, 0x00]),
            frame_counter=1,
        ),
    )

    assert synthetic_ieee(0x00000000) not in app.devices
    assert len(app.device_initialized.mock_calls) == 0


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
        make_gp_packet(
            0x11223344, GPDCommandID.CommissioningRequest, comm_payload, frame_counter=5
        ),
    )

    dev = app.devices[synthetic_ieee(0x11223344)]
    assert bytes(dev.security_key) == security_key
    assert dev.security_level == SecurityLevel.Encrypted
    # Extended byte 0x23: bits 2-4 = 0b000 = NoKey (Table 54)
    assert dev.security_key_type == SecurityKeyType.NoKey


async def test_commissioning_with_outgoing_counter(app, manager):
    """Commissioning with outgoing frame counter."""
    await manager.permit_join(time_s=60)

    # extended: outgoing_counter_present = 0x80
    comm_payload = bytes([0x02, 0x80, 0x80]) + struct.pack("<I", 42)

    await manager._process_commissioning(
        make_gp_packet(
            0x55667788, GPDCommandID.CommissioningRequest, comm_payload, frame_counter=1
        ),
    )

    dev = app.devices[synthetic_ieee(0x55667788)]
    assert dev.frame_counter == 42


async def test_recommissioning_replaces_device(app, manager):
    """Re-commissioning swaps the device object, announced like a re-interview."""
    await manager.permit_join(time_s=60)

    app.gp_packet_received(
        make_gp_packet(0x12345678, GPDCommandID.CommissioningRequest, b"\x02\x00")
    )
    await wait_for_gp_processing()

    old_device = app.devices[synthetic_ieee(0x12345678)]
    old_task = old_device.create_task(asyncio.Event().wait())

    app.gp_packet_received(
        make_gp_packet(
            0x12345678,
            GPDCommandID.CommissioningRequest,
            b"\x07\x00",
            frame_counter=2,
        )
    )
    await wait_for_gp_processing()

    new_device = app.devices[synthetic_ieee(0x12345678)]
    assert new_device is not old_device
    assert new_device.device_id == DeviceID.GenericSwitch

    # The old device object is cleaned up
    await asyncio.sleep(0)
    assert old_task.cancelled()

    assert app.device_initialized.mock_calls == [call(old_device)]
    assert call("device_reinterviewed", new_device) in app.listener_event.mock_calls
    assert call("device_joined", new_device) not in app.listener_event.mock_calls


async def test_commissioning_with_switch_information(app, manager):
    """A GenericSwitch describes its contacts in the switch information field."""
    await manager.permit_join(time_s=60)

    # options: app_info_present (bit 2) = 0x04 (Table 53)
    # app_info: switch_info_present (bit 4) = 0x10 (Figure 111)
    # switch information: length 2, 2 contacts as a button, no contacts closed
    comm_payload = bytes([0x07, 0x04, 0x10, 0x02, 0x12, 0x00])

    await manager._process_commissioning(
        make_gp_packet(0x66778899, GPDCommandID.CommissioningRequest, comm_payload),
    )

    dev = app.devices[synthetic_ieee(0x66778899)]
    assert dev.device_id == DeviceID.GenericSwitch
    assert dev.switch_configuration == GPGenericSwitchConfiguration(
        num_contacts=2, switch_type=SwitchType.Button, _reserved=0
    )


async def test_commissioning_with_outgoing_counter_zero(app, manager):
    """Outgoing counter of 0 must be used, not confused with None.

    Per the ZGP spec, outgoing_counter=0 is a valid initial frame
    counter. It must not be treated as absent (Python falsy).
    """
    await manager.permit_join(time_s=60)

    # extended: outgoing_counter_present (bit 7) = 0x80
    comm_payload = bytes([0x02, 0x80, 0x80]) + struct.pack("<I", 0)

    await manager._process_commissioning(
        make_gp_packet(
            0x99887766,
            GPDCommandID.CommissioningRequest,
            comm_payload,
            frame_counter=999,
        ),
    )

    dev = app.devices[synthetic_ieee(0x99887766)]
    # Must use outgoing_counter=0 from payload, NOT frame_counter=999
    assert dev.frame_counter == 0


@pytest.mark.parametrize(
    (
        "frame_counter",
        "security_level",
        "security_key_type",
        "security_status",
        "removed",
    ),
    [
        (
            11,
            SecurityLevel.FullFrameCounterAndMIC,
            SecurityKeyType.IndividualKey,
            SecurityStatus.SecuritySuccess,
            True,
        ),
        # Replayed frame counter
        (
            10,
            SecurityLevel.FullFrameCounterAndMIC,
            SecurityKeyType.IndividualKey,
            SecurityStatus.SecuritySuccess,
            False,
        ),
        # Unprotected frame for a GPD commissioned with security
        (
            11,
            SecurityLevel.NoSecurity,
            SecurityKeyType.NoKey,
            SecurityStatus.NoSecurity,
            False,
        ),
        # Another key type
        (
            11,
            SecurityLevel.FullFrameCounterAndMIC,
            SecurityKeyType.NWKKey,
            SecurityStatus.SecuritySuccess,
            False,
        ),
        # Failed security processing
        (
            11,
            SecurityLevel.FullFrameCounterAndMIC,
            SecurityKeyType.IndividualKey,
            SecurityStatus.AuthFailure,
            False,
        ),
    ],
)
async def test_decommissioning(
    app,
    manager,
    frame_counter,
    security_level,
    security_key_type,
    security_status,
    removed,
):
    """Decommissioning is only acted upon if it passes the checks (A.3.5.2.4)."""
    dev = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    dev.device_id = DeviceID.OnOffSwitch
    dev.security_key = t.KeyData(range(16))
    dev.security_level = SecurityLevel.FullFrameCounterAndMIC
    dev.security_key_type = SecurityKeyType.IndividualKey
    dev.frame_counter = t.uint32_t(10)
    app.devices[dev.ieee] = dev

    app.gp_packet_received(
        t.ZigbeeGpPacket(
            application_id=ApplicationID.SrcID,
            src_id=SrcID(0x12345678),
            command_id=GPDCommandID.DecommissioningRequest,
            frame_counter=t.uint32_t(frame_counter),
            security_level=security_level,
            security_key_type=security_key_type,
            security_status=security_status,
        )
    )
    await wait_for_gp_processing()

    assert (dev.ieee not in app.devices) is removed
    assert (call("device_removed", dev) in app.listener_event.mock_calls) is removed

    # GP Pairing (remove) is sent only for an accepted command
    assert app.send_packet.call_count == int(removed)


async def test_decommissioning_unknown_device(app, manager):
    """Decommissioning from an unknown GPD is ignored."""
    app.gp_packet_received(
        make_gp_packet(0xDEADBEEF, GPDCommandID.DecommissioningRequest)
    )
    await wait_for_gp_processing()

    assert len(app.send_packet.mock_calls) == 0


async def test_pairing_carries_key_in_the_clear(app, manager):
    """GP Pairing carries the Sink Table key as-is, proxies store it unmodified."""
    dev = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    dev.device_id = DeviceID.OnOffSwitch
    dev.security_key = t.KeyData(range(16))
    dev.security_level = SecurityLevel.Encrypted
    dev.security_key_type = SecurityKeyType.IndividualKey
    dev.frame_counter = t.uint32_t(0)

    await manager.send_pairing(dev, add_sink=True)

    packet = app.send_packet.mock_calls[0].args[0]
    _, data = foundation.ZCLHeader.deserialize(packet.data.serialize())
    pairing, _ = PairingSchema.deserialize(data)

    assert pairing.options.security_key_present
    assert pairing.options.security_level == SecurityLevel.Encrypted
    assert pairing.options.security_key_type == SecurityKeyType.IndividualKey
    assert pairing.key == t.KeyData(range(16))


@pytest.mark.parametrize(
    ("send", "command"),
    [
        (
            lambda manager: manager.permit_join(time_s=60),
            GreenPowerProxy.ClientCommandDefs.proxy_commissioning_mode,
        ),
        (
            lambda manager: manager._send_gp_response(
                source_id=0x12345678,
                gpd_command_id=GPDCommandID.ChannelConfiguration,
                gpd_command_payload=bytes([0x14]),
            ),
            GreenPowerProxy.ClientCommandDefs.response,
        ),
    ],
)
async def test_commands_sent_server_to_client(app, manager, send, command):
    """The sink is the GP cluster server, so commands to proxies are server-to-client."""
    await send(manager)

    packet = app.send_packet.mock_calls[0].args[0]
    hdr, data = foundation.ZCLHeader.deserialize(packet.data.serialize())

    assert hdr.frame_control.frame_type == foundation.FrameType.CLUSTER_COMMAND
    assert hdr.direction == foundation.Direction.Server_to_Client
    assert hdr.frame_control.disable_default_response
    assert hdr.command_id == command.id
    assert hdr.tsn == packet.tsn

    command.schema.deserialize(data)


async def test_pairing_sent_server_to_client(app, manager):
    """GP Pairing (0x01) read client-to-server would be a GP Pairing Search."""
    dev = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    dev.device_id = DeviceID.OnOffSwitch
    dev.security_level = SecurityLevel.NoSecurity
    dev.security_key_type = SecurityKeyType.NoKey
    dev.frame_counter = t.uint32_t(0)

    await manager.send_pairing(dev, add_sink=True)

    packet = app.send_packet.mock_calls[0].args[0]
    hdr, data = foundation.ZCLHeader.deserialize(packet.data.serialize())

    assert hdr.direction == foundation.Direction.Server_to_Client
    assert hdr.command_id == GreenPowerProxy.ClientCommandDefs.pairing.id

    pairing, _ = PairingSchema.deserialize(data)
    assert pairing.gpd_id == 0x12345678
    assert pairing.options.add_sink


async def test_channel_request_sends_response(app, manager):
    """Channel Request should trigger a GP Response with Channel Config."""
    # Channel Request payload: next_channel=15 (offset 4), second=20 (offset 9)
    channel_req_payload = bytes([4 | (9 << 4)])

    await manager._process_channel_request(
        make_gp_packet(0x12345678, GPDCommandID.ChannelRequest, channel_req_payload),
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
        make_gp_packet(0x12345678, GPDCommandID.ChannelRequest, bytes([0x00])),
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
        make_gp_packet(0x12345678, GPDCommandID.ChannelRequest, bytes([0x00])),
        proxy_nwk=None,
    )

    assert app.send_packet.call_count == 1


async def test_invalid_channel_request_ignored(app, manager):
    """Invalid channel request payload should be ignored."""
    await manager._process_channel_request(
        make_gp_packet(0x12345678, GPDCommandID.ChannelRequest, b""),
        proxy_nwk=0x1234,
    )

    assert len(app.send_packet.mock_calls) == 0


async def test_rx_capable_gets_commissioning_reply(app, manager):
    """RX-capable GPD commissioning should send a Commissioning Reply."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    # Commissioning with rx_on_capability=True (bit 1 of options)
    # options: extended (bit 7) + rx_on (bit 1) = 0x82
    comm_payload = bytes([0x02, 0x82, 0x00])

    await manager._process_commissioning(
        make_gp_packet(
            0xAABBCCDD, GPDCommandID.CommissioningRequest, comm_payload, frame_counter=1
        ),
        proxy_nwk=0x1234,
    )

    # Should have sent: Commissioning Reply + GP Pairing = 2 packets
    assert app.send_packet.call_count == 2

    dev = app.devices[synthetic_ieee(0xAABBCCDD)]
    assert dev.rx_on_capability is True


async def test_non_rx_skips_commissioning_reply(app, manager):
    """Non-RX GPD should NOT get a Commissioning Reply."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    # options: extended (bit 7) only, no rx_on = 0x80
    comm_payload = bytes([0x02, 0x80, 0x00])

    await manager._process_commissioning(
        make_gp_packet(
            0x11223344, GPDCommandID.CommissioningRequest, comm_payload, frame_counter=1
        ),
        proxy_nwk=0x1234,
    )

    # Should have sent: GP Pairing only = 1 packet
    assert app.send_packet.call_count == 1


@pytest.mark.parametrize(
    ("gpp_short_addr", "temp_master", "communication_mode"),
    [
        # Tunneled by a proxy
        (0x5678, 0x5678, CommunicationMode.UnicastLightweight),
        # Received directly by the coordinator
        (None, 0x0000, CommunicationMode.GroupcastForwardToDGroup),
    ],
)
async def test_commissioning_uses_forwarding_proxy(
    app, manager, gpp_short_addr, temp_master, communication_mode
):
    """The proxy that tunneled the Commissioning GPDF is the GP Response TempMaster."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    app.gp_packet_received(
        make_gp_packet(
            0xAABBCCDD,
            GPDCommandID.CommissioningRequest,
            bytes([0x02, 0x82, 0x00]),  # rx_on=True (bit 1, Table 53)
            gpp_short_addr=gpp_short_addr,
        )
    )
    await wait_for_gp_processing()

    reply_packet, pairing_packet = [c.args[0] for c in app.send_packet.mock_calls]

    _, data = foundation.ZCLHeader.deserialize(reply_packet.data.serialize())
    response, _ = ResponseSchema.deserialize(data)
    assert response.temp_master_short_addr == temp_master
    assert response.gpd_command_id == GPDCommandID.CommissioningReply

    _, data = foundation.ZCLHeader.deserialize(pairing_packet.data.serialize())
    pairing, _ = PairingSchema.deserialize(data)
    assert pairing.options.communication_mode == communication_mode


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
        make_gp_packet(
            source_id, GPDCommandID.CommissioningRequest, comm_payload, frame_counter=1
        ),
    )

    dev = app.devices[synthetic_ieee(source_id)]
    # The key must be DECRYPTED to the original
    assert bytes(dev.security_key) == original_key
    assert dev.security_level == SecurityLevel.Encrypted


async def test_shutdown_cancels_commissioning(manager):
    """Shutdown should cancel the commissioning timer and reset state."""
    await manager.permit_join(time_s=300)
    assert manager.is_commissioning

    await manager.shutdown()

    assert not manager.is_commissioning
    assert manager._commissioning_task is None


async def test_shutdown_cancels_owned_tasks(manager):
    """Shutdown must cancel tasks spawned by `_create_task`."""

    async def never_finishes() -> None:
        await asyncio.Event().wait()

    task = manager._create_task(never_finishes(), name="stuck")
    assert task in manager._tasks

    await manager.shutdown()

    assert task.cancelled()
    assert not manager._tasks


async def test_commissioning_with_corrupt_payload(app, manager):
    """Corrupt commissioning payload must not create a device."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await manager._process_commissioning(
        make_gp_packet(
            0x12345678, GPDCommandID.CommissioningRequest, b"\xff", frame_counter=1
        ),
    )

    assert synthetic_ieee(0x12345678) not in app.devices


async def test_commissioning_with_bad_encrypted_key(app, manager):
    """Invalid encrypted key MIC must reject commissioning."""

    await manager.permit_join(time_s=60)

    # Extended 0x63: Encrypted + key_present + key_encrypted (Table 54)
    bad_key = b"\x00" * 16
    bad_mic = struct.pack("<I", 0xDEADDEAD)  # wrong MIC
    comm_payload = bytes([0x02, 0x80, 0x63]) + bad_key + bad_mic

    await manager._process_commissioning(
        make_gp_packet(
            0xBBBBBBBB, GPDCommandID.CommissioningRequest, comm_payload, frame_counter=1
        ),
    )

    # Device must NOT be created when key decryption fails
    assert synthetic_ieee(0xBBBBBBBB) not in app.devices


async def test_commissioning_with_reserved_security_level(app, manager):
    """The reserved security level 0b01 must not commission a device (A.1.4.1.3)."""

    await manager.permit_join(time_s=60)

    # Extended 0x01: security level 0b01, no key material (Table 54)
    comm_payload = bytes([0x02, 0x80, 0x01])

    await manager._process_commissioning(
        make_gp_packet(
            0xCCCCCCCC, GPDCommandID.CommissioningRequest, comm_payload, frame_counter=1
        ),
    )

    assert synthetic_ieee(0xCCCCCCCC) not in app.devices


async def test_gp_packet_routes_commissioning(app, manager):
    """A CommissioningRequest (0xE0) GPDF triggers commissioning."""

    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    comm_inner = bytes([0x02, 0x00])  # device_id=2, options=0

    app.gp_packet_received(
        make_gp_packet(0xAAAA1111, GPDCommandID.CommissioningRequest, comm_inner)
    )
    await wait_for_gp_processing()

    assert synthetic_ieee(0xAAAA1111) in app.devices


async def test_gp_packet_routes_channel_request(app, manager):
    """A ChannelRequest (0xE3) GPDF triggers a GP Response."""

    app.gp_packet_received(
        make_gp_packet(0xCCCC3333, GPDCommandID.ChannelRequest, bytes([0x00]))
    )
    await wait_for_gp_processing()

    # Should have sent a GP Response (Channel Configuration)
    assert app.send_packet.call_count == 1


async def test_gp_packet_routes_success_report(app, manager):
    """A SuccessReport (0xE2) GPDF is accepted silently with no side effects."""

    app.gp_packet_received(make_gp_packet(0xDDDD4444, GPDCommandID.SuccessReport))
    await wait_for_gp_processing()

    # No device created, nothing sent
    assert synthetic_ieee(0xDDDD4444) not in app.devices
    assert len(app.send_packet.mock_calls) == 0


async def test_gp_packet_duplicate_commissioning_dropped(app, manager):
    """The same commissioning GPDF forwarded by two proxies is processed once."""

    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    packet = make_gp_packet(0xEEEE5555, GPDCommandID.CommissioningRequest, b"\x02\x00")

    app.gp_packet_received(packet)
    await wait_for_gp_processing()
    app.gp_packet_received(packet)
    await wait_for_gp_processing()

    assert len(app.device_initialized.mock_calls) == 1


async def test_gp_packet_ieee_addressing_ignored(app, manager):
    """Commissioning GPDFs from IEEE-addressed GPDs are not supported."""

    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    packet = t.ZigbeeGpPacket(
        application_id=ApplicationID.IEEE,
        ieee=t.EUI64.convert("11:22:33:44:55:66:77:88"),
        endpoint=t.uint8_t(1),
        command_id=GPDCommandID.CommissioningRequest,
        payload=t.SerializableBytes(b"\x02\x00"),
        frame_counter=t.uint32_t(1),
    )

    app.gp_packet_received(packet)
    await wait_for_gp_processing()

    assert len(app.device_initialized.mock_calls) == 0
    assert len(app.send_packet.mock_calls) == 0


async def test_proxy_commissioning_mode_send_failure(app, manager):
    """The window is not opened if the proxies could not be told about it."""
    app.send_packet = AsyncMock(side_effect=TimeoutError)

    with pytest.raises(TimeoutError):
        await manager.permit_join(time_s=60)

    assert not manager.is_commissioning


async def test_reopen_commissioning_cancels_previous(manager):
    """Opening a new window cancels the previous timer."""
    await manager.permit_join(time_s=300)
    first_task = manager._commissioning_task

    await manager.permit_join(time_s=60)
    second_task = manager._commissioning_task

    # Tasks must be different (new timer created)
    assert second_task is not first_task
