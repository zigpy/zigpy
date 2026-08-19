"""Tests for Green Power packet handling in the controller application."""

from __future__ import annotations

import logging
from unittest.mock import call

import pytest

from tests.conftest import add_initialized_device, make_ieee
from tests.zgp.test_tunneling import (
    COMMISSIONING_NOTIFICATION_ID,
    NOTIFICATION_ID,
    make_commissioning_options,
    make_notification_options,
    make_tunnel_packet,
)
from zigpy.device import GreenPowerDevice
import zigpy.types as t
from zigpy.zcl.clusters.greenpower import (
    CommissioningNotificationSchema,
    NotificationSchema,
)
from zigpy.zgp.types import (
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


async def test_tunneled_notification_security_failed(app, gpd, caplog):
    command = CommissioningNotificationSchema(
        options=make_commissioning_options(
            security_level=SecurityLevel.Encrypted,
            security_key_type=SecurityKeyType.IndividualKey,
            security_failed=1,
        ),
        gpd_id=0x12345678,
        frame_counter=42,
        command_id=GPDCommandID.CommissioningRequest,
        payload=GPDCommandPayload(b""),
        gpp_short_addr=0x1234,
        gpp_gpd_link=GPPGPDLink(rssi=20, link_quality=GPLinkQuality.High),
        mic=0xDEADBEEF,
    )
    packet = make_tunnel_packet(
        COMMISSIONING_NOTIFICATION_ID, command.serialize(), src=SRC, dst=DST
    )

    events = []
    gpd.on_event("gp_command_received", events.append)

    with caplog.at_level(logging.DEBUG):
        app.packet_received(packet)

    assert "could not decrypt" in caplog.text
    assert len(events) == 0


async def test_tunneled_notification_malformed(app, gpd, caplog):
    events = []
    gpd.on_event("gp_command_received", events.append)

    app.packet_received(make_notification_packet(suffix=b"\xde\xad"))

    assert "Failed to convert tunneled GP packet" in caplog.text
    assert len(events) == 0


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


async def test_remove_gpd(app, gpd):
    await app.remove(gpd.ieee)

    assert gpd.ieee not in app.devices
    assert call("device_removed", gpd) in app.listener_event.mock_calls


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
