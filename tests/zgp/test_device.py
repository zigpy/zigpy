"""Tests for Green Power device packet handling."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
from typing import Any
from unittest.mock import call

import freezegun
import pytest

from tests.async_mock import AsyncMock
from tests.conftest import FeaturelessApp, make_app
from tests.zgp.conftest import (
    STEP_UP,
    TIMESTAMP,
    commission_individual_key,
    encrypted_gp_packet,
    sent_command,
)
from zigpy.device import GP_DUPLICATE_TIMEOUT, GreenPowerDevice
from zigpy.exceptions import DeliveryError
import zigpy.types as t
from zigpy.zcl import AttributeReportedEvent, foundation
from zigpy.zcl.clusters.general import OnOff
from zigpy.zcl.clusters.greenpower import ResponseSchema
from zigpy.zcl.clusters.homeautomation import ElectricalMeasurement
from zigpy.zcl.clusters.smartenergy import Metering
from zigpy.zcl.foundation import DataTypeId
from zigpy.zgp.commands import (
    GPAttributeReportingPayload,
    GPClusterReport,
    GPGenericSwitchConfiguration,
    GPManufacturerSpecificAttributeReportingPayload,
    GPManufacturerSpecificMultiClusterReportingPayload,
    GPMultiClusterReportingPayload,
)
from zigpy.zgp.manager import GPDF_LIFETIME
from zigpy.zgp.types import (
    ApplicationID,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SecurityStatus,
    SrcID,
    SwitchType,
)
from zigpy.zgp.util import derive_alias

IEEE = t.EUI64.convert("11:22:33:44:55:66:77:88")


@pytest.fixture
def device() -> GreenPowerDevice:
    return GreenPowerDevice(
        None, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )


@pytest.fixture
def events(device) -> list:
    events = []
    device.on_event("gp_command_received", events.append)
    return events


def make_packet(
    frame_counter: int | None,
    *,
    command_id: GPDCommandID = GPDCommandID.Toggle,
    payload: bytes = b"",
    security_level: SecurityLevel = SecurityLevel.Encrypted,
    security_key_type: SecurityKeyType = SecurityKeyType.GPDGroupKey,
    security_status: SecurityStatus | None = None,
    offset: timedelta = timedelta(0),
    lqi: int = 200,
    rssi: int = -50,
    application_id: ApplicationID = ApplicationID.SrcID,
    endpoint: int | None = None,
) -> t.ZigbeeGpPacket:
    return t.ZigbeeGpPacket(
        timestamp=TIMESTAMP + offset,
        application_id=application_id,
        src_id=SrcID(0x12345678) if application_id is ApplicationID.SrcID else None,
        ieee=IEEE if application_id is ApplicationID.IEEE else None,
        endpoint=None if endpoint is None else t.uint8_t(endpoint),
        command_id=command_id,
        payload=t.SerializableBytes(payload),
        frame_counter=(None if frame_counter is None else t.uint32_t(frame_counter)),
        security_level=security_level,
        security_key_type=security_key_type,
        security_status=security_status,
        lqi=t.uint8_t(lqi),
        rssi=t.int8s(rssi),
    )


def commission_security(device: GreenPowerDevice) -> None:
    device.security_level = SecurityLevel.Encrypted
    device.security_key_type = SecurityKeyType.GPDGroupKey


def test_missing_gpd_id() -> None:
    with pytest.raises(ValueError, match="`src_id` is required"):
        GreenPowerDevice(None, application_id=ApplicationID.SrcID)

    with pytest.raises(ValueError, match="`ieee` is required"):
        GreenPowerDevice(None, application_id=ApplicationID.IEEE)


def test_ieee_addressed_gpd() -> None:
    device = GreenPowerDevice(None, application_id=ApplicationID.IEEE, ieee=IEEE)

    assert device.ieee == IEEE
    assert device.nwk == derive_alias(IEEE)
    assert device.src_id is None
    assert device.name == f"GreenPowerDevice {IEEE}"


def test_device_properties(device) -> None:
    assert device.src_id == 0x12345678
    assert device.nwk == derive_alias(0x12345678)
    assert device.name == "GreenPowerDevice 0x12345678"
    assert device.is_initialized
    assert device.manufacturer_id is None

    device.gpd_manufacturer_id = t.uint16_t(0x1234)
    device.switch_configuration = GPGenericSwitchConfiguration(
        num_contacts=2, switch_type=SwitchType.Rocker, _reserved=0
    )
    device.mac_seq_num_capability = True

    assert device.manufacturer_id == 0x1234
    assert device.get_signature() == {
        "application_id": ApplicationID.SrcID,
        "src_id": 0x12345678,
        "device_id": None,
        "manufacturer_id": 0x1234,
        "model_id": None,
        "commands": [],
        "server_cluster_ids": [],
        "client_cluster_ids": [],
        "switch_configuration": GPGenericSwitchConfiguration(0x22),
        "mac_seq_num_capability": True,
        "extra_commissioning_payload": None,
    }

    device.extra_commissioning_payload = b"qerh7pox@GP0001\xcb"
    assert (
        device.get_signature()["extra_commissioning_payload"]
        == "7165726837706f7840475030303031cb"
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, None),
        (b"", ""),
        (b"qerh7pox@GP0001\xcb", "7165726837706f7840475030303031cb"),
    ],
)
def test_signature_commissioning_payload(device, payload, expected) -> None:
    """The trailing commissioning data is hex in the JSON-serializable signature."""
    device.extra_commissioning_payload = payload
    signature = device.get_signature()

    assert signature["extra_commissioning_payload"] == expected
    assert json.loads(json.dumps(signature))["extra_commissioning_payload"] == expected


def test_packet_received(device, events) -> None:
    device.packet_received(make_packet(1000))

    assert len(events) == 1
    assert events[0].device_ieee == str(device.ieee)
    assert events[0].command_id == GPDCommandID.Toggle
    assert device.frame_counter == 1000
    assert device.last_seen == TIMESTAMP.timestamp()
    assert device.lqi == 200
    assert device.rssi == -50


def test_packet_received_parses_command(device, events) -> None:
    device.packet_received(
        make_packet(1, command_id=GPDCommandID.StepUp, payload=STEP_UP.serialize())
    )

    assert len(events) == 1
    assert events[0].command == STEP_UP


def test_packet_received_unparseable_payload(device, events) -> None:
    """A GPDF whose payload fails to parse is still delivered, without a command."""
    device.packet_received(make_packet(1, command_id=GPDCommandID.StepUp, payload=b""))

    assert len(events) == 1
    assert events[0].command is None


def test_packet_received_command_without_schema(device, events) -> None:
    device.packet_received(
        make_packet(1, command_id=GPDCommandID.ApplicationDescription, payload=b"\x01")
    )

    assert len(events) == 1
    assert events[0].command is None


def test_relayed_duplicate_does_not_refresh_state(device, events) -> None:
    """The same GPDF forwarded by a second, worse proxy keeps the first reception."""
    device.packet_received(make_packet(1000))
    device.packet_received(
        make_packet(1000, offset=timedelta(seconds=0.5), lqi=3, rssi=-120)
    )

    assert len(events) == 1
    assert device.lqi == 200
    assert device.rssi == -50
    assert device.last_seen == TIMESTAMP.timestamp()


def test_replay_does_not_refresh_state(device, events) -> None:
    """A protected frame failing the freshness check does not indicate liveness."""
    device.packet_received(make_packet(1000))
    device.packet_received(make_packet(500, offset=timedelta(days=3), lqi=1, rssi=-100))

    assert len(events) == 1
    assert device.frame_counter == 1000
    assert device.lqi == 200
    assert device.rssi == -50
    assert device.last_seen == TIMESTAMP.timestamp()


@pytest.mark.parametrize(
    ("offsets", "expected_events"),
    [
        # A repeated MAC sequence number within the 2s window is a duplicate
        ([timedelta(seconds=1)], 1),
        # Outside of it, it is a new (e.g. random sequence number) frame
        ([timedelta(seconds=3)], 2),
        # The window is anchored at the last accepted frame: it does not slide
        # forward on each filtered duplicate
        ([timedelta(seconds=1.5), timedelta(seconds=3)], 2),
    ],
)
def test_unprotected_duplicate_window(device, events, offsets, expected_events) -> None:
    device.packet_received(
        make_packet(
            7,
            security_level=SecurityLevel.NoSecurity,
            security_key_type=SecurityKeyType.NoKey,
        )
    )

    for offset in offsets:
        device.packet_received(
            make_packet(
                7,
                security_level=SecurityLevel.NoSecurity,
                security_key_type=SecurityKeyType.NoKey,
                offset=offset,
            )
        )

    assert len(events) == expected_events


@pytest.mark.parametrize(
    ("offset", "expected_events"),
    [
        # Within the 2s window, the first GPDF is still remembered
        (timedelta(seconds=1), 2),
        (timedelta(seconds=3), 3),
    ],
)
def test_unprotected_duplicate_after_newer_frame(
    device, events, offset, expected_events
) -> None:
    """An unprotected GPDF forwarded again after a newer one is still a duplicate."""
    for seq_num, seq_offset in (
        (7, timedelta(0)),
        (8, timedelta(seconds=0.5)),
        (7, offset),
    ):
        device.packet_received(
            make_packet(
                seq_num,
                security_level=SecurityLevel.NoSecurity,
                security_key_type=SecurityKeyType.NoKey,
                offset=seq_offset,
            )
        )

    assert len(events) == expected_events


@pytest.mark.parametrize(
    ("security_level", "security_key_type"),
    [
        (SecurityLevel.NoSecurity, SecurityKeyType.NoKey),
        (SecurityLevel.FullFrameCounterAndMIC, SecurityKeyType.GPDGroupKey),
        (SecurityLevel.Encrypted, SecurityKeyType.IndividualKey),
    ],
)
def test_security_mismatch_is_dropped(
    device, events, security_level, security_key_type
) -> None:
    """Frames not matching the commissioned security parameters are silently dropped."""
    commission_security(device)

    device.packet_received(make_packet(5000))
    device.packet_received(
        make_packet(
            6000,
            security_level=security_level,
            security_key_type=security_key_type,
            offset=timedelta(seconds=10),
        )
    )

    assert len(events) == 1
    assert device.frame_counter == 5000


@pytest.mark.parametrize(
    ("security_status", "delivered"),
    [
        (None, True),
        (SecurityStatus.SecuritySuccess, True),
        (SecurityStatus.NoSecurity, True),
        (SecurityStatus.CounterFailure, False),
        (SecurityStatus.AuthFailure, False),
    ],
)
def test_security_status_gate(device, events, security_status, delivered) -> None:
    """Only frames that passed security processing are delivered (A.3.5.2.5)."""
    commission_security(device)

    device.packet_received(make_packet(5000))
    device.packet_received(
        make_packet(
            6000,
            security_status=security_status,
            offset=timedelta(seconds=10),
        )
    )

    assert len(events) == (2 if delivered else 1)
    assert device.frame_counter == (6000 if delivered else 5000)


def test_missing_frame_counter_keeps_stored_counter(device, events) -> None:
    """A frame without a frame counter must not disable replay protection."""
    commission_security(device)

    device.packet_received(make_packet(5000))
    device.packet_received(make_packet(None, offset=timedelta(seconds=10)))
    device.packet_received(make_packet(1, offset=timedelta(seconds=20)))

    assert len(events) == 2
    assert device.frame_counter == 5000


def test_unprotected_frame_cannot_reset_frame_counter(device, events) -> None:
    """An unprotected inject must not break the anti-replay counter (A.3.5.2.4)."""
    commission_security(device)

    device.packet_received(make_packet(5000))
    device.packet_received(make_packet(4000, offset=timedelta(seconds=10)))
    device.packet_received(
        make_packet(
            42,
            security_level=SecurityLevel.NoSecurity,
            security_key_type=SecurityKeyType.NoKey,
            offset=timedelta(seconds=20),
        )
    )
    device.packet_received(make_packet(4000, offset=timedelta(seconds=30)))

    assert len(events) == 1
    assert device.frame_counter == 5000


def test_ieee_frame_endpoint_passthrough() -> None:
    """IEEE addressing delivers the frame's endpoint."""
    device = GreenPowerDevice(None, application_id=ApplicationID.IEEE, ieee=IEEE)

    events = []
    device.on_event("gp_command_received", events.append)

    device.packet_received(
        make_packet(1000, application_id=ApplicationID.IEEE, endpoint=5)
    )

    assert len(events) == 1
    assert events[0].endpoint_id == 5


