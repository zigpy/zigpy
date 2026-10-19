"""Tests for Green Power Manager."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import struct
from unittest.mock import call

import freezegun
import pytest

from tests.async_mock import AsyncMock
from tests.zgp.conftest import wait_for_gp_processing
from zigpy.device import GreenPowerDevice
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.greenpower import (
    GreenPowerProxy,
    PairingSchema,
    ProxyCommissioningModeSchema,
    ResponseSchema,
)
from zigpy.zgp.commands import (
    GPChannelConfigurationPayload,
    GPCommissioningReplyPayload,
    GPGenericSwitchConfiguration,
)
from zigpy.zgp.crypto import encrypt_security_key
from zigpy.zgp.types import (
    GP_ENDPOINT,
    ApplicationID,
    CommunicationMode,
    DeviceID,
    GPDCommandID,
    ProxyCommissioningModeExitMode,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SrcID,
    SwitchType,
)
from zigpy.zgp.util import derive_alias, synthetic_ieee

KEY = bytes(range(16))
ENCRYPTED_KEY, KEY_MIC = encrypt_security_key(0x11223344, KEY)


def make_gp_packet(
    src_id: int,
    command_id: GPDCommandID,
    payload: bytes = b"",
    frame_counter: int = 1,
    gpp_short_addr: int | None = None,
    rx_after_tx: bool | None = None,
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
        rx_after_tx=rx_after_tx,
    )


def sent_command(packet: t.ZigbeePacket, schema: type[t.Struct]) -> t.Struct:
    _, data = foundation.ZCLHeader.deserialize(packet.data.serialize())
    command, rest = schema.deserialize(data)
    assert not rest

    return command


async def commission(app, src_id: int, payload: bytes, **kwargs) -> None:
    app.gp_packet_received(
        make_gp_packet(src_id, GPDCommandID.CommissioningRequest, payload, **kwargs)
    )
    await wait_for_gp_processing()


async def test_permit_join_window(app, manager):
    """Proxies are told to enter commissioning mode for the window, then to exit."""
    await manager.permit_join(time_s=60)
    assert manager.is_commissioning

    await manager.permit_join(time_s=0)
    assert not manager.is_commissioning

    enter, exit_ = [
        sent_command(c.args[0], ProxyCommissioningModeSchema)
        for c in app.send_packet.mock_calls
    ]

    assert enter.options.enter
    assert enter.options.exit_mode == ProxyCommissioningModeExitMode.OnExplicitExit
    assert enter.window == 60
    assert not exit_.options.enter
    assert exit_.window is None


async def test_permit_join_window_expires(app, manager):
    """Proxies leave commissioning mode on their own when the window expires."""
    with freezegun.freeze_time() as frozen:
        await manager.permit_join(time_s=60)
        app.send_packet.reset_mock()

        frozen.tick(61)
        assert not manager.is_commissioning

        await commission(app, 0x11223344, b"\x02\x00")

    assert synthetic_ieee(0x11223344) not in app.devices
    assert len(app.send_packet.mock_calls) == 0


async def test_permit_join_send_failure(app, manager):
    """The window is not opened if the proxies could not be told about it."""
    app.send_packet = AsyncMock(side_effect=TimeoutError)

    with pytest.raises(TimeoutError):
        await manager.permit_join(time_s=60)

    assert not manager.is_commissioning


async def test_commissioning_window_closed(app, manager):
    await commission(app, 0x11223344, b"\x02\x00")

    assert synthetic_ieee(0x11223344) not in app.devices
    assert len(app.device_initialized.mock_calls) == 0


@pytest.mark.parametrize(
    ("payload", "frame_counter", "expected"),
    [
        # Minimal: DeviceID only. An unprotected GPD has no security frame counter, the
        # GPDF's MAC sequence number is used instead
        (
            b"\x02\x00",
            5,
            {
                "device_id": DeviceID.OnOffSwitch,
                "security_level": SecurityLevel.NoSecurity,
                "security_key_type": SecurityKeyType.NoKey,
                "security_key": None,
                "frame_counter": 5,
            },
        ),
        # Extended options 0xA3: Encrypted, NoKey, key in the clear, outgoing counter
        (
            b"\x02\x80\xa3" + KEY + struct.pack("<I", 7),
            1,
            {
                "security_level": SecurityLevel.Encrypted,
                "security_key_type": SecurityKeyType.NoKey,
                "security_key": t.KeyData(KEY),
                "frame_counter": 7,
            },
        ),
        # Extended options 0xE3: as above, but the key is protected with the TC-LK
        (
            b"\x02\x80\xe3" + ENCRYPTED_KEY + KEY_MIC + struct.pack("<I", 7),
            1,
            {"security_key": t.KeyData(KEY), "frame_counter": 7},
        ),
        # An outgoing counter of 0 is a valid counter, not an absent one
        (
            b"\x02\x80\x80" + struct.pack("<I", 0),
            999,
            {"frame_counter": 0},
        ),
        # Options 0x04: app info present; app info 0x10: switch information present.
        # Switch information: length 2, 2 contacts as a button, no contacts closed
        (
            b"\x07\x04\x10\x02\x12\x00",
            1,
            {
                "device_id": DeviceID.GenericSwitch,
                "switch_configuration": GPGenericSwitchConfiguration(
                    num_contacts=2, switch_type=SwitchType.Button, _reserved=0
                ),
            },
        ),
        # Options 0xC2: RxOn capable, fixed location
        (
            b"\x02\xc2\x00",
            1,
            {"rx_on_capability": True, "fixed_location": True},
        ),
    ],
)
async def test_commissioning(app, manager, payload, frame_counter, expected):
    await manager.permit_join(time_s=60)

    await commission(app, 0x11223344, payload, frame_counter=frame_counter)

    dev = app.devices[synthetic_ieee(0x11223344)]

    for name, value in expected.items():
        assert getattr(dev, name) == value


@pytest.mark.parametrize(
    ("src_id", "payload"),
    [
        # SrcID 0x00000000 is unspecified (A.1.4.1.4)
        (0x00000000, b"\x02\x00"),
        # Truncated payload
        (0x11223344, b"\xff"),
        # The reserved security level 0b01 has no defined processing (A.1.4.1.3)
        (0x11223344, b"\x02\x80\x01"),
        # A protected GPD must announce its frame counter (A.3.9.2.1.2)
        (0x11223344, b"\x02\x80\x32" + KEY),
        (0x11223344, b"\x02\x80\x33" + KEY),
        # The key MIC does not verify
        (0x11223344, b"\x02\x80\xe3" + KEY + b"\xad\xde\xad\xde" + b"\x07\x00\x00\x00"),
    ],
)
async def test_commissioning_rejected(app, manager, src_id, payload):
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await commission(app, src_id, payload)

    assert synthetic_ieee(src_id) not in app.devices
    assert len(app.send_packet.mock_calls) == 0


async def test_commissioning_registers_and_pairs(app, manager):
    """A new GPD joins, and proxies are paired in derived groupcast mode."""
    app.subscribe_to_multicast_group = AsyncMock(wraps=app.subscribe_to_multicast_group)

    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await commission(app, 0xAABBCCDD, b"\x02\x00")

    dev = app.devices[synthetic_ieee(0xAABBCCDD)]
    assert call("device_joined", dev) in app.listener_event.mock_calls
    assert app.device_initialized.mock_calls == [call(dev)]

    # The DGroupID is derived from the GPD ID like the alias (A.3.6.1.4), and the sink
    # joins it to receive the groupcast GP Notifications
    group = derive_alias(SrcID(0xAABBCCDD))
    assert app.subscribe_to_multicast_group.mock_calls == [
        call(group, endpoint_id=GP_ENDPOINT)
    ]

    [packet] = [c.args[0] for c in app.send_packet.mock_calls]
    pairing = sent_command(packet, PairingSchema)

    assert pairing.options.add_sink
    assert pairing.options.communication_mode == (
        CommunicationMode.GroupcastForwardToDGroup
    )
    assert pairing.gpd_id == 0xAABBCCDD
    assert pairing.sink_group == group
    assert pairing.sink_ieee is None
    assert pairing.sink_nwk_addr is None


async def test_commissioning_records_link(app, manager):
    """The commissioning GPDF is the latest reception from the GPD."""
    await manager.permit_join(time_s=60)

    packet = make_gp_packet(
        0x11223344, GPDCommandID.CommissioningRequest, b"\x02\x00"
    ).replace(
        timestamp=datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC),
        lqi=t.uint8_t(170),
        rssi=t.int8s(-70),
    )

    app.gp_packet_received(packet)
    await wait_for_gp_processing()

    dev = app.devices[synthetic_ieee(0x11223344)]
    assert dev.last_seen == packet.timestamp.timestamp()
    assert dev.lqi == 170
    assert dev.rssi == -70


async def test_recommissioning_replaces_device(app, manager):
    """Re-commissioning swaps the device object, announced like a re-interview."""
    await manager.permit_join(time_s=60)

    await commission(app, 0x12345678, b"\x02\x00")

    old_device = app.devices[synthetic_ieee(0x12345678)]
    old_task = old_device.create_task(asyncio.Event().wait())

    await commission(app, 0x12345678, b"\x07\x00", frame_counter=2)

    new_device = app.devices[synthetic_ieee(0x12345678)]
    assert new_device is not old_device
    assert new_device.device_id == DeviceID.GenericSwitch

    # The old device object is cleaned up
    await asyncio.sleep(0)
    assert old_task.cancelled()

    assert app.device_initialized.mock_calls == [call(old_device)]
    assert call("device_reinterviewed", new_device) in app.listener_event.mock_calls
    assert call("device_joined", new_device) not in app.listener_event.mock_calls


@pytest.mark.parametrize(
    ("options", "rx_after_tx", "gpp_short_addr", "temp_master"),
    [
        # RxAfterTx, tunneled by a proxy
        (0x82, True, 0x5678, 0x5678),
        # RxAfterTx, received directly by the coordinator
        (0x82, True, None, 0x0000),
        # RxAfterTx without RxOnCapability still gets a reply (A.3.9.1 13.j)
        (0x80, True, 0x5678, 0x5678),
        # RxOnCapability without RxAfterTx: the GPD is not listening
        (0x82, False, 0x5678, None),
        (0x80, False, 0x5678, None),
    ],
)
async def test_commissioning_reply(
    app, manager, options, rx_after_tx, gpp_short_addr, temp_master
):
    """A GPD listening after its GPDF gets a reply through the proxy that tunneled it."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await commission(
        app,
        0xAABBCCDD,
        bytes([0x02, options, 0x00]),
        gpp_short_addr=gpp_short_addr,
        rx_after_tx=rx_after_tx,
    )

    *replies, _ = [c.args[0] for c in app.send_packet.mock_calls]

    if temp_master is None:
        assert replies == []
        return

    [reply] = replies
    response = sent_command(reply, ResponseSchema)
    assert response.temp_master_short_addr == temp_master
    assert response.gpd_command_id == GPDCommandID.CommissioningReply
    GPCommissioningReplyPayload.deserialize(response.gpd_command_payload)


