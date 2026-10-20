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
from zigpy.zgp.commands import (
    GPCommissioningAppInfo,
    GPCommissioningExtendedOptions,
    GPCommissioningOptions,
    GPCommissioningPayload,
    GPStepPayload,
    GPSwitchInformation,
)
from zigpy.zgp.crypto import build_gpdf_header, encrypt_payload
from zigpy.zgp.manager import GreenPowerManager
from zigpy.zgp.types import (
    GP_ENDPOINT,
    ApplicationID,
    DeviceID,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SrcID,
)

TIMESTAMP = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)
KEY = bytes(range(16))
STEP_UP = GPStepPayload(step_size=5, transition_time=10)

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


async def commission(app, src_id: int, payload: bytes, **kwargs) -> None:
    app.gp_packet_received(
        make_gp_packet(src_id, GPDCommandID.CommissioningRequest, payload, **kwargs)
    )
    await wait_for_gp_processing()


def commissioning_payload(
    device_id: DeviceID = DeviceID.OnOffSwitch,
    *,
    security_level: SecurityLevel | None = None,
    key_type: SecurityKeyType = SecurityKeyType.NoKey,
    key: bytes | None = None,
    key_mic: int | None = None,
    outgoing_counter: int | None = None,
    switch_information: GPSwitchInformation | None = None,
    **options: int,
) -> bytes:
    """Serialize a GP Commissioning payload, `options` overriding the Options bits."""
    # Extended options are only sent along with a security level, and a key MIC marks
    # the key as protected with the TC-LK
    extended_options = None

    if security_level is not None:
        extended_options = GPCommissioningExtendedOptions(
            security_level=security_level,
            key_type=key_type,
            key_present=int(key is not None),
            key_encrypted=int(key_mic is not None),
            outgoing_counter_present=int(outgoing_counter is not None),
        )

    app_info = None

    if switch_information is not None:
        app_info = GPCommissioningAppInfo(
            manufacturer_id_present=0,
            model_id_present=0,
            gpd_commands_present=0,
            cluster_list_present=0,
            switch_info_present=1,
            app_description_follows=0,
            _reserved=0,
        )

    return GPCommissioningPayload(
        device_id=device_id,
        options=GPCommissioningOptions(
            **{
                "mac_seq_num_capability": 0,
                "rx_on_capability": 0,
                "app_info_present": int(app_info is not None),
                "_reserved": 0,
                "pan_id_request": 0,
                "security_key_request": 0,
                "fixed_location": 0,
                "extended_options_present": int(extended_options is not None),
                **options,
            }
        ),
        extended_options=extended_options,
        security_key=None if key is None else t.KeyData(key),
        key_mic=None if key_mic is None else t.uint32_t(key_mic),
        outgoing_counter=(
            None if outgoing_counter is None else t.uint32_t(outgoing_counter)
        ),
        app_info=app_info,
        switch_information=switch_information,
    ).serialize()