@pytest.mark.parametrize("rx_after_tx", [True, False])
async def test_rx_after_tx_passthrough(app, rx_after_tx) -> None:
    """The event says whether the GPD listens after the GPDF."""
    device = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    events = []
    device.on_event("gp_command_received", events.append)

    device.packet_received(make_packet(1000).replace(rx_after_tx=rx_after_tx))

    assert len(events) == 1
    assert events[0].rx_after_tx is rx_after_tx


def encrypted_packet(frame_counter: int) -> t.ZigbeeGpPacket:
    """Encrypt a Step Up command as a GPD would, with an individual key."""
    return encrypted_gp_packet(
        0x12345678, frame_counter, bytes([GPDCommandID.StepUp]) + STEP_UP.serialize()
    )


def test_unprocessed_frame_decrypted(device, events) -> None:
    """A protected frame the radio did not process is decrypted by the sink."""
    commission_individual_key(device)

    device.packet_received(encrypted_packet(1000))

    assert len(events) == 1
    assert events[0].command_id == GPDCommandID.StepUp
    assert events[0].command == STEP_UP
    assert device.frame_counter == 1000


@pytest.mark.parametrize(
    "packet_kwargs",
    [
        # Tampered MIC
        {"mic": t.uint32_t(0xDEADBEEF)},
        # Protected with a shared key, the GPD was commissioned with an individual one
        {"individual_key": False},
        # Another security level than the commissioned one
        {"security_level": SecurityLevel.FullFrameCounterAndMIC},
    ],
)
def test_unprocessed_frame_rejected(device, events, packet_kwargs) -> None:
    """A frame that does not verify with the commissioned key is dropped."""
    commission_individual_key(device)
    device.frame_counter = t.uint32_t(10)

    device.packet_received(encrypted_packet(1000).replace(**packet_kwargs))

    assert len(events) == 0
    assert device.frame_counter == 10