@pytest.mark.parametrize(
    ("payload", "security_level", "security_key_type"),
    [
        # No extended options: an unprotected GPD
        (
            b"\x02\x00",
            SecurityLevel.NoSecurity,
            SecurityKeyType.NoKey,
        ),
        # Extended options 0xA3: Encrypted, NoKey, key in the clear, outgoing counter
        (
            b"\x02\x80\xa3" + KEY + struct.pack("<I", 7),
            SecurityLevel.Encrypted,
            SecurityKeyType.NoKey,
        ),
        # Extended options 0xA2: FullFrameCounterAndMIC, NoKey
        (
            b"\x02\x80\xa2" + KEY + struct.pack("<I", 7),
            SecurityLevel.FullFrameCounterAndMIC,
            SecurityKeyType.NoKey,
        ),
        # Extended options 0xF3: Encrypted, IndividualKey, key protected with the TC-LK
        (
            b"\x02\x80\xf3" + ENCRYPTED_KEY + KEY_MIC + struct.pack("<I", 7),
            SecurityLevel.Encrypted,
            SecurityKeyType.IndividualKey,
        ),
    ],
)
async def test_commissioning_reply_options(
    app, manager, payload, security_level, security_key_type
):
    """The reply echoes the GPD's security level and key type (A.3.9.1 13.j.i)."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await commission(app, 0x11223344, payload, rx_after_tx=True)

    reply, _ = [c.args[0] for c in app.send_packet.mock_calls]
    response = sent_command(reply, ResponseSchema)
    command, rest = GPCommissioningReplyPayload.deserialize(
        response.gpd_command_payload
    )

    assert not rest
    assert command.options.security_level == security_level
    assert command.options.key_type == security_key_type
    assert not command.options.pan_id_present
    assert not command.options.security_key_present


async def test_duplicate_commissioning_dropped(app, manager):
    """The same commissioning GPDF forwarded by two proxies is processed once."""
    await manager.permit_join(time_s=60)

    packet = make_gp_packet(0xEEEE5555, GPDCommandID.CommissioningRequest, b"\x02\x00")

    app.gp_packet_received(packet)
    await wait_for_gp_processing()
    app.gp_packet_received(packet)
    await wait_for_gp_processing()

    assert len(app.device_initialized.mock_calls) == 1


async def test_ieee_addressing_ignored(app, manager):
    """Commissioning GPDFs from IEEE-addressed GPDs are not supported."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    app.gp_packet_received(
        t.ZigbeeGpPacket(
            application_id=ApplicationID.IEEE,
            ieee=t.EUI64.convert("11:22:33:44:55:66:77:88"),
            endpoint=t.uint8_t(1),
            command_id=GPDCommandID.CommissioningRequest,
            payload=t.SerializableBytes(b"\x02\x00"),
            frame_counter=t.uint32_t(1),
        )
    )
    await wait_for_gp_processing()

    assert len(app.device_initialized.mock_calls) == 0
    assert len(app.send_packet.mock_calls) == 0


