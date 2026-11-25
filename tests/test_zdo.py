import asyncio
import logging

import pytest

from tests.conftest import make_node_desc
from zigpy import zdo
import zigpy.device
import zigpy.types as t
from zigpy.zdo import commands as zdo_c
import zigpy.zdo.types as zdo_types

from .async_mock import AsyncMock, MagicMock

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


@pytest.fixture
def zdo_f(app):
    ieee = t.EUI64(map(t.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))
    dev = zigpy.device.Device(app, ieee, 65535)
    dev.request = AsyncMock()

    app.devices[dev.ieee] = dev

    return zdo.ZDO(dev)


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


async def test_send_zdo_command(zdo_f):
    rsp = zdo_c.NodeDescRsp(
        status=zdo_types.Status.SUCCESS,
        nwk_addr_of_interest=0x1234,
        node_descriptor=make_node_desc(),
    )
    zdo_f.device.request.return_value = rsp

    result = await zdo_f.device.send_zdo_command(
        zdo_c.NodeDescReq(nwk_addr_of_interest=0x1234),
        response_type=zdo_c.NodeDescRsp,
    )

    assert result is rsp
    assert len(zdo_f.device.request.mock_calls) == 1

    kwargs = zdo_f.device.request.mock_calls[0].kwargs
    assert kwargs["cluster"] == zdo_types.ZDOCmd.Node_Desc_req
    assert kwargs["expect_reply"] is True
    assert kwargs["data"] == bytes([kwargs["sequence"]]) + b"\x34\x12"


async def test_send_zdo_command_no_response(zdo_f):
    result = await zdo_f.device.send_zdo_command(
        zdo_c.MgmtLeaveRsp(status=zdo_types.Status.SUCCESS), tsn=0x23
    )

    assert result is None

    kwargs = zdo_f.device.request.mock_calls[0].kwargs
    assert kwargs["cluster"] == zdo_types.ZDOCmd.Mgmt_Leave_rsp
    assert kwargs["expect_reply"] is False
    assert kwargs["sequence"] == 0x23
    assert kwargs["data"] == b"\x23\x00"


@pytest.mark.parametrize("aps_encryption", [False, True])
async def test_send_zdo_command_aps_encryption(zdo_f, aps_encryption):
    await zdo_f.device.send_zdo_command(
        zdo_c.MgmtLeaveRsp(status=zdo_types.Status.SUCCESS),
        aps_encryption=aps_encryption,
    )
    assert zdo_f.device.request.mock_calls[0].kwargs["aps_encryption"] is aps_encryption


@pytest.mark.parametrize(
    ("method", "command_id", "response"),
    [
        ("bind", zdo_types.ZDOCmd.Bind_req, zdo_c.BindRsp),
        ("unbind", zdo_types.ZDOCmd.Unbind_req, zdo_c.UnbindRsp),
    ],
)
async def test_bind_unbind(zdo_f, method, command_id, response):
    zdo_f.device.request.return_value = response(status=zdo_types.Status.SUCCESS)

    cluster = MagicMock()
    cluster.endpoint.endpoint_id = 1
    cluster.cluster_id = 1026
    rsp = await getattr(zdo_f, method)(cluster)

    assert rsp == response(status=zdo_types.Status.SUCCESS)
    assert len(zdo_f.device.request.mock_calls) == 1
    assert zdo_f.device.request.mock_calls[0].kwargs["cluster"] == command_id


@pytest.mark.parametrize(
    ("remove_children", "rejoin", "flags"),
    [
        (False, False, 0),
        (False, True, 0x80),
        (True, False, 0x40),
        (True, True, 0xC0),
    ],
)
async def test_leave(zdo_f, remove_children, rejoin, flags):
    """Test ZDO leave request options."""
    zdo_f.device.request.return_value = zdo_c.MgmtLeaveRsp(
        status=zdo_types.Status.SUCCESS
    )
    await zdo_f.leave(remove_children, rejoin)

    kwargs = zdo_f.device.request.mock_calls[0].kwargs
    assert kwargs["cluster"] == zdo_types.ZDOCmd.Mgmt_Leave_req
    assert kwargs["data"][1:] == (
        zdo_c.MgmtLeaveReq(
            device_address=t.EUI64.convert("07:06:05:04:03:02:01:00"), options=flags
        ).serialize()
    )


async def test_permit(zdo_f):
    zdo_f.device.request.return_value = zdo_c.MgmtPermitJoiningRsp(
        status=zdo_types.Status.SUCCESS
    )
    await zdo_f.permit()
    assert len(zdo_f.device.request.mock_calls) == 1
    assert zdo_f.device.request.mock_calls[0].kwargs["cluster"] == 0x0036


async def test_broadcast(app):
    await zigpy.zdo.broadcast(
        app,
        zdo_c.MgmtPermitJoiningReq(permit_duration=60, tc_significant=False),
        0,
        0,
    )

    assert len(app.send_packet.mock_calls) == 1

    packet = app.send_packet.mock_calls[0].args[0]
    assert packet.dst.addr_mode == t.AddrMode.Broadcast
    assert packet.cluster_id == 0x0036
    assert packet.data.serialize()[1:] == b"\x3c\x00"