def test_unprocessed_frame_without_key(device, events) -> None:
    """Without a commissioned key, a protected frame cannot be verified."""
    commission_security(device)

    device.packet_received(encrypted_packet(1000))

    assert len(events) == 0


def rx_after_tx_packet(
    gpp_short_addr: int | None = None,
    *,
    lqi: int = 200,
    bidirectional_cap: bool = True,
    tx_queue_full: bool = False,
) -> t.ZigbeeGpPacket:
    """A GPDF after which the GPD listens, received directly or through a proxy."""
    return make_packet(5, lqi=lqi).replace(
        rx_after_tx=True,
        gpp_short_addr=None if gpp_short_addr is None else t.NWK(gpp_short_addr),
        gpp_bidirectional_cap=None if gpp_short_addr is None else bidirectional_cap,
        gpp_tx_queue_full=None if gpp_short_addr is None else tx_queue_full,
    )


def register_device(app, **kwargs) -> GreenPowerDevice:
    device = GreenPowerDevice(app, **kwargs)
    app.devices[device.ieee] = device

    return device


@pytest.fixture
def gp_app(app):
    app.state.network_info.channel = 15
    app.send_gpdf = AsyncMock()
    return app


async def test_send_gpdf_direct(gp_app) -> None:
    """A GPDF to a GPD the radio hears directly is sent by the radio."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )

    async def send_gpdf(**kwargs) -> None:
        # The radio waits for the GPD to listen, so proxies are told first
        assert len(gp_app.send_packet.mock_calls) == 1

    gp_app.send_gpdf.side_effect = send_gpdf

    gp_app.gp_packet_received(rx_after_tx_packet())
    await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert gp_app.send_gpdf.mock_calls == [
        call(
            target=SrcID(0x12345678),
            command_id=GPDCommandID(0xFE),
            payload=b"\x00",
            channel=15,
            lifetime=GPDF_LIFETIME,
        )
    ]

    # Proxies are told the sink was elected, to drop their queued GPDFs (A.3.6.2.3)
    [packet] = [c.args[0] for c in gp_app.send_packet.mock_calls]
    response = sent_command(packet, ResponseSchema)
    assert response.temp_master_short_addr == 0x0000
    assert response.gpd_id == 0x12345678


async def test_send_gpdf_through_proxy(gp_app) -> None:
    """A GPDF to a GPD heard through a proxy is sent by that proxy."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )

    gp_app.gp_packet_received(rx_after_tx_packet(0x1234))
    await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert len(gp_app.send_gpdf.mock_calls) == 0

    [packet] = [c.args[0] for c in gp_app.send_packet.mock_calls]
    response = sent_command(packet, ResponseSchema)
    assert response.temp_master_short_addr == 0x1234
    assert response.temp_master_tx_channel.transmit_channel == 15 - 11
    assert response.gpd_id == 0x12345678
    assert response.gpd_command_id == GPDCommandID(0xFE)
    assert response.gpd_command_payload == b"\x00"