async def test_success_report_ignored(app, manager):
    app.gp_packet_received(make_gp_packet(0xDDDD4444, GPDCommandID.SuccessReport))
    await wait_for_gp_processing()

    assert synthetic_ieee(0xDDDD4444) not in app.devices
    assert len(app.send_packet.mock_calls) == 0


@pytest.mark.parametrize(
    ("channel", "next_channel", "gpp_short_addr", "temp_master"),
    [
        (20, 15, 0x1234, 0x1234),
        (15, 25, None, 0x0000),
    ],
)
async def test_channel_request(
    app, manager, channel, next_channel, gpp_short_addr, temp_master
):
    """A Channel Request is answered with the operational channel, on the GPD's."""
    app.state.network_info.channel = channel
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    # Channel Request: next channel, then second next channel 26
    app.gp_packet_received(
        make_gp_packet(
            0x12345678,
            GPDCommandID.ChannelRequest,
            bytes([(next_channel - 11) | (15 << 4)]),
            gpp_short_addr=gpp_short_addr,
        )
    )
    await wait_for_gp_processing()

    [packet] = [c.args[0] for c in app.send_packet.mock_calls]
    response = sent_command(packet, ResponseSchema)

    assert response.temp_master_short_addr == temp_master
    assert response.temp_master_tx_channel.transmit_channel == next_channel - 11
    assert response.gpd_command_id == GPDCommandID.ChannelConfiguration

    configuration, _ = GPChannelConfigurationPayload.deserialize(
        response.gpd_command_payload
    )
    assert configuration.operational_channel == channel - 11
    assert configuration.basic


