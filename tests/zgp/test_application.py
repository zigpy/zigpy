"""Tests for Green Power packet handling in the controller application."""

from __future__ import annotations

import asyncio
from unittest.mock import call

import pytest

from tests.async_mock import AsyncMock
from tests.conftest import add_initialized_device, make_ieee
from tests.zgp.conftest import (
    NOTIFICATION_ID,
    STEP_UP,
    commission_individual_key,
    encrypted_gp_packet,
    make_notification_options,
    make_tunnel_packet,
    sent_command,
)
from zigpy.device import GreenPowerDevice
from zigpy.exceptions import DeliveryError
import zigpy.types as t
from zigpy.zcl.clusters.greenpower import NotificationSchema, PairingSchema
import zigpy.zdo.types as zdo_types
from zigpy.zgp.types import (
    GP_ENDPOINT,
    GP_GROUP_ID,
    ApplicationID,
    GPDCommandID,
    GPDCommandPayload,
    GPLinkQuality,
    GPPGPDLink,
    SecurityKeyType,
    SecurityLevel,
    SrcID,
)

SRC = t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x9876)
DST = t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000)


@pytest.fixture
def gpd(app):
    device = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    app.devices[device.ieee] = device
    return device


def make_notification_packet(suffix: bytes = b"") -> t.ZigbeePacket:
    command = NotificationSchema(
        options=make_notification_options(),
        gpd_id=0x12345678,
        frame_counter=100,
        command_id=GPDCommandID.Toggle,
        payload=GPDCommandPayload(b""),
        gpp_short_addr=0xAABB,
        gpp_gpd_link=GPPGPDLink(rssi=20, link_quality=GPLinkQuality.High),
    )

    return make_tunnel_packet(
        NOTIFICATION_ID, command.serialize() + suffix, src=SRC, dst=DST
    )


async def test_tunneled_notification_is_delivered(app, gpd):
    events = []
    gpd.on_event("gp_command_received", events.append)

    app.packet_received(make_notification_packet())

    assert len(events) == 1
    assert events[0].command_id == GPDCommandID.Toggle
    assert gpd.frame_counter == 100


async def test_tunneled_notification_malformed(app, gpd, caplog):
    events = []
    gpd.on_event("gp_command_received", events.append)

    app.packet_received(make_notification_packet(suffix=b"\xde\xad"))

    assert "Failed to convert tunneled GP packet" in caplog.text
    assert len(events) == 0


@pytest.mark.parametrize(
    ("frame_counter", "ciphertext_command_id"),
    [
        (80, GPDCommandID.CommissioningRequest),
        (910, GPDCommandID.SuccessReport),
        (200, GPDCommandID.ChannelRequest),
    ],
)
async def test_encrypted_packet_routed_to_device(
    app, gpd, frame_counter, ciphertext_command_id
):
    """An unprocessed encrypted GPDF is not routed on its ciphertext command ID."""
    commission_individual_key(gpd)

    events = []
    gpd.on_event("gp_command_received", events.append)

    packet = encrypted_gp_packet(
        0x12345678, frame_counter, bytes([GPDCommandID.StepUp]) + STEP_UP.serialize()
    )
    assert packet.command_id == ciphertext_command_id

    app.gp_packet_received(packet)

    assert len(events) == 1
    assert events[0].command_id == GPDCommandID.StepUp


async def test_gp_packet_from_unknown_device(app, caplog):
    packet = t.ZigbeeGpPacket(
        application_id=ApplicationID.SrcID,
        src_id=SrcID(0x99999999),
        command_id=GPDCommandID.Toggle,
    )
    app.gp_packet_received(packet)

    assert "unknown device" in caplog.text


async def test_gp_packet_for_non_gp_device(app, caplog):
    dev = add_initialized_device(app, nwk=0x1234, ieee=make_ieee(1))

    packet = t.ZigbeeGpPacket(
        application_id=ApplicationID.IEEE,
        ieee=dev.ieee,
        command_id=GPDCommandID.Toggle,
    )
    app.gp_packet_received(packet)

    assert "non-GP device" in caplog.text