async def test_send_gpdf_ieee(gp_app) -> None:
    """A GPD addressed by its IEEE address is targeted with its endpoint."""
    device = register_device(gp_app, application_id=ApplicationID.IEEE, ieee=IEEE)

    gp_app.gp_packet_received(
        make_packet(5, application_id=ApplicationID.IEEE, endpoint=1).replace(
            rx_after_tx=True
        )
    )
    await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert gp_app.send_gpdf.mock_calls == [
        call(
            target=(IEEE, 1),
            command_id=GPDCommandID(0xFE),
            payload=b"\x00",
            channel=15,
            lifetime=GPDF_LIFETIME,
        )
    ]
    assert len(gp_app.send_packet.mock_calls) == 0


async def test_send_gpdf_ieee_through_proxy(gp_app) -> None:
    """A GP Response cannot carry the IEEE address of a GPD yet."""
    device = register_device(gp_app, application_id=ApplicationID.IEEE, ieee=IEEE)

    gp_app.gp_packet_received(
        make_packet(5, application_id=ApplicationID.IEEE, endpoint=1).replace(
            rx_after_tx=True,
            gpp_short_addr=t.NWK(0x1234),
            gpp_bidirectional_cap=True,
            gpp_tx_queue_full=False,
        )
    )

    with pytest.raises(DeliveryError):
        await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert len(gp_app.send_gpdf.mock_calls) == 0
    assert len(gp_app.send_packet.mock_calls) == 0


