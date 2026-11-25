import asyncio
import logging

import pytest

from tests.conftest import add_initialized_device, make_ieee, make_node_desc
from zigpy import zdo
import zigpy.device
import zigpy.exceptions
import zigpy.types as t
from zigpy.zdo import commands as zdo_c
import zigpy.zdo.types as zdo_types

from .async_mock import patch

IEEE = "11:22:33:44:55:66:77:88"
IEEE_BYTES = "8877665544332211"


def make_frame(command: zdo_c.ZDOPayload, tsn: int = 0x10) -> zdo_c.ZDOCommand:
    return zdo_c.ZDOCommand(
        command_id=command.command_id, tsn=t.uint8_t(tsn), command=command
    )


def test_commands():
    for command_id, command in zdo_c.ZDO_COMMANDS.items():
        assert command.command_id == command_id
        assert issubclass(command, zdo_c.ZDOPayload)


NWK = t.NWK(0x1234)


@pytest.fixture
def dev(app):
    return add_initialized_device(
        app, nwk=NWK, ieee=t.EUI64.convert("07:06:05:04:03:02:01:00")
    )


def zdo_packet(nwk: t.NWK, frame: zdo_c.ZDOCommand) -> t.ZigbeePacket:
    return t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=nwk),
        src_ep=zdo.ZDO_ENDPOINT,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        dst_ep=zdo.ZDO_ENDPOINT,
        tsn=frame.tsn,
        profile_id=0x0000,
        cluster_id=frame.command_id,
        data=t.SerializableBytes(frame.serialize()),
    )


def sent_frames(app) -> list[tuple[t.ZigbeePacket, zdo_c.ZDOCommand]]:
    """The ZDO frames sent so far."""
    return [
        (
            c.args[0],
            zdo_c.ZDOCommand.deserialize(
                c.args[0].cluster_id, c.args[0].data.serialize()
            ),
        )
        for c in app.send_packet.mock_calls
    ]


def respond(app, responder) -> None:
    """Answer each sent ZDO request with the payload `responder` returns, if any."""

    async def send_packet(packet: t.ZigbeePacket) -> None:
        request = zdo_c.ZDOCommand.deserialize(
            packet.cluster_id, packet.data.serialize()
        )
        response = responder(request.command)

        if response is not None:
            asyncio.get_running_loop().call_soon(
                app.packet_received,
                zdo_packet(packet.dst.address, make_frame(response, tsn=request.tsn)),
            )

    app.send_packet.side_effect = send_packet


async def wait_for_replies() -> None:
    # Replies are sent from tasks
    await asyncio.sleep(0.01)


def test_deserialize(caplog):
    with caplog.at_level(logging.WARNING):
        frame = zdo_c.ZDOCommand.deserialize(0x0002, b"\x01\x02\x03xx")

    assert frame == zdo_c.ZDOCommand(
        command_id=zdo_types.ZDOCmd.Node_Desc_req,
        tsn=1,
        command=zdo_c.NodeDescReq(nwk_addr_of_interest=0x0302),
    )
    assert "Data remains after deserializing ZDO frame" in caplog.text


@pytest.mark.parametrize("payload", [b"", b"\xaa\x55"])
def test_deserialize_unknown(payload):
    """Commands without a schema keep their raw payload."""
    frame = zdo_c.ZDOCommand.deserialize(0x0100, b"\x01" + payload)

    assert frame.command_id == 0x0100
    assert frame.command_id not in list(zdo_types.ZDOCmd)
    assert frame.tsn == 1
    assert frame.command == zdo_c.UnknownCommand(data=payload)
    assert frame.serialize() == b"\x01" + payload


def test_command_id_mismatch():
    with pytest.raises(AssertionError):
        zdo_c.ZDOCommand(
            command_id=zdo_types.ZDOCmd.Node_Desc_rsp,
            tsn=1,
            command=zdo_c.NodeDescReq(nwk_addr_of_interest=0x0302),
        )