async def test_channel_request_window_closed(app, manager):
    """A Channel Request outside of commissioning mode is dropped (A.3.9.1 7.a)."""
    app.gp_packet_received(
        make_gp_packet(0x12345678, GPDCommandID.ChannelRequest, b"\x00")
    )
    await wait_for_gp_processing()

    assert len(app.send_packet.mock_calls) == 0


async def test_channel_request_invalid(app, manager):
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    app.gp_packet_received(make_gp_packet(0x12345678, GPDCommandID.ChannelRequest, b""))
    await wait_for_gp_processing()

    assert len(app.send_packet.mock_calls) == 0


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
    dev.security_key = t.KeyData(KEY)
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

    if not removed:
        assert len(app.send_packet.mock_calls) == 0
        return

    [packet] = [c.args[0] for c in app.send_packet.mock_calls]
    pairing = sent_command(packet, PairingSchema)
    assert pairing.options.remove_gpd
    assert pairing.gpd_id == 0x12345678


async def test_decommissioning_unknown_device(app, manager):
    """Decommissioning from an unknown GPD is ignored."""
    app.gp_packet_received(
        make_gp_packet(0xDEADBEEF, GPDCommandID.DecommissioningRequest)
    )
    await wait_for_gp_processing()

    assert len(app.send_packet.mock_calls) == 0


