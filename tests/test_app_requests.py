import asyncio

import pytest

import zigpy.device
import zigpy.exceptions
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import Basic, Groups, Ota, PollControl
import zigpy.zdo.commands as zdo_c
import zigpy.zdo.types as zdo_t

from .conftest import make_node_desc

NWK = t.NWK(0x1234)
POLICY = zigpy.device.SendPolicy(
    timeout=0.05, extended_timeout=False, retries=0, retry_delay=0
)

READ_ATTRIBUTES_RSP = foundation.ReadAttributesResponse(
    status_records=[
        foundation.ReadAttributeRecord(
            attrid=0x0004,
            status=foundation.Status.SUCCESS,
            value=foundation.TypeValue(
                type=foundation.DataTypeId.string, value=t.CharacterString("abc")
            ),
        )
    ]
)


def zcl_packet(
    *,
    tsn: int,
    command_id: int,
    payload: bytes,
    endpoint: int = 1,
    cluster_id: int = Basic.cluster_id,
    direction: foundation.Direction = foundation.Direction.Server_to_Client,
    general: bool = True,
) -> t.ZigbeePacket:
    frame_control = (
        foundation.FrameControl.general(direction=direction)
        if general
        else foundation.FrameControl.cluster(direction=direction)
    )
    header = foundation.ZCLHeader(
        frame_control=frame_control, tsn=tsn, command_id=command_id
    )

    return t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=NWK),
        src_ep=endpoint,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=0x0000),
        dst_ep=endpoint,
        profile_id=0x0104,
        cluster_id=cluster_id,
        data=t.SerializableBytes(header.serialize() + payload),
    )


def sent_zcl(app) -> list[tuple[t.ZigbeePacket, foundation.ZCLHeader, bytes]]:
    """The ZCL frames sent so far."""
    packets = [c.args[0] for c in app.send_packet.mock_calls]

    return [
        (packet, *foundation.ZCLHeader.deserialize(packet.data.serialize()))
        for packet in packets
    ]


def respond(app, make_responses) -> None:
    """Answer each sent request with the packets `make_responses(tsn)` returns."""

    async def send_packet(packet: t.ZigbeePacket) -> None:
        for response in make_responses(packet.tsn):
            asyncio.get_running_loop().call_soon(app.packet_received, response)

    app.send_packet.side_effect = send_packet


@pytest.mark.parametrize("manufacturer", [None, 0x115F])
async def test_read_attributes(app, manufacturer):
    respond(
        app,
        lambda tsn: [
            zcl_packet(
                tsn=tsn,
                command_id=foundation.GeneralCommand.Read_Attributes_rsp,
                payload=READ_ATTRIBUTES_RSP.serialize(),
            )
        ],
    )

    rsp = await app.send_zcl_command(
        NWK,
        1,
        Basic.cluster_id,
        foundation.ReadAttributes(attribute_ids=[0x0004]),
        foundation.ReadAttributesResponse,
        policy=POLICY,
        manufacturer=manufacturer,
    )

    assert rsp == READ_ATTRIBUTES_RSP

    [(request, header, payload)] = sent_zcl(app)

    assert request.dst == t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=NWK)
    assert request.src_ep == request.dst_ep == 1
    assert request.profile_id == 0x0104
    assert request.cluster_id == Basic.cluster_id
    assert request.tsn == header.tsn
    assert not request.tx_options & t.TransmitOptions.ACK
    assert header.frame_control == foundation.FrameControl.general(
        direction=foundation.Direction.Client_to_Server,
        is_manufacturer_specific=manufacturer is not None,
    )
    assert header.command_id == foundation.GeneralCommand.Read_Attributes
    assert header.manufacturer == manufacturer
    assert payload == t.List[t.uint16_t]([0x0004]).serialize()


async def test_read_attributes_ignores_other_frames(app):
    """Reports, other endpoints, TSNs and directions do not match the response."""
    respond(
        app,
        lambda tsn: [
            zcl_packet(
                tsn=tsn,
                command_id=foundation.GeneralCommand.Report_Attributes,
                payload=b"",
            ),
            zcl_packet(
                tsn=tsn,
                endpoint=2,
                command_id=foundation.GeneralCommand.Read_Attributes_rsp,
                payload=READ_ATTRIBUTES_RSP.serialize(),
            ),
            zcl_packet(
                tsn=(tsn + 1) % 256,
                command_id=foundation.GeneralCommand.Read_Attributes_rsp,
                payload=READ_ATTRIBUTES_RSP.serialize(),
            ),
            zcl_packet(
                tsn=tsn,
                direction=foundation.Direction.Client_to_Server,
                command_id=foundation.GeneralCommand.Read_Attributes_rsp,
                payload=READ_ATTRIBUTES_RSP.serialize(),
            ),
        ],
    )

    with pytest.raises(TimeoutError):
        await app.send_zcl_command(
            NWK,
            1,
            Basic.cluster_id,
            foundation.ReadAttributes(attribute_ids=[0x0004]),
            foundation.ReadAttributesResponse,
            policy=POLICY,
        )