@pytest.mark.parametrize(
    ("cluster_id", "data", "expected"),
    [
        # Single device response: no associated device fields
        (
            zdo_types.ZDOCmd.NWK_addr_rsp,
            "00" + IEEE_BYTES + "3412",
            zdo_c.NwkAddrRsp(
                status=zdo_types.Status.SUCCESS,
                ieee_addr=t.EUI64.convert(IEEE),
                nwk_addr=0x1234,
            ),
        ),
        # Extended response with no associated devices: only the count
        (
            zdo_types.ZDOCmd.NWK_addr_rsp,
            "00" + IEEE_BYTES + "3412" + "00",
            zdo_c.NwkAddrRsp(
                status=zdo_types.Status.SUCCESS,
                ieee_addr=t.EUI64.convert(IEEE),
                nwk_addr=0x1234,
                num_assoc_dev=0,
            ),
        ),
        # Extended response with associated devices
        (
            zdo_types.ZDOCmd.IEEE_addr_rsp,
            "00" + IEEE_BYTES + "3412" + "02" + "00" + "0100" + "0200",
            zdo_c.IeeeAddrRsp(
                status=zdo_types.Status.SUCCESS,
                ieee_addr=t.EUI64.convert(IEEE),
                nwk_addr=0x1234,
                num_assoc_dev=2,
                start_index=0,
                nwk_addr_assoc_dev_list=[0x0001, 0x0002],
            ),
        ),
        (
            zdo_types.ZDOCmd.NWK_addr_rsp,
            "81" + IEEE_BYTES + "ffff",
            zdo_c.NwkAddrRsp(
                status=zdo_types.Status.DEVICE_NOT_FOUND,
                ieee_addr=t.EUI64.convert(IEEE),
                nwk_addr=0xFFFF,
            ),
        ),
        (
            zdo_types.ZDOCmd.Node_Desc_rsp,
            "813412",
            zdo_c.NodeDescRsp(
                status=zdo_types.Status.DEVICE_NOT_FOUND, nwk_addr_of_interest=0x1234
            ),
        ),
        (
            zdo_types.ZDOCmd.Power_Desc_rsp,
            "893412",
            zdo_c.PowerDescRsp(
                status=zdo_types.Status.NO_DESCRIPTOR, nwk_addr_of_interest=0x1234
            ),
        ),
        # The length is always present, the descriptor only on success
        (
            zdo_types.ZDOCmd.Simple_Desc_rsp,
            "83341200",
            zdo_c.SimpleDescRsp(
                status=zdo_types.Status.NOT_ACTIVE,
                nwk_addr_of_interest=0x1234,
                length=0,
            ),
        ),
        (
            zdo_types.ZDOCmd.Simple_Desc_rsp,
            "0034120a" + "01" + "0401" + "0001" + "01" + "01" + "0000" + "00",
            zdo_c.SimpleDescRsp(
                status=zdo_types.Status.SUCCESS,
                nwk_addr_of_interest=0x1234,
                length=10,
                simple_descriptor=zdo_types.SimpleDescriptor(
                    endpoint=1,
                    profile=0x0104,
                    device_type=0x0100,
                    device_version=1,
                    input_clusters=[0x0000],
                    output_clusters=[],
                ),
            ),
        ),
        (
            zdo_types.ZDOCmd.Active_EP_rsp,
            "81341200",
            zdo_c.ActiveEpRsp(
                status=zdo_types.Status.DEVICE_NOT_FOUND,
                nwk_addr_of_interest=0x1234,
                active_ep_list=[],
            ),
        ),
        (
            zdo_types.ZDOCmd.Mgmt_Lqi_rsp,
            "84",
            zdo_c.MgmtLqiRsp(status=zdo_types.Status.NOT_SUPPORTED),
        ),
        (
            zdo_types.ZDOCmd.Mgmt_Rtg_rsp,
            "84",
            zdo_c.MgmtRtgRsp(status=zdo_types.Status.NOT_SUPPORTED),
        ),
        (
            zdo_types.ZDOCmd.Mgmt_Bind_rsp,
            "84",
            zdo_c.MgmtBindRsp(status=zdo_types.Status.NOT_SUPPORTED),
        ),
        # An empty binding table has a count of zero and no list
        (
            zdo_types.ZDOCmd.Mgmt_Bind_rsp,
            "00000000",
            zdo_c.MgmtBindRsp(
                status=zdo_types.Status.SUCCESS,
                binding_table_entries=0,
                start_index=0,
                binding_table_list=[],
            ),
        ),
    ],
)
def test_response_round_trip(cluster_id, data, expected):
    """Responses follow the field presence rules of the specification."""
    frame = zdo_c.ZDOCommand.deserialize(cluster_id, bytes.fromhex("05" + data))

    assert frame == zdo_c.ZDOCommand(command_id=cluster_id, tsn=5, command=expected)
    assert frame.serialize() == bytes.fromhex("05" + data)


