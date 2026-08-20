"""Tests for conversion of ZCL-tunneled GP frames into GP packets."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from zigpy.exceptions import GPSecurityProcessingFailed
import zigpy.profiles.zgp
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.greenpower import (
    CommissioningNotificationOptions,
    CommissioningNotificationSchema,
    GreenPowerProxy,
    NotificationOptions,
    NotificationSchema,
)
from zigpy.zgp.tunneling import gp_packet_from_zcl, is_gp_tunnel_packet
from zigpy.zgp.types import (
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    ApplicationID,
    GPDCommandID,
    GPDCommandPayload,
    GPLinkQuality,
    GPPGPDLink,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
)

TIMESTAMP = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)

NOTIFICATION_ID = GreenPowerProxy.ServerCommandDefs.notification.id
COMMISSIONING_NOTIFICATION_ID = (
    GreenPowerProxy.ServerCommandDefs.commissioning_notification.id
)


def make_tunnel_packet(command_id: int, payload: bytes, **kwargs) -> t.ZigbeePacket:
    hdr = foundation.ZCLHeader.cluster(tsn=0x12, command_id=command_id)

    return t.ZigbeePacket(
        timestamp=TIMESTAMP,
        profile_id=zigpy.profiles.zgp.PROFILE_ID,
        cluster_id=GP_CLUSTER_ID,
        src_ep=GP_ENDPOINT,
        dst_ep=GP_ENDPOINT,
        data=t.SerializableBytes(hdr.serialize() + payload),
        **kwargs,
    )


def make_notification_options(**kwargs) -> NotificationOptions:
    return NotificationOptions(
        **{
            "application_id": ApplicationID.SrcID,
            "also_unicast": 0,
            "also_derived_group": 1,
            "also_commissioned_group": 0,
            "security_level": SecurityLevel.FullFrameCounterAndMIC,
            "security_key_type": SecurityKeyType.NWKKey,
            "rx_after_tx": 0,
            "tx_queue_full": 1,
            "bidirectional_cap": 0,
            "proxy_info_present": 1,
            "_reserved": 0,
            **kwargs,
        }
    )


def make_commissioning_options(**kwargs) -> CommissioningNotificationOptions:
    return CommissioningNotificationOptions(
        **{
            "application_id": ApplicationID.SrcID,
            "rx_after_tx": 0,
            "security_level": SecurityLevel.NoSecurity,
            "security_key_type": SecurityKeyType.NoKey,
            "security_failed": 0,
            "bidirectional_cap": 0,
            "proxy_info_present": 1,
            "_reserved": 0,
            **kwargs,
        }
    )


@pytest.mark.parametrize(
    ("gpd_kwargs", "expected_src_id", "expected_ieee", "expected_endpoint"),
    [
        (
            {
                "options": make_notification_options(),
                "gpd_id": 0x12345678,
            },
            0x12345678,
            None,
            None,
        ),
        (
            {
                "options": make_notification_options(application_id=ApplicationID.IEEE),
                "gpd_ieee": t.EUI64.convert("11:22:33:44:55:66:77:88"),
                "gpd_endpoint": 3,
            },
            None,
            t.EUI64.convert("11:22:33:44:55:66:77:88"),
            3,
        ),
    ],
)
def test_notification(gpd_kwargs, expected_src_id, expected_ieee, expected_endpoint):
    command = NotificationSchema(
        frame_counter=1000,
        command_id=GPDCommandID.Toggle,
        payload=GPDCommandPayload(b"\x01\x02"),
        gpp_short_addr=0xAABB,
        gpp_gpd_link=GPPGPDLink(rssi=20, link_quality=GPLinkQuality.High),
        **gpd_kwargs,
    )
    packet = make_tunnel_packet(NOTIFICATION_ID, command.serialize())

    gp_packet = gp_packet_from_zcl(packet)

    assert gp_packet.timestamp == TIMESTAMP
    assert gp_packet.application_id == gpd_kwargs["options"].application_id
    assert gp_packet.src_id == expected_src_id
    assert gp_packet.ieee == expected_ieee
    assert gp_packet.endpoint == expected_endpoint
    assert gp_packet.command_id == GPDCommandID.Toggle
    assert gp_packet.payload.serialize() == b"\x01\x02"
    assert gp_packet.frame_counter == 1000
    assert gp_packet.security_level == SecurityLevel.FullFrameCounterAndMIC
    assert gp_packet.security_key_type == SecurityKeyType.NWKKey
    # The proxy did the security processing, so the key type it echoes is trustworthy
    assert gp_packet.security_status == SecurityStatus.SecuritySuccess
    # GPPGPDLink 20 * 2 - 110 = -70 dBm, High spread over the 0-255 LQI range
    assert gp_packet.rssi == -70
    assert gp_packet.lqi == 170


def test_commissioning_notification():
    command = CommissioningNotificationSchema(
        options=make_commissioning_options(),
        gpd_id=0x01020304,
        frame_counter=42,
        command_id=GPDCommandID.CommissioningRequest,
        payload=GPDCommandPayload(b"\x02\x00"),
        gpp_short_addr=0x1234,
        gpp_gpd_link=GPPGPDLink(rssi=0, link_quality=GPLinkQuality.Poor),
    )
    packet = make_tunnel_packet(COMMISSIONING_NOTIFICATION_ID, command.serialize())

    gp_packet = gp_packet_from_zcl(packet)

    assert gp_packet.src_id == 0x01020304
    assert gp_packet.command_id == GPDCommandID.CommissioningRequest
    assert gp_packet.payload.serialize() == b"\x02\x00"
    assert gp_packet.frame_counter == 42
    assert gp_packet.security_level == SecurityLevel.NoSecurity
    assert gp_packet.security_key_type == SecurityKeyType.NoKey
    assert gp_packet.rssi == -110
    assert gp_packet.lqi == 0


def test_commissioning_notification_security_failed():
    command = CommissioningNotificationSchema(
        options=make_commissioning_options(
            security_level=SecurityLevel.Encrypted,
            security_key_type=SecurityKeyType.IndividualKey,
            security_failed=1,
        ),
        gpd_id=0x01020304,
        frame_counter=42,
        command_id=GPDCommandID.CommissioningRequest,
        payload=GPDCommandPayload(b"\xaa\xbb"),
        gpp_short_addr=0x1234,
        gpp_gpd_link=GPPGPDLink(rssi=20, link_quality=GPLinkQuality.High),
        mic=0xDEADBEEF,
    )
    packet = make_tunnel_packet(COMMISSIONING_NOTIFICATION_ID, command.serialize())

    with pytest.raises(GPSecurityProcessingFailed, match="Security processing"):
        gp_packet_from_zcl(packet)


def test_notification_unspecified_payload():
    """A payload length byte of 0xff means unspecified/no payload."""
    command = NotificationSchema(
        options=make_notification_options(),
        gpd_id=0x12345678,
        frame_counter=1,
        command_id=GPDCommandID.On,
        payload=GPDCommandPayload(b""),
        gpp_short_addr=0xAABB,
        gpp_gpd_link=GPPGPDLink(rssi=10, link_quality=GPLinkQuality.Moderate),
    )
    data = command.serialize()

    # Splice the 0x00 length byte into the legacy 0xff "unspecified" marker
    assert data[11:12] == b"\x00"
    data = data[:11] + b"\xff" + data[12:]

    packet = make_tunnel_packet(NOTIFICATION_ID, data)
    gp_packet = gp_packet_from_zcl(packet)

    assert gp_packet.payload.serialize() == b""


def test_notification_without_proxy_info():
    command = NotificationSchema(
        options=make_notification_options(proxy_info_present=0),
        gpd_id=0x12345678,
        frame_counter=1,
        command_id=GPDCommandID.Off,
        payload=GPDCommandPayload(b""),
    )
    packet = make_tunnel_packet(NOTIFICATION_ID, command.serialize())

    gp_packet = gp_packet_from_zcl(packet)

    assert gp_packet.lqi is None
    assert gp_packet.rssi is None
    assert gp_packet.gpp_distance is None


def test_notification_from_legacy_proxy():
    """A Green Power 1.0 proxy sends a Distance byte instead of the GPP-GPD link."""
    command = NotificationSchema(
        options=make_notification_options(proxy_info_present=0, rx_after_tx=1),
        gpd_id=0x12345678,
        frame_counter=1,
        command_id=GPDCommandID.Off,
        payload=GPDCommandPayload(b""),
        gpp_short_addr=0xAABB,
        gpp_distance=0x42,
    )
    packet = make_tunnel_packet(NOTIFICATION_ID, command.serialize())

    gp_packet = gp_packet_from_zcl(packet)

    assert gp_packet.lqi is None
    assert gp_packet.rssi is None
    assert gp_packet.gpp_distance == 0x42


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, True),
        ({"profile_id": 0x0104}, False),
        ({"cluster_id": 0x0006}, False),
        ({"src_ep": 1}, False),
    ],
)
def test_is_gp_tunnel_packet(kwargs, expected):
    command = NotificationSchema(
        options=make_notification_options(proxy_info_present=0),
        gpd_id=0x12345678,
        frame_counter=1,
        command_id=GPDCommandID.Toggle,
        payload=GPDCommandPayload(b""),
    )
    packet = make_tunnel_packet(NOTIFICATION_ID, command.serialize()).replace(**kwargs)

    assert is_gp_tunnel_packet(packet) == expected


def test_is_gp_tunnel_packet_undecodable_header():
    packet = make_tunnel_packet(NOTIFICATION_ID, b"")
    packet = packet.replace(data=t.SerializableBytes(b"\x01"))

    assert not is_gp_tunnel_packet(packet)


def test_notification_response_direction():
    """GP Notification Response shares an ID with GP Notification: not a tunnel."""
    command = NotificationSchema(
        options=make_notification_options(proxy_info_present=0),
        gpd_id=0x12345678,
        frame_counter=1,
        command_id=GPDCommandID.Toggle,
        payload=GPDCommandPayload(b""),
    )
    hdr = foundation.ZCLHeader.cluster(
        tsn=0x12,
        command_id=NOTIFICATION_ID,
        direction=foundation.Direction.Server_to_Client,
    )
    packet = make_tunnel_packet(NOTIFICATION_ID, b"").replace(
        data=t.SerializableBytes(hdr.serialize() + command.serialize())
    )

    assert not is_gp_tunnel_packet(packet)

    with pytest.raises(ValueError, match="Not a client-to-server command"):
        gp_packet_from_zcl(packet)


def test_non_cluster_command():
    hdr = foundation.ZCLHeader.general(
        tsn=0x12, command_id=foundation.GeneralCommand.Read_Attributes
    )
    packet = make_tunnel_packet(NOTIFICATION_ID, b"")
    packet = packet.replace(data=t.SerializableBytes(hdr.serialize() + b"\x00\x00"))

    with pytest.raises(ValueError, match="Not a cluster-specific command"):
        gp_packet_from_zcl(packet)


def test_untunneled_gp_command():
    command = GreenPowerProxy.ServerCommandDefs.pairing_search
    packet = make_tunnel_packet(command.id, b"\x00\x00\x78\x56\x34\x12")

    with pytest.raises(ValueError, match="Not a tunneled GPDF command"):
        gp_packet_from_zcl(packet)


def test_trailing_data():
    command = NotificationSchema(
        options=make_notification_options(),
        gpd_id=0x12345678,
        frame_counter=1,
        command_id=GPDCommandID.Toggle,
        payload=GPDCommandPayload(b""),
        gpp_short_addr=0xAABB,
        gpp_gpd_link=GPPGPDLink(rssi=10, link_quality=GPLinkQuality.Moderate),
    )
    packet = make_tunnel_packet(NOTIFICATION_ID, command.serialize() + b"\xde\xad")

    with pytest.raises(ValueError, match="Trailing data"):
        gp_packet_from_zcl(packet)


def test_unprotected_notification_status() -> None:
    """An unprotected tunneled frame is reported as such rather than as verified."""
    command = NotificationSchema(
        options=make_notification_options(
            security_level=SecurityLevel.NoSecurity,
            security_key_type=SecurityKeyType.NoKey,
        ),
        gpd_id=0x01020304,
        frame_counter=1000,
        command_id=GPDCommandID.Toggle,
        payload=GPDCommandPayload(b""),
        gpp_short_addr=0xAABB,
        gpp_gpd_link=GPPGPDLink(rssi=20, link_quality=GPLinkQuality.High),
    )
    gp_packet = gp_packet_from_zcl(
        make_tunnel_packet(NOTIFICATION_ID, command.serialize())
    )

    assert gp_packet.security_status == SecurityStatus.NoSecurity
