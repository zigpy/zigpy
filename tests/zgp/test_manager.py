"""Tests for Green Power Manager."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
from unittest.mock import call

import freezegun
import pytest

from tests.async_mock import AsyncMock
from tests.zgp.conftest import (
    COMMISSIONING_NOTIFICATION_ID,
    KEY,
    commission,
    commissioning_payload,
    encrypted_gp_packet,
    make_commissioning_options,
    make_gp_packet,
    make_tunnel_packet,
    sent_command,
    wait_for_gp_processing,
)
from zigpy.device import GreenPowerDevice
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.greenpower import (
    CommissioningNotificationSchema,
    GreenPowerProxy,
    PairingSchema,
    ProxyCommissioningModeSchema,
    ResponseSchema,
)
import zigpy.zdo.types as zdo_types
from zigpy.zgp.commands import (
    GPChannelConfigurationPayload,
    GPChannelRequestPayload,
    GPCommissioningReplyPayload,
    GPGenericSwitchConfiguration,
    GPSwitchInformation,
)
from zigpy.zgp.crypto import build_gpdf_header, encrypt_payload, encrypt_security_key
from zigpy.zgp.manager import derived_group
from zigpy.zgp.types import (
    GP_ENDPOINT,
    ApplicationID,
    CommunicationMode,
    DeviceID,
    GPDCommandID,
    GPDCommandPayload,
    GPLinkQuality,
    GPPGPDLink,
    ProxyCommissioningModeExitMode,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SrcID,
    SwitchType,
)
from zigpy.zgp.util import derive_alias, synthetic_ieee

ENCRYPTED_KEY, _mic = encrypt_security_key(0x11223344, KEY)
KEY_MIC = int.from_bytes(_mic, "little")

ENCRYPTED_COMMISSIONING = commissioning_payload(
    security_level=SecurityLevel.Encrypted,
    key_type=SecurityKeyType.IndividualKey,
    key=KEY,
    outgoing_counter=7,
)
UNPROTECTED_COMMISSIONING = commissioning_payload()


def encrypted_success_packet(
    src_id: int, frame_counter: int, key: bytes = KEY
) -> t.ZigbeeGpPacket:
    return encrypted_gp_packet(
        src_id, frame_counter, bytes([GPDCommandID.SuccessReport]), key
    )


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


async def test_permit_join_send_failure(app, manager):
    """The window is not opened if the proxies could not be told about it."""
    app.send_packet = AsyncMock(side_effect=TimeoutError)

    with pytest.raises(TimeoutError):
        await manager.permit_join(time_s=60)

    assert not manager.is_commissioning


async def test_commissioning_window_closed(app, manager):
    await commission(app, 0x11223344, UNPROTECTED_COMMISSIONING)

    assert synthetic_ieee(0x11223344) not in app.devices
    assert len(app.device_initialized.mock_calls) == 0


@pytest.mark.parametrize(
    ("payload", "frame_counter", "expected"),
    [
        # Minimal: DeviceID only. An unprotected GPD has no security frame counter, the
        # GPDF's MAC sequence number is used instead
        (
            UNPROTECTED_COMMISSIONING,
            5,
            {
                "device_id": DeviceID.OnOffSwitch,
                "security_level": SecurityLevel.NoSecurity,
                "security_key_type": SecurityKeyType.NoKey,
                "security_key": None,
                "frame_counter": 5,
            },
        ),
        # Key in the clear
        (
            commissioning_payload(
                security_level=SecurityLevel.Encrypted, key=KEY, outgoing_counter=7
            ),
            1,
            {
                "security_level": SecurityLevel.Encrypted,
                "security_key_type": SecurityKeyType.NoKey,
                "security_key": t.KeyData(KEY),
                "frame_counter": 7,
            },
        ),
        # Key protected with the TC-LK
        (
            commissioning_payload(
                security_level=SecurityLevel.Encrypted,
                key=ENCRYPTED_KEY,
                key_mic=KEY_MIC,
                outgoing_counter=7,
            ),
            1,
            {"security_key": t.KeyData(KEY), "frame_counter": 7},
        ),
        # An outgoing counter of 0 is a valid counter, not an absent one
        (
            commissioning_payload(
                security_level=SecurityLevel.FullFrameCounterAndMIC,
                key=KEY,
                outgoing_counter=0,
            ),
            999,
            {"frame_counter": 0},
        ),
        # The security fields of an unprotected GPD are ignored (A.4.2.1.1.3)
        (
            commissioning_payload(
                security_level=SecurityLevel.NoSecurity,
                key_type=SecurityKeyType.IndividualKey,
                key=KEY,
                outgoing_counter=7,
            ),
            5,
            {
                "security_level": SecurityLevel.NoSecurity,
                "security_key_type": SecurityKeyType.NoKey,
                "security_key": None,
                "frame_counter": 5,
            },
        ),
        # Switch information: 2 contacts as a button, no contacts closed
        (
            commissioning_payload(
                DeviceID.GenericSwitch,
                switch_information=GPSwitchInformation(
                    configuration=GPGenericSwitchConfiguration(
                        num_contacts=2, switch_type=SwitchType.Button, _reserved=0
                    ),
                    contact_status=t.bitmap8(0),
                ),
            ),
            1,
            {
                "device_id": DeviceID.GenericSwitch,
                "switch_configuration": GPGenericSwitchConfiguration(
                    num_contacts=2, switch_type=SwitchType.Button, _reserved=0
                ),
            },
        ),
        (
            commissioning_payload(
                security_level=SecurityLevel.NoSecurity,
                rx_on_capability=1,
                fixed_location=1,
            ),
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
        (0x00000000, UNPROTECTED_COMMISSIONING),
        # Truncated payload: a DeviceID without Options
        (0x11223344, b"\xff"),
        # The reserved security level 0b01 has no defined processing (A.1.4.1.3)
        (0x11223344, commissioning_payload(security_level=SecurityLevel.Reserved)),
        # A protected GPD must announce its frame counter (A.3.9.2.1.2)
        (
            0x11223344,
            commissioning_payload(
                security_level=SecurityLevel.FullFrameCounterAndMIC,
                key_type=SecurityKeyType.IndividualKey,
                key=KEY,
            ),
        ),
        (
            0x11223344,
            commissioning_payload(
                security_level=SecurityLevel.Encrypted,
                key_type=SecurityKeyType.IndividualKey,
                key=KEY,
            ),
        ),
        # The key MIC does not verify
        (
            0x11223344,
            commissioning_payload(
                security_level=SecurityLevel.Encrypted,
                key=ENCRYPTED_KEY,
                key_mic=0xDEADDEAD,
                outgoing_counter=7,
            ),
        ),
        # A protected GPD without a key (A.3.9.1 step 13.g)
        (
            0x11223344,
            commissioning_payload(
                security_level=SecurityLevel.Encrypted,
                key_type=SecurityKeyType.IndividualKey,
                outgoing_counter=7,
            ),
        ),
        (
            0x11223344,
            commissioning_payload(
                security_level=SecurityLevel.FullFrameCounterAndMIC,
                key_type=SecurityKeyType.IndividualKey,
                outgoing_counter=7,
            ),
        ),
        # Requesting a key does not help, this sink provisions none
        (
            0x11223344,
            commissioning_payload(
                security_level=SecurityLevel.Encrypted,
                key_type=SecurityKeyType.IndividualKey,
                outgoing_counter=7,
                security_key_request=1,
            ),
        ),
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
    app.state.network_info.security_level = 5

    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await commission(app, 0xAABBCCDD, UNPROTECTED_COMMISSIONING)

    dev = app.devices[synthetic_ieee(0xAABBCCDD)]
    assert call("device_joined", dev) in app.listener_event.mock_calls
    assert app.device_initialized.mock_calls == [call(dev)]

    # The DGroupID is derived from the GPD ID like the alias (A.3.6.1.4), and the sink
    # joins it to receive the groupcast GP Notifications
    group = derive_alias(SrcID(0xAABBCCDD))
    assert app.subscribe_to_multicast_group.mock_calls == [
        call(group, endpoint_id=GP_ENDPOINT)
    ]

    # The alias is announced before the proxies are paired (A.3.9.1 19.e-f)
    [annce, packet] = [c.args[0] for c in app.send_packet.mock_calls]

    assert annce.cluster_id == zdo_types.ZDOCmd.Device_annce
    assert annce.profile_id == 0
    assert annce.src_ep == 0
    assert annce.dst_ep == 0
    assert annce.dst.address == t.BroadcastAddress.RX_ON_WHEN_IDLE
    # Sent as the alias itself, with a fixed sequence number (A.3.6.3.4.2)
    assert annce.alias_src == group
    assert annce.alias_seq == 0
    assert annce.tsn == 0

    # The ZDO TSN, then an invalid IEEE address and the security capability
    tsn, data = t.uint8_t.deserialize(annce.data.serialize())
    assert tsn == 0
    assert t.deserialize(
        data, zdo_types.CLUSTERS[zdo_types.ZDOCmd.Device_annce][1]
    ) == (
        [group, t.EUI64.UNKNOWN, zdo_types.MACCapabilityFlags.SecurityCapable],
        b"",
    )

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
        0x11223344, GPDCommandID.CommissioningRequest, UNPROTECTED_COMMISSIONING
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


async def test_device_annce_only_on_first_commissioning(app, manager):
    """A re-commissioned GPD already occupies its alias (A.3.9.1 19.e)."""
    await manager.permit_join(time_s=60)
    await commission(app, 0xAABBCCDD, UNPROTECTED_COMMISSIONING)
    app.send_packet.reset_mock()

    await commission(app, 0xAABBCCDD, UNPROTECTED_COMMISSIONING, frame_counter=2)

    [packet] = [c.args[0] for c in app.send_packet.mock_calls]
    assert packet.alias_src is None
    assert sent_command(packet, PairingSchema).options.add_sink


async def test_device_annce_unsupported(app, manager, caplog):
    """A radio that cannot send as an alias announces the alias as itself."""

    async def send_packet(packet: t.ZigbeePacket) -> None:
        if packet.alias_src is not None:
            raise NotImplementedError

    app.send_packet = AsyncMock(side_effect=send_packet)

    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    with caplog.at_level(logging.DEBUG):
        await commission(app, 0xAABBCCDD, UNPROTECTED_COMMISSIONING)

    assert synthetic_ieee(0xAABBCCDD) in app.devices
    assert "announcing 0xCCDD as ourselves" in caplog.text

    [aliased, fallback, pairing] = [c.args[0] for c in app.send_packet.mock_calls]
    assert aliased.alias_src == derive_alias(SrcID(0xAABBCCDD))
    # The payload is the same, only the aliasing is dropped
    assert fallback.alias_src is None
    assert fallback.alias_seq is None
    assert fallback.cluster_id == zdo_types.ZDOCmd.Device_annce
    assert fallback.data == aliased.data
    assert fallback.tsn != 0
    assert sent_command(pairing, PairingSchema).options.add_sink


async def test_recommissioning_replaces_device(app, manager):
    """Re-commissioning swaps the device object, announced like a re-interview."""
    await manager.permit_join(time_s=60)

    await commission(app, 0x12345678, UNPROTECTED_COMMISSIONING)

    old_device = app.devices[synthetic_ieee(0x12345678)]
    old_task = old_device.create_task(asyncio.Event().wait())

    await commission(
        app, 0x12345678, commissioning_payload(DeviceID.GenericSwitch), frame_counter=2
    )

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
    ("security_level", "key", "outgoing_counter", "frame_counter"),
    [
        # A replayed Commissioning GPDF with an older counter keeps the newer one
        (SecurityLevel.Encrypted, KEY, 50, 100),
        (SecurityLevel.Encrypted, KEY, 200, 200),
        (SecurityLevel.FullFrameCounterAndMIC, KEY, 50, 100),
        # Another key is another GPD security context
        (SecurityLevel.Encrypted, bytes(range(16, 32)), 50, 50),
        # An unprotected GPD has no security frame counter, its outgoing counter is
        # ignored and the GPDF's MAC sequence number is kept
        (SecurityLevel.NoSecurity, None, 50, 2),
    ],
)
async def test_recommissioning_keeps_frame_counter(
    app, manager, security_level, key, outgoing_counter, frame_counter
):
    """Re-commissioning cannot lower the replay baseline of a protected GPD."""
    await manager.permit_join(time_s=60)

    await commission(
        app,
        0x11223344,
        commissioning_payload(
            security_level=SecurityLevel.Encrypted, key=KEY, outgoing_counter=100
        ),
    )
    await commission(
        app,
        0x11223344,
        commissioning_payload(
            security_level=security_level, key=key, outgoing_counter=outgoing_counter
        ),
        frame_counter=2,
    )

    assert app.devices[synthetic_ieee(0x11223344)].frame_counter == frame_counter


@pytest.mark.parametrize(
    ("payload", "gpp_short_addr", "temp_master", "security_level", "security_key_type"),
    [
        # Tunneled by a proxy. RxAfterTx without RxOnCapability still gets a reply
        # (A.3.9.1 13.j)
        (
            UNPROTECTED_COMMISSIONING,
            0x5678,
            0x5678,
            SecurityLevel.NoSecurity,
            SecurityKeyType.NoKey,
        ),
        # Received directly by the coordinator
        (
            UNPROTECTED_COMMISSIONING,
            None,
            0x0000,
            SecurityLevel.NoSecurity,
            SecurityKeyType.NoKey,
        ),
        (
            commissioning_payload(
                security_level=SecurityLevel.NoSecurity, rx_on_capability=1
            ),
            0x5678,
            0x5678,
            SecurityLevel.NoSecurity,
            SecurityKeyType.NoKey,
        ),
        (
            commissioning_payload(
                security_level=SecurityLevel.Encrypted, key=KEY, outgoing_counter=7
            ),
            0x5678,
            0x5678,
            SecurityLevel.Encrypted,
            SecurityKeyType.NoKey,
        ),
        (
            commissioning_payload(
                security_level=SecurityLevel.FullFrameCounterAndMIC,
                key=KEY,
                outgoing_counter=7,
            ),
            0x5678,
            0x5678,
            SecurityLevel.FullFrameCounterAndMIC,
            SecurityKeyType.NoKey,
        ),
        # Key protected with the TC-LK
        (
            commissioning_payload(
                security_level=SecurityLevel.Encrypted,
                key_type=SecurityKeyType.IndividualKey,
                key=ENCRYPTED_KEY,
                key_mic=KEY_MIC,
                outgoing_counter=7,
            ),
            0x5678,
            0x5678,
            SecurityLevel.Encrypted,
            SecurityKeyType.IndividualKey,
        ),
    ],
)
async def test_commissioning_reply(
    app,
    manager,
    payload,
    gpp_short_addr,
    temp_master,
    security_level,
    security_key_type,
):
    """A listening GPD gets a reply echoing its security, via its proxy (A.3.9.1 13.j)."""
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await commission(
        app, 0x11223344, payload, gpp_short_addr=gpp_short_addr, rx_after_tx=True
    )

    # The GPD is paired once its Success GPDF arrives
    [reply] = [c.args[0] for c in app.send_packet.mock_calls]
    response = sent_command(reply, ResponseSchema)
    assert response.temp_master_short_addr == temp_master
    assert response.gpd_command_id == GPDCommandID.CommissioningReply

    command, rest = GPCommissioningReplyPayload.deserialize(
        response.gpd_command_payload
    )

    assert not rest
    assert command.options.security_level == security_level
    assert command.options.key_type == security_key_type
    assert not command.options.pan_id_present
    assert not command.options.security_key_present


@pytest.mark.parametrize(
    ("payload", "success", "repeated_success"),
    [
        (
            UNPROTECTED_COMMISSIONING,
            make_gp_packet(0x11223344, GPDCommandID.SuccessReport, frame_counter=2),
            make_gp_packet(0x11223344, GPDCommandID.SuccessReport, frame_counter=3),
        ),
        (
            ENCRYPTED_COMMISSIONING,
            encrypted_success_packet(0x11223344, 8),
            encrypted_success_packet(0x11223344, 9),
        ),
    ],
)
async def test_bidirectional_commissioning(
    app, manager, payload, success, repeated_success
):
    """A GPD listening for a reply is paired once its Success GPDF arrives (A.3.9.1)."""
    app.subscribe_to_multicast_group = AsyncMock(wraps=app.subscribe_to_multicast_group)

    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    await commission(app, 0x11223344, payload, rx_after_tx=True)

    # Only the Commissioning Reply is sent, the GPD is not registered yet
    [reply] = [c.args[0] for c in app.send_packet.mock_calls]
    assert sent_command(reply, ResponseSchema).gpd_command_id == (
        GPDCommandID.CommissioningReply
    )
    assert synthetic_ieee(0x11223344) not in app.devices
    assert len(app.device_initialized.mock_calls) == 0
    assert len(app.subscribe_to_multicast_group.mock_calls) == 0
    app.send_packet.reset_mock()

    app.gp_packet_received(success)
    await wait_for_gp_processing()

    dev = app.devices[synthetic_ieee(0x11223344)]
    assert app.device_initialized.mock_calls == [call(dev)]
    assert app.subscribe_to_multicast_group.mock_calls == [
        call(derived_group(dev), endpoint_id=GP_ENDPOINT)
    ]

    [_, packet] = [c.args[0] for c in app.send_packet.mock_calls]
    assert sent_command(packet, PairingSchema).options.add_sink
    app.send_packet.reset_mock()

    # The GPD can repeat its Success GPDF with an incremented frame counter
    app.gp_packet_received(repeated_success)
    await wait_for_gp_processing()

    assert len(app.send_packet.mock_calls) == 0
    assert app.device_initialized.mock_calls == [call(dev)]


@pytest.mark.parametrize(
    "success",
    [
        # Not the commissioned key
        encrypted_success_packet(0x11223344, 8, key=bytes(16)),
        # Not fresher than the outgoing counter of the Commissioning GPDF (A.3.9.2)
        encrypted_success_packet(0x11223344, 7),
        # Not protected as agreed
        make_gp_packet(0x11223344, GPDCommandID.SuccessReport, frame_counter=8),
    ],
)
async def test_bidirectional_commissioning_success_rejected(app, manager, success):
    """A Success GPDF that fails its checks does not finish commissioning."""
    await manager.permit_join(time_s=60)
    await commission(app, 0x11223344, ENCRYPTED_COMMISSIONING, rx_after_tx=True)
    app.send_packet.reset_mock()

    app.gp_packet_received(success)
    await wait_for_gp_processing()

    assert synthetic_ieee(0x11223344) not in app.devices
    assert len(app.send_packet.mock_calls) == 0


def tunneled_success_packet(
    src_id: int,
    frame_counter: int,
    security_level: SecurityLevel,
    key: bytes = KEY,
) -> t.ZigbeePacket:
    """A protected Success GPDF forwarded by a proxy that could not verify it.

    The proxy is not paired with the GPD yet, so it forwards the GPDF unprocessed in
    a GP Commissioning Notification with its MIC (A.3.9.1 step 17.b.i).
    """
    header = build_gpdf_header(
        src_id,
        frame_counter,
        security_level=security_level,
        individual_key=True,
        auto_commissioning=False,
        rx_after_tx=False,
    )
    ciphertext, mic = encrypt_payload(
        src_id,
        frame_counter,
        key,
        bytes([GPDCommandID.SuccessReport]),
        header=header,
        security_level=security_level,
    )

    command = CommissioningNotificationSchema(
        options=make_commissioning_options(
            security_level=security_level,
            # The proxy reports the derived individual key type for an individual
            # key it does not have (A.3.9.2.1.1)
            security_key_type=SecurityKeyType.DerivedIndividual,
            security_failed=1,
        ),
        gpd_id=src_id,
        frame_counter=frame_counter,
        command_id=GPDCommandID(ciphertext[0]),
        payload=GPDCommandPayload(ciphertext[1:]),
        gpp_short_addr=0x1234,
        gpp_gpd_link=GPPGPDLink(rssi=20, link_quality=GPLinkQuality.High),
        mic=int.from_bytes(mic, "little"),
    )

    return make_tunnel_packet(
        COMMISSIONING_NOTIFICATION_ID,
        command.serialize(),
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x1234),
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
    )


@pytest.mark.parametrize(
    ("payload", "security_level"),
    [
        (ENCRYPTED_COMMISSIONING, SecurityLevel.Encrypted),
        (
            commissioning_payload(
                security_level=SecurityLevel.FullFrameCounterAndMIC,
                key_type=SecurityKeyType.IndividualKey,
                key=KEY,
                outgoing_counter=7,
            ),
            SecurityLevel.FullFrameCounterAndMIC,
        ),
    ],
)
async def test_bidirectional_commissioning_through_proxy(
    app, manager, payload, security_level
):
    """The sink security processes a Success GPDF the forwarding proxy could not."""
    await manager.permit_join(time_s=60)
    await commission(app, 0x11223344, payload, rx_after_tx=True, gpp_short_addr=0x1234)
    app.send_packet.reset_mock()

    app.packet_received(tunneled_success_packet(0x11223344, 8, security_level))
    await wait_for_gp_processing()

    dev = app.devices[synthetic_ieee(0x11223344)]
    assert dev.security_level == security_level
    assert dev.frame_counter == 8
    assert app.device_initialized.mock_calls == [call(dev)]

    [_, packet] = [c.args[0] for c in app.send_packet.mock_calls]
    assert sent_command(packet, PairingSchema).options.add_sink


@pytest.mark.parametrize(
    "security_level",
    [SecurityLevel.Encrypted, SecurityLevel.FullFrameCounterAndMIC],
)
async def test_bidirectional_commissioning_through_proxy_rejected(
    app, manager, security_level
):
    """A tunneled Success GPDF protected with another key is rejected."""
    await manager.permit_join(time_s=60)
    await commission(
        app,
        0x11223344,
        ENCRYPTED_COMMISSIONING,
        rx_after_tx=True,
        gpp_short_addr=0x1234,
    )
    app.send_packet.reset_mock()

    app.packet_received(
        tunneled_success_packet(0x11223344, 8, security_level, key=bytes(16))
    )
    await wait_for_gp_processing()

    assert synthetic_ieee(0x11223344) not in app.devices
    assert len(app.send_packet.mock_calls) == 0


async def close_window(manager, frozen) -> None:
    await manager.permit_join(time_s=0)


async def close_and_reopen_window(manager, frozen) -> None:
    await manager.permit_join(time_s=0)
    await manager.permit_join(time_s=60)


async def expire_window(manager, frozen) -> None:
    frozen.tick(61)


async def expire_and_reopen_window(manager, frozen) -> None:
    frozen.tick(61)
    await manager.permit_join(time_s=60)


async def extend_window(manager, frozen) -> None:
    frozen.tick(30)
    await manager.permit_join(time_s=60)
    frozen.tick(45)


@pytest.mark.parametrize(
    ("change_window", "commissioned"),
    [
        (close_window, False),
        # An explicit close ends commissioning in progress
        (close_and_reopen_window, False),
        # The Success GPDF is only accepted in commissioning mode (A.3.9.1 step 18.a)
        (expire_window, False),
        # A client may keep re-requesting the window, with lapses in between
        (expire_and_reopen_window, True),
        (extend_window, True),
    ],
)
async def test_bidirectional_commissioning_window_changes(
    app, manager, change_window, commissioned
):
    """Commissioning in progress follows the window until its Success GPDF."""
    with freezegun.freeze_time() as frozen:
        await manager.permit_join(time_s=60)
        await commission(app, 0x11223344, ENCRYPTED_COMMISSIONING, rx_after_tx=True)

        await change_window(manager, frozen)

        app.gp_packet_received(encrypted_success_packet(0x11223344, 8))
        await wait_for_gp_processing()

    assert (synthetic_ieee(0x11223344) in app.devices) is commissioned


async def test_bidirectional_recommissioning(app, manager):
    """A re-commissioned GPD keeps its registration until its Success GPDF arrives."""
    await manager.permit_join(time_s=60)
    await commission(app, 0x11223344, UNPROTECTED_COMMISSIONING)
    old_device = app.devices[synthetic_ieee(0x11223344)]

    await commission(
        app, 0x11223344, ENCRYPTED_COMMISSIONING, frame_counter=2, rx_after_tx=True
    )
    assert app.devices[synthetic_ieee(0x11223344)] is old_device

    app.gp_packet_received(encrypted_success_packet(0x11223344, 8))
    await wait_for_gp_processing()

    new_device = app.devices[synthetic_ieee(0x11223344)]
    assert new_device is not old_device
    assert new_device.security_level == SecurityLevel.Encrypted
    assert call("device_reinterviewed", new_device) in app.listener_event.mock_calls


async def test_bidirectional_commissioning_fallback(app, manager):
    """A GPD falling back to unidirectional commissioning is paired right away."""
    await manager.permit_join(time_s=60)
    await commission(app, 0x11223344, ENCRYPTED_COMMISSIONING, rx_after_tx=True)
    await commission(
        app, 0x11223344, ENCRYPTED_COMMISSIONING, frame_counter=2, rx_after_tx=False
    )

    dev = app.devices[synthetic_ieee(0x11223344)]
    assert app.device_initialized.mock_calls == [call(dev)]
    app.send_packet.reset_mock()

    # Its Success GPDF no longer finishes anything
    app.gp_packet_received(encrypted_success_packet(0x11223344, 8))
    await wait_for_gp_processing()

    assert app.devices[synthetic_ieee(0x11223344)] is dev
    assert len(app.send_packet.mock_calls) == 0


async def test_duplicate_commissioning_dropped(app, manager):
    """The same commissioning GPDF forwarded by two proxies is processed once."""
    await manager.permit_join(time_s=60)

    packet = make_gp_packet(
        0xEEEE5555, GPDCommandID.CommissioningRequest, UNPROTECTED_COMMISSIONING
    )

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
            payload=t.SerializableBytes(UNPROTECTED_COMMISSIONING),
            frame_counter=t.uint32_t(1),
        )
    )
    await wait_for_gp_processing()

    assert len(app.device_initialized.mock_calls) == 0
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

    app.gp_packet_received(
        make_gp_packet(
            0x12345678,
            GPDCommandID.ChannelRequest,
            GPChannelRequestPayload(
                next_channel=next_channel - 11, second_next_channel=26 - 11
            ).serialize(),
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
        make_gp_packet(
            0x12345678,
            GPDCommandID.ChannelRequest,
            GPChannelRequestPayload(next_channel=0, second_next_channel=0).serialize(),
        )
    )
    await wait_for_gp_processing()

    assert len(app.send_packet.mock_calls) == 0


async def test_channel_request_invalid(app, manager):
    await manager.permit_join(time_s=60)
    app.send_packet.reset_mock()

    app.gp_packet_received(make_gp_packet(0x12345678, GPDCommandID.ChannelRequest, b""))
    await wait_for_gp_processing()

    assert len(app.send_packet.mock_calls) == 0


def add_secured_gpd(app) -> GreenPowerDevice:
    dev = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    dev.device_id = DeviceID.OnOffSwitch
    dev.security_key = t.KeyData(KEY)
    dev.security_level = SecurityLevel.FullFrameCounterAndMIC
    dev.security_key_type = SecurityKeyType.IndividualKey
    dev.frame_counter = t.uint32_t(10)
    app.devices[dev.ieee] = dev

    return dev


def decommissioning_packet(**kwargs) -> t.ZigbeeGpPacket:
    return t.ZigbeeGpPacket(
        **{
            "application_id": ApplicationID.SrcID,
            "src_id": SrcID(0x12345678),
            "command_id": GPDCommandID.DecommissioningRequest,
            "frame_counter": t.uint32_t(11),
            "security_level": SecurityLevel.FullFrameCounterAndMIC,
            "security_key_type": SecurityKeyType.IndividualKey,
            "security_status": SecurityStatus.SecuritySuccess,
            **kwargs,
        }
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        # Replayed frame counter
        {"frame_counter": t.uint32_t(10)},
        # Unprotected frame for a GPD commissioned with security
        {
            "security_level": SecurityLevel.NoSecurity,
            "security_key_type": SecurityKeyType.NoKey,
            "security_status": SecurityStatus.NoSecurity,
        },
        # Another key type
        {"security_key_type": SecurityKeyType.NWKKey},
        # Failed security processing
        {"security_status": SecurityStatus.AuthFailure},
    ],
)
async def test_decommissioning_rejected(app, manager, kwargs):
    """Decommissioning is only acted upon if it passes the checks (A.3.5.2.4)."""
    dev = add_secured_gpd(app)

    app.gp_packet_received(decommissioning_packet(**kwargs))
    await wait_for_gp_processing()

    assert app.devices[dev.ieee] is dev
    assert call("device_removed", dev) not in app.listener_event.mock_calls
    assert len(app.send_packet.mock_calls) == 0


async def test_decommissioning(app, manager):
    dev = add_secured_gpd(app)

    app.gp_packet_received(decommissioning_packet())
    await wait_for_gp_processing()

    assert dev.ieee not in app.devices
    assert call("device_removed", dev) in app.listener_event.mock_calls

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
        make_gp_packet(
            0x11223344, GPDCommandID.CommissioningRequest, UNPROTECTED_COMMISSIONING
        )
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
        make_gp_packet(
            0x12345678,
            GPDCommandID.ChannelRequest,
            GPChannelRequestPayload(next_channel=0, second_next_channel=0).serialize(),
        )
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

    assert packet.dst == t.AddrModeAddress(
        addr_mode=t.AddrMode.Broadcast, address=t.BroadcastAddress.RX_ON_WHEN_IDLE
    )
    assert packet.src_ep == packet.dst_ep == GP_ENDPOINT
    assert hdr.frame_control.frame_type == foundation.FrameType.CLUSTER_COMMAND
    assert hdr.direction == foundation.Direction.Server_to_Client
    assert hdr.frame_control.disable_default_response
    assert hdr.command_id == command.id
    assert hdr.tsn == packet.tsn

    sent_command(packet, command.schema)