async def test_read_attributes_default_response(app):
    """A rejected request returns the Default Response."""
    default_rsp = foundation.DefaultResponse(
        command_id=foundation.GeneralCommand.Read_Attributes,
        status=foundation.Status.UNSUP_GENERAL_COMMAND,
    )
    respond(
        app,
        lambda tsn: [
            zcl_packet(
                tsn=tsn,
                command_id=foundation.GeneralCommand.Default_Response,
                payload=default_rsp.serialize(),
            )
        ],
    )

    rsp = await app.send_zcl_command(
        NWK,
        1,
        Basic.cluster_id,
        foundation.ReadAttributes(attribute_ids=[0x0004]),
        foundation.ReadAttributesResponse,
        policy=POLICY,
    )

    assert rsp == default_rsp


async def test_read_attributes_parsing_error(app):
    respond(
        app,
        lambda tsn: [
            zcl_packet(
                tsn=tsn,
                command_id=foundation.GeneralCommand.Read_Attributes_rsp,
                payload=b"\x04",
            )
        ],
    )

    with pytest.raises(zigpy.exceptions.ParsingError):
        await app.send_zcl_command(
            NWK,
            1,
            Basic.cluster_id,
            foundation.ReadAttributes(attribute_ids=[0x0004]),
            foundation.ReadAttributesResponse,
            policy=POLICY,
        )


async def test_cluster_command_without_reply(app):
    """A check-in response is a cluster command sent without waiting for a reply."""
    rsp = await app.send_zcl_command(
        NWK,
        1,
        PollControl.cluster_id,
        PollControl.ServerCommandDefs.checkin_response.schema(
            start_fast_polling=True, fast_poll_timeout=40
        ),
        policy=POLICY,
        tsn=0x42,
    )

    assert rsp is None

    [(request, header, payload)] = sent_zcl(app)

    assert request.tsn == 0x42
    assert request.tx_options & t.TransmitOptions.ACK
    assert header.frame_control == foundation.FrameControl.cluster(
        direction=foundation.Direction.Client_to_Server
    )
    assert header.tsn == 0x42
    assert header.command_id == PollControl.ServerCommandDefs.checkin_response.id
    assert payload == (
        PollControl.ServerCommandDefs.checkin_response.schema(
            start_fast_polling=True, fast_poll_timeout=40
        ).serialize()
    )


async def test_cluster_command_server_to_client(app):
    """Commands sent as the server, like an image notify, skip default responses."""
    await app.send_zcl_command(
        NWK,
        1,
        Ota.cluster_id,
        Ota.ClientCommandDefs.image_notify.schema(
            payload_type=Ota.ImageNotifyCommand.PayloadType.QueryJitter,
            query_jitter=100,
        ),
        policy=POLICY,
        direction=foundation.Direction.Server_to_Client,
    )

    [(_, header, _)] = sent_zcl(app)

    assert header.frame_control == foundation.FrameControl.cluster(
        direction=foundation.Direction.Server_to_Client
    )
    assert header.frame_control.disable_default_response


VIEW = Groups.ServerCommandDefs.view
VIEW_RESPONSE = Groups.ClientCommandDefs.view_response


def view_response_packet(tsn: int, *, command_id: int, payload: bytes, general=False):
    return zcl_packet(
        tsn=tsn,
        cluster_id=Groups.cluster_id,
        general=general,
        command_id=command_id,
        payload=payload,
    )


async def test_cluster_response(app):
    """Cluster-specific responses are parsed with the cluster's definitions."""
    view_response = VIEW_RESPONSE.schema(
        status=foundation.Status.SUCCESS, group_id=0x0002, group_name="Group"
    )
    respond(
        app,
        lambda tsn: [
            view_response_packet(
                tsn, command_id=VIEW_RESPONSE.id, payload=view_response.serialize()
            )
        ],
    )

    rsp = await app.send_zcl_command(
        NWK,
        1,
        Groups.cluster_id,
        VIEW.schema(group_id=0x0002),
        VIEW_RESPONSE.schema,
        policy=POLICY,
    )

    assert rsp == view_response


async def test_unknown_cluster_response(app):
    """Responses without a definition are parsed with the expected type."""
    respond(
        app,
        lambda tsn: [
            zcl_packet(
                tsn=tsn,
                cluster_id=0xFC00,
                general=False,
                command_id=VIEW_RESPONSE.id,
                payload=VIEW_RESPONSE.schema(
                    status=foundation.Status.SUCCESS, group_id=0x0002, group_name=""
                ).serialize(),
            )
        ],
    )

    rsp = await app.send_zcl_command(
        NWK,
        1,
        0xFC00,
        VIEW.schema(group_id=0x0002),
        VIEW_RESPONSE.schema,
        policy=POLICY,
    )

    assert rsp == VIEW_RESPONSE.schema(
        status=foundation.Status.SUCCESS, group_id=0x0002, group_name=""
    )