@pytest.mark.parametrize(
    ("other_src_id", "unsubscribed"),
    [
        # No other GPD uses the group
        (0x44445555, True),
        # Another GPD derives the same group
        (0x33332222, False),
    ],
)
async def test_decommissioning_leaves_derived_group(
    app, manager, other_src_id, unsubscribed
):
    """The sink leaves a derived group once no commissioned GPD uses it."""
    app.unsubscribe_from_multicast_group = AsyncMock(
        wraps=app.unsubscribe_from_multicast_group
    )

    for src_id in (0x11112222, other_src_id):
        dev = GreenPowerDevice(
            app, application_id=ApplicationID.SrcID, src_id=SrcID(src_id)
        )
        dev.security_level = SecurityLevel.NoSecurity
        dev.security_key_type = SecurityKeyType.NoKey
        app.devices[dev.ieee] = dev

    manager.decommission(app.devices[synthetic_ieee(0x11112222)])
    await wait_for_gp_processing()

    assert synthetic_ieee(0x11112222) not in app.devices
    assert app.unsubscribe_from_multicast_group.mock_calls == (
        [call(t.Group(0x2222), endpoint_id=GP_ENDPOINT)] if unsubscribed else []
    )


async def test_startup_joins_derived_groups(app, manager):
    """Every commissioned GPD's derived group is joined once on startup."""
    app.subscribe_to_multicast_group = AsyncMock(wraps=app.subscribe_to_multicast_group)

    # The first two GPDs derive the same group
    for src_id in (0x11112222, 0x33332222, 0x44445555):
        dev = GreenPowerDevice(
            app, application_id=ApplicationID.SrcID, src_id=SrcID(src_id)
        )
        app.devices[dev.ieee] = dev

    await manager.startup()

    assert app.subscribe_to_multicast_group.mock_calls == [
        call(t.Group(0x2222), endpoint_id=GP_ENDPOINT),
        call(t.Group(0x5555), endpoint_id=GP_ENDPOINT),
    ]


async def test_shutdown(app, manager):
    """Shutdown closes the window and cancels commissioning still in progress."""
    await manager.permit_join(time_s=60)

    app.gp_packet_received(
        make_gp_packet(0x11223344, GPDCommandID.CommissioningRequest, b"\x02\x00")
    )
    await manager.shutdown()

    assert not manager.is_commissioning
    assert synthetic_ieee(0x11223344) not in app.devices