async def test_send_gpdf_elects_from_all_instances(gp_app) -> None:
    """Every instance of a GPDF is a candidate, but the GPD processes it once."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    events = []
    device.on_event("gp_command_received", events.append)

    gp_app.gp_packet_received(rx_after_tx_packet(lqi=100))
    gp_app.gp_packet_received(rx_after_tx_packet(0x1234, lqi=255))
    await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert len(events) == 1
    assert len(gp_app.send_gpdf.mock_calls) == 0

    [packet] = [c.args[0] for c in gp_app.send_packet.mock_calls]
    assert sent_command(packet, ResponseSchema).temp_master_short_addr == 0x1234


@pytest.mark.parametrize(
    "packets",
    [
        [],
        [make_packet(5).replace(rx_after_tx=False)],
        # In operational mode, only proxies capable of bidirectional communication with
        # room in their gpTxQueue transmit (A.3.6.2.3)
        [rx_after_tx_packet(0x1234, bidirectional_cap=False)],
        [rx_after_tx_packet(0x1234, tx_queue_full=True)],
    ],
)
async def test_send_gpdf_no_temp_master(gp_app, packets) -> None:
    """A GPDF without a node to transmit it is not sent."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )

    for packet in packets:
        gp_app.gp_packet_received(packet)

    with pytest.raises(DeliveryError):
        await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert len(gp_app.send_gpdf.mock_calls) == 0
    assert len(gp_app.send_packet.mock_calls) == 0