async def test_send_zdo_command(app, dev):
    rsp = zdo_c.NodeDescRsp(
        status=zdo_types.Status.SUCCESS,
        nwk_addr_of_interest=NWK,
        node_descriptor=make_node_desc(),
    )
    respond(app, lambda request: rsp)

    result = await dev.send_zdo_command(
        zdo_c.NodeDescReq(nwk_addr_of_interest=NWK),
        response_type=zdo_c.NodeDescRsp,
    )

    assert result == rsp

    [(packet, frame)] = sent_frames(app)
    assert packet.dst == t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=NWK)
    assert packet.tsn == frame.tsn
    assert not packet.tx_options & t.TransmitOptions.ACK
    assert frame.command == zdo_c.NodeDescReq(nwk_addr_of_interest=NWK)


async def test_send_zdo_command_without_device(app):
    """Requests are matched by NWK, a device object is not needed."""
    rsp = zdo_c.ActiveEpRsp(
        status=zdo_types.Status.SUCCESS,
        nwk_addr_of_interest=NWK,
        active_ep_list=[1],
    )
    respond(app, lambda request: rsp)

    result = await app.send_zdo_command(
        NWK,
        zdo_c.ActiveEpReq(nwk_addr_of_interest=NWK),
        zdo_c.ActiveEpRsp,
        policy=zigpy.device.SendPolicy.from_node_descriptor(None),
    )

    assert result == rsp
    assert NWK not in [d.nwk for d in app.devices.values()]


async def test_send_zdo_command_timeout(app, dev):
    """A request without a response is retried, then times out."""
    # A response for another request does not match
    respond(
        app,
        lambda request: zdo_c.NodeDescRsp(
            status=zdo_types.Status.DEVICE_NOT_FOUND, nwk_addr_of_interest=NWK
        ),
    )

    with pytest.raises(TimeoutError):
        await app.send_zdo_command(
            NWK,
            zdo_c.ActiveEpReq(nwk_addr_of_interest=NWK),
            zdo_c.ActiveEpRsp,
            policy=zigpy.device.SendPolicy(
                timeout=0.01, extended_timeout=False, retries=1, retry_delay=0
            ),
        )

    packets = [packet for packet, _ in sent_frames(app)]
    assert len(packets) == 2
    assert packets[0].tsn == packets[1].tsn
    assert not packets[0].tx_options & t.TransmitOptions.FORCE_ROUTE_DISCOVERY
    assert packets[1].tx_options & t.TransmitOptions.FORCE_ROUTE_DISCOVERY


async def test_device_send_zdo_command_retries(app, dev, monkeypatch):
    """The device's policy can be overridden per request."""
    monkeypatch.setattr(zigpy.device, "APS_REPLY_TIMEOUT", 0.01)
    respond(app, lambda request: None)

    with pytest.raises(TimeoutError):
        await dev.send_zdo_command(
            zdo_c.ActiveEpReq(nwk_addr_of_interest=NWK),
            response_type=zdo_c.ActiveEpRsp,
            retries=1,
            retry_delay=0,
        )

    assert len(sent_frames(app)) == 2


async def test_send_zdo_command_no_response(app, dev):
    result = await dev.send_zdo_command(
        zdo_c.MgmtLeaveRsp(status=zdo_types.Status.SUCCESS), tsn=0x23
    )

    assert result is None

    [(packet, frame)] = sent_frames(app)
    assert packet.cluster_id == zdo_types.ZDOCmd.Mgmt_Leave_rsp
    assert packet.tsn == 0x23
    assert packet.tx_options & t.TransmitOptions.ACK
    assert packet.data.serialize() == b"\x23\x00"


@pytest.mark.parametrize("aps_encryption", [False, True])
async def test_send_zdo_command_aps_encryption(app, dev, aps_encryption):
    await dev.send_zdo_command(
        zdo_c.MgmtLeaveRsp(status=zdo_types.Status.SUCCESS),
        aps_encryption=aps_encryption,
    )

    [(packet, _)] = sent_frames(app)
    assert bool(packet.tx_options & t.TransmitOptions.APS_Encryption) is (
        aps_encryption
    )