@pytest.mark.parametrize(
    ("general", "command_id", "payload", "error"),
    [
        # Malformed response
        (False, VIEW_RESPONSE.id, b"\x00", zigpy.exceptions.ParsingError),
        # Another cluster-specific command
        (
            False,
            Groups.ClientCommandDefs.add_response.id,
            b"\x00\x02\x00",
            zigpy.exceptions.InvalidResponse,
        ),
        # A general command with the same ID
        (
            True,
            VIEW_RESPONSE.id,
            READ_ATTRIBUTES_RSP.serialize(),
            zigpy.exceptions.InvalidResponse,
        ),
    ],
)
async def test_cluster_response_errors(app, general, command_id, payload, error):
    respond(
        app,
        lambda tsn: [
            view_response_packet(
                tsn, command_id=command_id, payload=payload, general=general
            )
        ],
    )

    with pytest.raises(error):
        await app.send_zcl_command(
            NWK,
            1,
            Groups.cluster_id,
            VIEW.schema(group_id=0x0002),
            VIEW_RESPONSE.schema,
            policy=POLICY,
        )


async def test_unexpected_general_response(app):
    """A general response of another type than expected is invalid."""
    respond(
        app,
        lambda tsn: [
            zcl_packet(
                tsn=tsn,
                command_id=foundation.GeneralCommand.Write_Attributes_rsp,
                payload=b"\x00",
            )
        ],
    )

    with pytest.raises(zigpy.exceptions.InvalidResponse):
        await app.send_zcl_command(
            NWK,
            1,
            Basic.cluster_id,
            foundation.ReadAttributes(attribute_ids=[0x0004]),
            foundation.ReadAttributesResponse,
            policy=POLICY,
        )


def test_get_zcl_sequence_per_nwk(app):
    """Each destination NWK has its own TSN counter."""
    first = [app.get_zcl_sequence(NWK) for _ in range(3)]
    other = app.get_zcl_sequence(t.NWK(0x5678))

    assert first == [1, 2, 3]
    assert other == 1
    assert app.get_zcl_sequence(NWK) == 4


def test_get_zcl_sequence_wraps(app):
    tsns = [app.get_zcl_sequence(NWK) for _ in range(257)]

    assert tsns[254:] == [255, 0, 1]


def test_get_sequence_is_global(app):
    """The broadcast and group counter is apart from the per-NWK counters."""
    # The test app pins `get_sequence`, use the real one
    get_sequence = type(app).get_sequence

    assert [get_sequence(app), get_sequence(app)] == [1, 2]
    assert app.get_zcl_sequence(NWK) == 1
    assert app.get_zdo_sequence(NWK) == 1


def test_zdo_and_zcl_sequences_are_separate(app):
    """ZDO and ZCL TSNs to a NWK are counted apart."""
    assert [app.get_zdo_sequence(NWK) for _ in range(2)] == [1, 2]
    assert [app.get_zcl_sequence(NWK) for _ in range(2)] == [1, 2]
    assert app.get_zdo_sequence(t.NWK(0x5678)) == 1


async def test_device_zdo_sequence(app):
    """A device's ZDO requests use the ZDO counter of its NWK."""
    dev = app.add_device(ieee=t.EUI64.convert("11:22:33:44:55:66:77:88"), nwk=NWK)
    app.get_zdo_sequence(NWK)

    await dev.send_zdo_command(zdo_c.MgmtLeaveRsp(status=zdo_t.Status.SUCCESS))

    [packet] = [c.args[0] for c in app.send_packet.mock_calls]
    assert packet.tsn == 2
    assert app.get_zcl_sequence(NWK) == 1


def test_device_shares_nwk_sequence(app):
    """A device and requests to its NWK draw from one counter."""
    dev = app.add_device(ieee=t.EUI64.convert("11:22:33:44:55:66:77:88"), nwk=NWK)

    assert [dev.get_sequence(), app.get_zcl_sequence(NWK), dev.get_sequence()] == [
        1,
        2,
        3,
    ]


@pytest.mark.parametrize(
    ("node_desc", "timeout", "extended"),
    [
        (None, zigpy.device.APS_REPLY_TIMEOUT_EXTENDED, True),
        (
            make_node_desc(logical_type=zdo_t.LogicalType.EndDevice),
            zigpy.device.APS_REPLY_TIMEOUT_EXTENDED,
            True,
        ),
        (
            make_node_desc(logical_type=zdo_t.LogicalType.Router),
            zigpy.device.APS_REPLY_TIMEOUT,
            False,
        ),
    ],
)
def test_send_policy_from_node_descriptor(node_desc, timeout, extended):
    policy = zigpy.device.SendPolicy.from_node_descriptor(node_desc)

    assert policy == zigpy.device.SendPolicy(
        timeout=timeout,
        extended_timeout=extended,
        retries=zigpy.device.DEFAULT_REQUEST_RETRIES,
        retry_delay=zigpy.device.DEFAULT_REQUEST_RETRY_DELAY,
        limiter=None,
    )