@pytest.mark.parametrize(
    ("security_level", "mac_seq_num_capability", "frame_counter"),
    [
        (SecurityLevel.NoSecurity, False, None),
        (SecurityLevel.NoSecurity, True, 1234),
        (SecurityLevel.FullFrameCounterAndMIC, False, 1234),
        (SecurityLevel.Encrypted, False, 1234),
    ],
)
async def test_pairing_frame_counter_presence(
    app, manager, security_level, mac_seq_num_capability, frame_counter
):
    """The frame counter is only sent if the GPD has one to check (A.3.3.5.2)."""
    dev = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    dev.device_id = DeviceID.OnOffSwitch
    dev.mac_seq_num_capability = mac_seq_num_capability
    dev.security_level = security_level
    dev.security_key_type = SecurityKeyType.NoKey
    dev.frame_counter = t.uint32_t(1234)

    await manager.send_pairing(dev, add_sink=True)

    pairing = sent_command(app.send_packet.mock_calls[0].args[0], PairingSchema)

    assert pairing.options.security_frame_counter_present == (frame_counter is not None)
    assert pairing.frame_counter == frame_counter


async def test_pairing_carries_key_in_the_clear(app, manager):
    """GP Pairing carries the Sink Table key as-is, proxies store it unmodified."""
    dev = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    dev.device_id = DeviceID.OnOffSwitch
    dev.security_key = t.KeyData(KEY)
    dev.security_level = SecurityLevel.Encrypted
    dev.security_key_type = SecurityKeyType.IndividualKey
    dev.frame_counter = t.uint32_t(0)

    await manager.send_pairing(dev, add_sink=True)

    pairing = sent_command(app.send_packet.mock_calls[0].args[0], PairingSchema)

    assert pairing.options.security_key_present
    assert pairing.options.security_level == SecurityLevel.Encrypted
    assert pairing.options.security_key_type == SecurityKeyType.IndividualKey
    assert pairing.key == t.KeyData(KEY)


async def open_window(app, manager) -> None:
    await manager.permit_join(time_s=60)


async def request_channel(app, manager) -> None:
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    app.gp_packet_received(
        make_gp_packet(0x12345678, GPDCommandID.ChannelRequest, b"\x00")
    )
    await wait_for_gp_processing()


async def pair(app, manager) -> None:
    dev = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    dev.device_id = DeviceID.OnOffSwitch
    dev.security_level = SecurityLevel.NoSecurity
    dev.security_key_type = SecurityKeyType.NoKey

    await manager.send_pairing(dev, add_sink=True)


@pytest.mark.parametrize(
    ("send", "command"),
    [
        (open_window, GreenPowerProxy.ClientCommandDefs.proxy_commissioning_mode),
        (request_channel, GreenPowerProxy.ClientCommandDefs.response),
        # Read client-to-server, 0x01 would be a GP Pairing Search
        (pair, GreenPowerProxy.ClientCommandDefs.pairing),
    ],
)
async def test_commands_sent_server_to_client(app, manager, send, command):
    """The sink is the GP cluster server, so commands to proxies are server-to-client."""
    await send(app, manager)

    [packet] = [c.args[0] for c in app.send_packet.mock_calls]
    hdr, _ = foundation.ZCLHeader.deserialize(packet.data.serialize())

    assert packet.dst.addr_mode == t.AddrMode.Broadcast
    assert packet.src_ep == packet.dst_ep == GP_ENDPOINT
    assert hdr.frame_control.frame_type == foundation.FrameType.CLUSTER_COMMAND
    assert hdr.direction == foundation.Direction.Server_to_Client
    assert hdr.frame_control.disable_default_response
    assert hdr.command_id == command.id
    assert hdr.tsn == packet.tsn

    sent_command(packet, command.schema)