async def test_send_gpdf_radio_cannot_send() -> None:
    """A GPD heard only by a radio that cannot transmit GPDFs is not sent one."""
    app = make_app({}, app_base=FeaturelessApp)
    device = register_device(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )

    app.gp_packet_received(rx_after_tx_packet())

    with pytest.raises(DeliveryError):
        await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert len(app.send_packet.mock_calls) == 0


async def test_send_gpdf_expired(gp_app) -> None:
    """A GPDF with RxAfterTx is only replied to within gpDuplicateTimeout."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )

    with freezegun.freeze_time() as frozen:
        gp_app.gp_packet_received(rx_after_tx_packet(0x1234))
        frozen.tick(GP_DUPLICATE_TIMEOUT.total_seconds() + 1)

        # The loop runs due timers after the callbacks already scheduled
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        with pytest.raises(DeliveryError):
            await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert len(gp_app.send_packet.mock_calls) == 0


async def test_forged_gpdf_does_not_suppress_genuine(gp_app) -> None:
    """An instance that fails security does not start an election for its counter."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    commission_individual_key(device)
    events = []
    device.on_event("gp_command_received", events.append)

    plaintext = bytes([GPDCommandID.StepUp]) + STEP_UP.serialize()

    gp_app.gp_packet_received(
        encrypted_gp_packet(0x12345678, 1000, plaintext, rx_after_tx=True)
    )
    gp_app.gp_packet_received(
        encrypted_gp_packet(
            0x12345678, 1001, plaintext, key=bytes(16), rx_after_tx=True
        )
    )
    gp_app.gp_packet_received(
        encrypted_gp_packet(0x12345678, 1001, plaintext, rx_after_tx=True)
    )

    assert len(events) == 2
    assert device.frame_counter == 1001


async def test_send_gpdf_ignores_replayed_instances(gp_app) -> None:
    """An older GPDF forwarded again is not a candidate for the latest one."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )

    gp_app.gp_packet_received(rx_after_tx_packet(0x1111, lqi=100))
    gp_app.gp_packet_received(
        rx_after_tx_packet(0x2222, lqi=255).replace(frame_counter=t.uint32_t(4))
    )
    await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    [packet] = [c.args[0] for c in gp_app.send_packet.mock_calls]
    assert sent_command(packet, ResponseSchema).temp_master_short_addr == 0x1111


async def test_send_gpdf_candidate_after_newer_gpdf(gp_app) -> None:
    """A newer GPDF without RxAfterTx does not end the election of an older one."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )

    gp_app.gp_packet_received(rx_after_tx_packet(lqi=50))
    gp_app.gp_packet_received(make_packet(6, lqi=50))
    gp_app.gp_packet_received(rx_after_tx_packet(0x1111, lqi=255))
    await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert len(gp_app.send_gpdf.mock_calls) == 0

    [packet] = [c.args[0] for c in gp_app.send_packet.mock_calls]
    assert sent_command(packet, ResponseSchema).temp_master_short_addr == 0x1111