@pytest.mark.parametrize(
    ("method", "request_type", "response"),
    [
        ("bind", zdo_c.BindReq, zdo_c.BindRsp),
        ("unbind", zdo_c.UnbindReq, zdo_c.UnbindRsp),
    ],
)
async def test_bind_unbind(app, dev, method, request_type, response):
    respond(app, lambda request: response(status=zdo_types.Status.SUCCESS))

    ep = dev.add_endpoint(1)
    cluster = ep.add_input_cluster(0x0402)
    rsp = await getattr(dev, method)(cluster)

    assert rsp == response(status=zdo_types.Status.SUCCESS)

    [(_, frame)] = sent_frames(app)
    assert frame.command == request_type(
        src_address=dev.ieee,
        src_endpoint=1,
        cluster_id=0x0402,
        dst_address=app.get_dst_address(cluster),
    )


@pytest.mark.parametrize(
    ("remove_children", "rejoin", "flags"),
    [
        (False, False, 0),
        (False, True, 0x80),
        (True, False, 0x40),
        (True, True, 0xC0),
    ],
)
async def test_leave(app, dev, remove_children, rejoin, flags):
    """Test ZDO leave request options."""
    respond(app, lambda request: zdo_c.MgmtLeaveRsp(status=zdo_types.Status.SUCCESS))
    await dev.leave(remove_children, rejoin)

    [(_, frame)] = sent_frames(app)
    assert frame.command == zdo_c.MgmtLeaveReq(device_address=dev.ieee, options=flags)


async def test_permit(app, dev):
    respond(
        app,
        lambda request: zdo_c.MgmtPermitJoiningRsp(status=zdo_types.Status.SUCCESS),
    )
    await dev.permit(duration=30)

    [(_, frame)] = sent_frames(app)
    assert frame.command == zdo_c.MgmtPermitJoiningReq(
        permit_duration=30, tc_significant=False
    )


async def test_broadcast(app):
    await app.broadcast_zdo_command(
        zdo_c.MgmtPermitJoiningReq(permit_duration=60, tc_significant=False),
        radius=0,
    )

    assert len(app.send_packet.mock_calls) == 1

    packet = app.send_packet.mock_calls[0].args[0]
    assert packet.dst == t.AddrModeAddress(
        addr_mode=t.AddrMode.Broadcast, address=t.BroadcastAddress.RX_ON_WHEN_IDLE
    )
    assert packet.src_ep == packet.dst_ep == 0
    assert packet.profile_id == 0x0000
    assert packet.cluster_id == 0x0036
    assert packet.data.serialize() == bytes([packet.tsn]) + b"\x3c\x00"


@pytest.mark.parametrize(
    ("profile", "match_list"),
    [
        (260, [1]),
        (0, []),
    ],
)
async def test_handle_match_desc(app, dev, profile, match_list):
    app.packet_received(
        zdo_packet(
            NWK,
            make_frame(
                zdo_c.MatchDescReq(
                    nwk_addr_of_interest=0x0000,
                    profile_id=profile,
                    in_cluster_list=[],
                    out_cluster_list=[],
                ),
                tsn=0x12,
            ),
        )
    )
    await wait_for_replies()

    [(packet, frame)] = sent_frames(app)
    assert packet.priority == t.PacketPriority.CRITICAL
    assert frame.tsn == 0x12
    assert frame.command == zdo_c.MatchDescRsp(
        status=zdo_types.Status.SUCCESS,
        nwk_addr_of_interest=app.state.node_info.nwk,
        match_list=match_list,
    )


@pytest.mark.parametrize(
    ("request_type", "num_assoc_dev"),
    [
        (zdo_types.AddrRequestType.Single, None),
        (zdo_types.AddrRequestType.Extended, 0),
    ],
)
async def test_handle_addr_reqs(app, dev, request_type, num_assoc_dev):
    node_info = app.state.node_info

    app.packet_received(
        zdo_packet(
            NWK,
            make_frame(
                zdo_c.NwkAddrReq(
                    ieee_addr=node_info.ieee, request_type=request_type, start_index=0
                ),
                tsn=0x10,
            ),
        )
    )
    app.packet_received(
        zdo_packet(
            NWK,
            make_frame(
                zdo_c.IeeeAddrReq(
                    nwk_addr_of_interest=node_info.nwk,
                    request_type=request_type,
                    start_index=0,
                ),
                tsn=0x11,
            ),
        )
    )
    await wait_for_replies()

    replies = sent_frames(app)
    assert [frame.tsn for _, frame in replies] == [0x10, 0x11]
    assert [frame.command for _, frame in replies] == [
        rsp_type(
            status=zdo_types.Status.SUCCESS,
            ieee_addr=node_info.ieee,
            nwk_addr=node_info.nwk,
            num_assoc_dev=num_assoc_dev,
        )
        for rsp_type in (zdo_c.NwkAddrRsp, zdo_c.IeeeAddrRsp)
    ]