async def test_zigbee_packet_from_gp_device(app, gpd, caplog):
    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.IEEE, address=gpd.ieee),
        src_ep=1,
        dst=DST,
        dst_ep=1,
        tsn=0x12,
        profile_id=260,
        cluster_id=0x0006,
        data=t.SerializableBytes(b""),
    )
    app.packet_received(packet)

    assert "non-Zigbee device" in caplog.text


async def test_packet_from_gp_alias(app, gpd, caplog):
    """The sink's own aliased Device_annce, relayed back, is not an unknown device."""
    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=gpd.nwk),
        src_ep=0,
        dst=t.AddrModeAddress(
            addr_mode=t.AddrMode.Broadcast,
            address=t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
        ),
        dst_ep=0,
        tsn=0x00,
        profile_id=0x0000,
        cluster_id=zdo_types.ZDOCmd.Device_annce,
        data=t.SerializableBytes(
            b"\x00" + gpd.nwk.serialize() + t.EUI64.UNKNOWN.serialize() + b"\x40"
        ),
    )
    app.packet_received(packet)
    await asyncio.sleep(0)

    assert "Unknown device" not in caplog.text
    assert len(app.send_packet.mock_calls) == 0


async def test_non_announce_packet_from_gp_alias(app, gpd, caplog):
    """Only Device_annce is ignored, an unknown device sharing the alias is discovered."""
    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=gpd.nwk),
        src_ep=1,
        dst=DST,
        dst_ep=1,
        tsn=0x12,
        profile_id=260,
        cluster_id=0x0006,
        data=t.SerializableBytes(b"\x18\x12\x0b\x00\x00"),
    )
    app.packet_received(packet)

    assert "Ignoring announce packet" not in caplog.text
    assert "Unknown device" in caplog.text


@pytest.mark.parametrize(
    "send_error",
    [None, TimeoutError(), DeliveryError("Failed")],
)
async def test_remove_gpd(app, gpd, send_error):
    """Removing a GPD also removes it from the proxies and leaves its group."""
    gpd.security_level = SecurityLevel.NoSecurity
    gpd.security_key_type = SecurityKeyType.NoKey
    app.send_packet.side_effect = send_error
    app.unsubscribe_from_multicast_group = AsyncMock(
        wraps=app.unsubscribe_from_multicast_group
    )

    await app.remove(gpd.ieee)

    assert gpd.ieee not in app.devices
    assert call("device_removed", gpd) in app.listener_event.mock_calls

    [packet] = [c.args[0] for c in app.send_packet.mock_calls]
    pairing = sent_command(packet, PairingSchema)
    assert pairing.options.remove_gpd
    assert pairing.gpd_id == 0x12345678

    assert app.unsubscribe_from_multicast_group.mock_calls == [
        call(GP_GROUP_ID, endpoint_id=GP_ENDPOINT)
    ]


async def test_reinterview_gpd(app, gpd):
    """Commissioning fully describes a GPD, so re-interviewing it does nothing."""
    await app.reinterview_device(gpd.ieee)

    assert app.devices[gpd.ieee] is gpd
    assert call("device_reinterviewed", gpd) not in app.listener_event.mock_calls


async def test_handle_join_gpd(app, gpd, caplog):
    app.handle_join(0x1234, gpd.ieee, None)

    assert "Ignoring join announcement" in caplog.text
    assert app.devices[gpd.ieee] is gpd
    assert call("device_joined", gpd) not in app.listener_event.mock_calls


async def test_handle_leave_gpd(app, gpd, caplog):
    app.handle_leave(gpd.nwk, gpd.ieee)

    assert "Ignoring leave announcement" in caplog.text
    assert app.devices[gpd.ieee] is gpd
    assert call("device_left", gpd) not in app.listener_event.mock_calls