async def test_send_gpdf_newer_gpdf_during_election(gp_app) -> None:
    """A newer GPDF with RxAfterTx during the election is replied to instead."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )

    gp_app.gp_packet_received(rx_after_tx_packet(0x1111, lqi=255))
    send = asyncio.create_task(device.send_gpdf(GPDCommandID(0xFE), b"\x00"))
    await asyncio.sleep(0)
    gp_app.gp_packet_received(
        rx_after_tx_packet(0x2222, lqi=100).replace(frame_counter=t.uint32_t(6))
    )
    await send

    [packet] = [c.args[0] for c in gp_app.send_packet.mock_calls]
    assert sent_command(packet, ResponseSchema).temp_master_short_addr == 0x2222


async def test_send_gpdf_commissioning_window_open(gp_app) -> None:
    """An operational GPDF needs a bidirectional proxy, even in commissioning mode."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    await gp_app.green_power.permit_join(time_s=60)
    gp_app.send_packet.reset_mock()

    gp_app.gp_packet_received(rx_after_tx_packet(0x1234, bidirectional_cap=False))

    with pytest.raises(DeliveryError):
        await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert len(gp_app.send_packet.mock_calls) == 0


async def test_send_gpdf_unprotected_candidate_after_newer_gpdf(gp_app) -> None:
    """An unprotected GPDF forwarded after a newer one stays a TempMaster candidate."""
    device = register_device(
        gp_app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    events = []
    device.on_event("gp_command_received", events.append)
    unprotected = {
        "security_level": SecurityLevel.NoSecurity,
        "security_key_type": SecurityKeyType.NoKey,
    }

    gp_app.gp_packet_received(
        rx_after_tx_packet(0x1111, lqi=255).replace(**unprotected)
    )
    gp_app.gp_packet_received(make_packet(6).replace(**unprotected))
    gp_app.gp_packet_received(rx_after_tx_packet(0x2222, lqi=10).replace(**unprotected))
    await device.send_gpdf(GPDCommandID(0xFE), b"\x00")

    assert len(events) == 2
    assert device.frame_counter == 6

    [packet] = [c.args[0] for c in gp_app.send_packet.mock_calls]
    assert sent_command(packet, ResponseSchema).temp_master_short_addr == 0x1111


def attribute(attr_id: int, data_type: DataTypeId, value: Any) -> foundation.Attribute:
    return foundation.Attribute(
        attrid=attr_id, value=foundation.TypeValue(type=data_type, value=value)
    )


VOLTAGE = attribute(
    ElectricalMeasurement.AttributeDefs.rms_voltage.id,
    DataTypeId.uint16,
    t.uint16_t(230),
)
ENERGY = attribute(
    Metering.AttributeDefs.current_summ_delivered.id,
    DataTypeId.uint48,
    t.uint48_t(1234),
)
VENDOR = attribute(0x5000, DataTypeId.uint16, t.uint16_t(7))
VENDOR_CLUSTER_ID = 0xFC00


@pytest.mark.parametrize(
    ("command_id", "command", "expected"),
    [
        (
            GPDCommandID.AttributeReporting,
            GPAttributeReportingPayload(
                cluster_id=Metering.cluster_id, attributes=[ENERGY]
            ),
            [(Metering.cluster_id, ENERGY.attrid, None, 1234)],
        ),
        # Public attributes of standard clusters stay standard (Table 58)
        (
            GPDCommandID.ManufacturerSpecificReporting,
            GPManufacturerSpecificAttributeReportingPayload(
                manufacturer_code=0x105E,
                cluster_id=ElectricalMeasurement.cluster_id,
                attributes=[VOLTAGE, VENDOR],
            ),
            [
                (ElectricalMeasurement.cluster_id, VOLTAGE.attrid, None, 230),
                (ElectricalMeasurement.cluster_id, VENDOR.attrid, 0x105E, 7),
            ],
        ),
        (
            GPDCommandID.MultiClusterReporting,
            GPMultiClusterReportingPayload(
                reports=[
                    GPClusterReport(cluster_id=Metering.cluster_id, attribute=ENERGY),
                    GPClusterReport(
                        cluster_id=ElectricalMeasurement.cluster_id, attribute=VOLTAGE
                    ),
                ]
            ),
            [
                (Metering.cluster_id, ENERGY.attrid, None, 1234),
                (ElectricalMeasurement.cluster_id, VOLTAGE.attrid, None, 230),
            ],
        ),
        # Every attribute of a manufacturer-specific cluster is manufacturer-specific
        (
            GPDCommandID.ManufacturerSpecificMultiClusterReporting,
            GPManufacturerSpecificMultiClusterReportingPayload(
                manufacturer_code=0x105E,
                reports=[
                    GPClusterReport(cluster_id=VENDOR_CLUSTER_ID, attribute=VOLTAGE),
                    GPClusterReport(cluster_id=Metering.cluster_id, attribute=ENERGY),
                ],
            ),
            [
                (VENDOR_CLUSTER_ID, VOLTAGE.attrid, 0x105E, 230),
                (Metering.cluster_id, ENERGY.attrid, None, 1234),
            ],
        ),
        # A value that does not fit its attribute's type does not drop the others
        (
            GPDCommandID.MultiClusterReporting,
            GPMultiClusterReportingPayload(
                reports=[
                    GPClusterReport(
                        cluster_id=Metering.cluster_id,
                        attribute=attribute(
                            ENERGY.attrid,
                            DataTypeId.string,
                            t.CharacterString("abc"),
                        ),
                    ),
                    GPClusterReport(
                        cluster_id=ElectricalMeasurement.cluster_id, attribute=VOLTAGE
                    ),
                ]
            ),
            [(ElectricalMeasurement.cluster_id, VOLTAGE.attrid, None, 230)],
        ),
        # Manufacturer-specific attributes need a manufacturer code
        (
            GPDCommandID.AttributeReporting,
            GPAttributeReportingPayload(
                cluster_id=Metering.cluster_id, attributes=[VENDOR]
            ),
            [],
        ),
        # Clusters the GPD did not list during commissioning are not created
        (
            GPDCommandID.AttributeReporting,
            GPAttributeReportingPayload(
                cluster_id=OnOff.cluster_id,
                attributes=[attribute(0x0000, DataTypeId.bool_, t.Bool.true)],
            ),
            [],
        ),
    ],
)
def test_attribute_reports_reach_clusters(app, command_id, command, expected) -> None:
    """GPD attribute reports are passed to the reported clusters as ZCL reports."""
    device = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    device.server_cluster_ids = [
        Metering.cluster_id,
        ElectricalMeasurement.cluster_id,
        VENDOR_CLUSTER_ID,
    ]
    device.add_clusters()

    reports = []

    for cluster in device.endpoints[None].in_clusters.values():
        cluster.on_event(AttributeReportedEvent.event_type, reports.append)

    device.packet_received(
        make_packet(1, command_id=command_id, payload=command.serialize())
    )

    assert [
        (r.cluster_id, r.attribute_id, r.manufacturer_code, r.value) for r in reports
    ] == expected
    assert all(r.endpoint_id is None for r in reports)


def test_endpoint(app) -> None:
    """A SrcID-addressed GPD's clusters belong to its single endpoint, without ID."""
    device = GreenPowerDevice(
        app, application_id=ApplicationID.SrcID, src_id=SrcID(0x12345678)
    )
    device.server_cluster_ids = [Metering.cluster_id]
    device.client_cluster_ids = [OnOff.cluster_id]
    device.add_clusters()

    (endpoint,) = device.non_zdo_endpoints

    assert endpoint is device.endpoints[None]
    assert endpoint.device is device
    assert endpoint.endpoint_id is None
    assert [cluster.cluster_id for cluster in endpoint.clusters] == [
        Metering.cluster_id,
        OnOff.cluster_id,
    ]
    assert all(cluster.endpoint is endpoint for cluster in endpoint.clusters)
    assert repr(endpoint) == "<GreenPowerEndpoint in=[0x0702] out=[0x0006]>"