@pytest.mark.parametrize(
    ("logical_type", "rx_on_when_idle", "attempts"),
    [
        # No device object, it may be asleep
        (None, False, 1),
        (zdo_types.LogicalType.EndDevice, False, 1),
        (zdo_types.LogicalType.EndDevice, True, 3),
        (zdo_types.LogicalType.Router, False, 3),
    ],
)
async def test_address_replies_retries(app, logical_type, rx_on_when_idle, attempts):
    """Address replies are not retried for devices that may be asleep."""
    if logical_type is not None:
        dev = add_initialized_device(app, nwk=NWK, ieee=t.EUI64.convert(IEEE))
        dev.node_desc = make_node_desc(logical_type=logical_type)

        if rx_on_when_idle:
            dev.node_desc = dev.node_desc.replace(
                mac_capability_flags=dev.node_desc.mac_capability_flags
                | zdo_types.NodeDescriptor.MACCapabilityFlags.RxOnWhenIdle
            )

    app.send_packet.side_effect = zigpy.exceptions.DeliveryError("Failed")

    with patch.object(app, "_discover_unknown_device"):
        app.packet_received(
            zdo_packet(
                NWK,
                make_frame(
                    zdo_c.NwkAddrReq(
                        ieee_addr=app.state.node_info.ieee,
                        request_type=zdo_types.AddrRequestType.Single,
                        start_index=0,
                    )
                ),
            )
        )

    # Retries are spaced by the default retry delay
    await asyncio.sleep(0.5)

    assert len(app.send_packet.mock_calls) == attempts


@pytest.mark.parametrize(
    "frame",
    [
        make_frame(
            zdo_c.DeviceAnnce(
                nwk_addr=0x1234,
                ieee_addr=t.EUI64.convert(IEEE),
                capability=zdo_types.MACCapabilityFlags.NONE,
            )
        ),
        make_frame(
            zdo_c.MgmtPermitJoiningReq(permit_duration=100, tc_significant=True)
        ),
        zdo_c.ZDOCommand.deserialize(0xFFFF, b"\x10\xaa"),
        # Address requests for another node
        make_frame(
            zdo_c.NwkAddrReq(
                ieee_addr=t.EUI64.convert(IEEE),
                request_type=zdo_types.AddrRequestType.Single,
                start_index=0,
            )
        ),
        make_frame(
            zdo_c.IeeeAddrReq(
                nwk_addr_of_interest=0x1234,
                request_type=zdo_types.AddrRequestType.Single,
                start_index=0,
            )
        ),
    ],
)
async def test_unanswered_requests(app, dev, frame):
    """Frames without a handler, or not addressed to us, are not answered."""
    with patch.object(app, "handle_join"):
        app.packet_received(zdo_packet(NWK, frame))

    await wait_for_replies()

    assert len(app.send_packet.mock_calls) == 0


async def test_unanswered_ieee_source(app):
    """Requests from an IEEE source address cannot be answered by NWK."""
    packet = zdo_packet(
        NWK,
        make_frame(
            zdo_c.MatchDescReq(
                nwk_addr_of_interest=0x0000,
                profile_id=260,
                in_cluster_list=[],
                out_cluster_list=[],
            )
        ),
    ).replace(src=t.AddrModeAddress(addr_mode=t.AddrMode.IEEE, address=make_ieee()))

    with patch.object(app, "_discover_unknown_device"):
        app.packet_received(packet)

    await wait_for_replies()

    assert len(app.send_packet.mock_calls) == 0


async def test_reply_failure(app, dev, caplog):
    """A reply that cannot be delivered is logged, not raised."""
    app.send_packet.side_effect = zigpy.exceptions.DeliveryError("Failed")

    with caplog.at_level(logging.DEBUG):
        app.packet_received(
            zdo_packet(
                NWK,
                make_frame(
                    zdo_c.MatchDescReq(
                        nwk_addr_of_interest=0x0000,
                        profile_id=260,
                        in_cluster_list=[],
                        out_cluster_list=[],
                    )
                ),
            )
        )

        # The reply is retried
        await asyncio.sleep(0.5)

    assert len(app.send_packet.mock_calls) == 3
    assert "Failed to send ZDO reply" in caplog.text