@pytest.mark.parametrize(
    ("profile", "match_list"),
    [
        (260, [1]),
        (0, []),
    ],
)
async def test_handle_match_desc(zdo_f, profile, match_list):
    zdo_f.handle_message(
        make_frame(
            zdo_c.MatchDescReq(
                nwk_addr_of_interest=0x0000,
                profile_id=profile,
                in_cluster_list=[],
                out_cluster_list=[],
            ),
            tsn=0x12,
        )
    )
    await asyncio.sleep(0)

    kwargs = zdo_f.device.request.mock_calls[0].kwargs
    assert kwargs["cluster"] == zdo_types.ZDOCmd.Match_Desc_rsp
    assert kwargs["sequence"] == 0x12
    rsp = zdo_c.ZDOCommand.deserialize(kwargs["cluster"], kwargs["data"])
    assert rsp.command.match_list == match_list


@pytest.mark.parametrize(
    ("request_type", "num_assoc_dev"),
    [
        (zdo_types.AddrRequestType.Single, None),
        (zdo_types.AddrRequestType.Extended, 0),
    ],
)
async def test_handle_addr_reqs(zdo_f, request_type, num_assoc_dev):
    node_info = zdo_f._device.application.state.node_info

    zdo_f.handle_message(
        make_frame(
            zdo_c.NwkAddrReq(
                ieee_addr=node_info.ieee, request_type=request_type, start_index=0
            ),
            tsn=0x10,
        )
    )
    zdo_f.handle_message(
        make_frame(
            zdo_c.IeeeAddrReq(
                nwk_addr_of_interest=node_info.nwk,
                request_type=request_type,
                start_index=0,
            ),
            tsn=0x11,
        )
    )
    await asyncio.sleep(0)

    assert len(zdo_f.device.request.mock_calls) == 2

    for request_call, rsp_type, tsn in zip(
        zdo_f.device.request.mock_calls,
        [zdo_c.NwkAddrRsp, zdo_c.IeeeAddrRsp],
        [0x10, 0x11],
        strict=True,
    ):
        assert request_call.kwargs["sequence"] == tsn
        rsp = zdo_c.ZDOCommand.deserialize(
            request_call.kwargs["cluster"], request_call.kwargs["data"]
        )
        assert rsp.command == rsp_type(
            status=zdo_types.Status.SUCCESS,
            ieee_addr=node_info.ieee,
            nwk_addr=node_info.nwk,
            num_assoc_dev=num_assoc_dev,
        )


@pytest.mark.parametrize(
    ("logical_type", "rx_on_when_idle", "expected_retries"),
    [
        (zdo_types.LogicalType.EndDevice, False, 0),
        (zdo_types.LogicalType.EndDevice, True, None),
        (zdo_types.LogicalType.Router, False, None),
    ],
)
async def test_address_replies_retries(
    zdo_f, logical_type, rx_on_when_idle, expected_retries
):
    """Address replies are not retried for devices that may be asleep."""
    zdo_f._device.node_desc = make_node_desc(logical_type=logical_type)
    if rx_on_when_idle:
        node_desc = zdo_f._device.node_desc
        zdo_f._device.node_desc = node_desc.replace(
            mac_capability_flags=node_desc.mac_capability_flags
            | zdo_types.NodeDescriptor.MACCapabilityFlags.RxOnWhenIdle
        )
    node_info = zdo_f._device.application.state.node_info
    zdo_f.handle_nwk_addr_req(
        make_frame(
            zdo_c.NwkAddrReq(
                ieee_addr=node_info.ieee,
                request_type=zdo_types.AddrRequestType.Single,
                start_index=0,
            )
        )
    )
    zdo_f.handle_ieee_addr_req(
        make_frame(
            zdo_c.IeeeAddrReq(
                nwk_addr_of_interest=node_info.nwk,
                request_type=zdo_types.AddrRequestType.Single,
                start_index=0,
            )
        )
    )
    await asyncio.sleep(0)

    assert len(zdo_f._device.request.mock_calls) == 2

    for request_call in zdo_f._device.request.mock_calls:
        assert request_call.kwargs["retries"] == expected_retries


def test_handle_announce(zdo_f):
    dev = zdo_f._device
    listener = MagicMock()
    zdo_f.add_listener(listener)

    dev._application.devices.pop(dev.ieee)
    frame = make_frame(
        zdo_c.DeviceAnnce(
            nwk_addr=dev.nwk,
            ieee_addr=dev.ieee,
            capability=zdo_types.MACCapabilityFlags.NONE,
        )
    )
    zdo_f.handle_message(frame)

    assert listener.device_announce.mock_calls == [((dev,),)]
    assert listener.zdo_device_annce.mock_calls == [((dev, None, frame),)]


def test_handle_permit_join(zdo_f):
    listener = MagicMock()
    zdo_f.add_listener(listener)
    zdo_f.handle_message(
        make_frame(zdo_c.MgmtPermitJoiningReq(permit_duration=100, tc_significant=True))
    )
    assert listener.permit_duration.mock_calls == [((100,),)]


def test_handle_unsupported(zdo_f):
    listener = MagicMock()
    zdo_f.add_listener(listener)
    zdo_f.handle_message(zdo_c.ZDOCommand.deserialize(0xFFFF, b"\x10\xaa"))

    assert len(listener.zdo_undefined_0xffff.mock_calls) == 1
    assert len(zdo_f.device.request.mock_calls) == 0


def test_device_accessor(zdo_f):
    assert zdo_f.device.nwk == 65535
