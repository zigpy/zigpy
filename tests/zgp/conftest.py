"""Shared fixtures for Green Power tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from zigpy.device import GreenPowerDevice
import zigpy.profiles.zgp
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.greenpower import (
    CommissioningNotificationOptions,
    GreenPowerProxy,
    NotificationOptions,
)
from zigpy.zgp.crypto import build_gpdf_header, encrypt_payload
from zigpy.zgp.manager import GreenPowerManager
from zigpy.zgp.types import (
    GP_ENDPOINT,
    ApplicationID,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SrcID,
)

TIMESTAMP = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)
KEY = bytes(range(16))

NOTIFICATION_ID = GreenPowerProxy.ServerCommandDefs.notification.id
COMMISSIONING_NOTIFICATION_ID = (
    GreenPowerProxy.ServerCommandDefs.commissioning_notification.id
)


@pytest.fixture
def manager(app) -> GreenPowerManager:
    """Return the GP manager attached to the test application.

    A valid operational Zigbee channel (15) is pinned on the app state so
    GP responses that encode `channel - 11` don't underflow. Individual
    tests remain free to overwrite `app.state.network_info.channel`.
    """
    app.state.network_info.channel = 15
    return app.green_power


async def wait_for_gp_processing() -> None:
    """Wait for the manager to finish processing received commissioning GPDFs."""
    await asyncio.gather(
        *(
            task
            for task in asyncio.all_tasks()
            if task.get_name().startswith("gp_process_command")
        )
    )


def make_tunnel_packet(command_id: int, payload: bytes, **kwargs) -> t.ZigbeePacket:
    hdr = foundation.ZCLHeader.cluster(tsn=0x12, command_id=command_id)

    return t.ZigbeePacket(
        timestamp=TIMESTAMP,
        profile_id=zigpy.profiles.zgp.PROFILE_ID,
        cluster_id=GreenPowerProxy.cluster_id,
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


def sent_command(packet: t.ZigbeePacket, schema: type[t.Struct]) -> t.Struct:
    _, data = foundation.ZCLHeader.deserialize(packet.data.serialize())
    command, rest = schema.deserialize(data)
    assert not rest

    return command


def encrypted_gp_packet(
    src_id: int, frame_counter: int, plaintext: bytes, key: bytes = KEY
) -> t.ZigbeeGpPacket:
    """A GPDF encrypted with an individual key, not processed by the radio.

    `plaintext` is the GPD command ID followed by its payload.
    """
    header = build_gpdf_header(
        src_id,
        frame_counter,
        security_level=SecurityLevel.Encrypted,
        individual_key=True,
        auto_commissioning=False,
        rx_after_tx=False,
    )
    ciphertext, mic = encrypt_payload(
        src_id,
        frame_counter,
        key,
        plaintext,
        header=header,
        security_level=SecurityLevel.Encrypted,
    )

    return t.ZigbeeGpPacket(
        application_id=ApplicationID.SrcID,
        src_id=SrcID(src_id),
        command_id=GPDCommandID(ciphertext[0]),
        payload=t.SerializableBytes(ciphertext[1:]),
        frame_counter=t.uint32_t(frame_counter),
        security_level=SecurityLevel.Encrypted,
        security_key_type=SecurityKeyType.NoKey,
        security_status=SecurityStatus.Unprocessed,
        mic=t.uint32_t(int.from_bytes(mic, "little")),
        auto_commissioning=False,
        rx_after_tx=False,
        individual_key=True,
    )


def commission_individual_key(device: GreenPowerDevice) -> None:
    device.security_key = t.KeyData(KEY)
    device.security_level = SecurityLevel.Encrypted
    device.security_key_type = SecurityKeyType.IndividualKey
