import pytest

import zigpy.device
import zigpy.endpoint
import zigpy.group
import zigpy.types as t
import zigpy.zcl

from .async_mock import AsyncMock, MagicMock, call, sentinel

FIXTURE_GRP_ID = 0x1001
FIXTURE_GRP_NAME = "fixture group"


@pytest.fixture
def endpoint(app_mock):
    ieee = t.EUI64(map(t.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))
    dev = zigpy.device.Device(app_mock, ieee, 65535)
    return zigpy.endpoint.Endpoint(dev, 3)


@pytest.fixture
def groups(app_mock):
    groups = zigpy.group.Groups(app_mock)
    groups.listener_event = MagicMock()
    groups.add_group(FIXTURE_GRP_ID, FIXTURE_GRP_NAME, suppress_event=True)
    return groups


@pytest.fixture
def group():
    groups_mock = MagicMock(spec_set=zigpy.group.Groups)
    groups_mock.application.mrequest = AsyncMock()
    return zigpy.group.Group(FIXTURE_GRP_ID, FIXTURE_GRP_NAME, groups_mock)


@pytest.fixture
def group_endpoint(group):
    group.request = AsyncMock()
    return zigpy.group.GroupEndpoint(group)


def test_add_group(groups, monkeypatch):
    monkeypatch.setattr(
        zigpy.group,
        "Group",
        MagicMock(spec_set=zigpy.group.Group, return_value=sentinel.group),
    )
    grp_id, grp_name = 0x1234, "Group Name for 0x1234 group."

    assert grp_id not in groups
    ret = groups.add_group(grp_id, grp_name)
    assert groups.listener_event.call_count == 1
    assert ret is sentinel.group

    groups.listener_event.reset_mock()
    ret = groups.add_group(grp_id, grp_name)
    assert groups.listener_event.call_count == 0
    assert ret is sentinel.group


def test_add_group_no_evt(groups, monkeypatch):
    monkeypatch.setattr(
        zigpy.group,
        "Group",
        MagicMock(spec_set=zigpy.group.Group, return_value=sentinel.group),
    )
    grp_id, grp_name = 0x1234, "Group Name for 0x1234 group."

    assert grp_id not in groups
    ret = groups.add_group(grp_id, grp_name, suppress_event=True)
    assert groups.listener_event.call_count == 0
    assert ret is sentinel.group

    groups.listener_event.reset_mock()
    ret = groups.add_group(grp_id, grp_name)
    assert groups.listener_event.call_count == 0
    assert ret is sentinel.group


def test_pop_group_id(groups, endpoint):
    group = groups[FIXTURE_GRP_ID]
    group.add_member(endpoint)
    group.remove_member = MagicMock(side_effect=group.remove_member)
    groups.listener_event.reset_mock()

    assert FIXTURE_GRP_ID in groups
    grp = groups.pop(FIXTURE_GRP_ID)

    assert isinstance(grp, zigpy.group.Group)
    assert FIXTURE_GRP_ID not in groups
    assert groups.listener_event.call_count == 2
    assert group.remove_member.call_count == 1
    assert group.remove_member.call_args[0][0] is endpoint

    with pytest.raises(KeyError):
        groups.pop(FIXTURE_GRP_ID)


def test_pop_group(groups, endpoint):
    assert FIXTURE_GRP_ID in groups
    group = groups[FIXTURE_GRP_ID]
    group.add_member(endpoint)
    group.remove_member = MagicMock(side_effect=group.remove_member)
    groups.listener_event.reset_mock()

    grp = groups.pop(group)
    assert isinstance(grp, zigpy.group.Group)
    assert FIXTURE_GRP_ID not in groups
    assert groups.listener_event.call_count == 2
    assert group.remove_member.call_count == 1
    assert group.remove_member.call_args[0][0] is endpoint

    with pytest.raises(KeyError):
        groups.pop(grp)


def test_group_add_member(group, endpoint):
    listener = MagicMock()
    group.add_listener(listener)

    assert endpoint.unique_id not in group.members
    assert FIXTURE_GRP_ID not in endpoint.member_of
    group.add_member(endpoint)
    assert endpoint.unique_id in group.members
    assert FIXTURE_GRP_ID in endpoint.member_of
    assert listener.member_added.call_count == 1
    assert listener.member_removed.call_count == 0

    listener.reset_mock()
    group.add_member(endpoint)
    assert listener.member_added.call_count == 0
    assert listener.member_removed.call_count == 0

    group.__repr__()
    assert group.name == FIXTURE_GRP_NAME

    with pytest.raises(ValueError):
        group.add_member(endpoint.endpoint_id)


def test_group_add_member_no_evt(group, endpoint):
    listener = MagicMock()
    group.add_listener(listener)

    assert endpoint.unique_id not in group
    group.add_member(endpoint, suppress_event=True)
    assert endpoint.unique_id in group
    assert FIXTURE_GRP_ID in endpoint.member_of
    assert listener.member_added.call_count == 0
    assert listener.member_removed.call_count == 0


def test_noname_group():
    group = zigpy.group.Group(FIXTURE_GRP_ID)
    assert group.name.startswith("No name group ")


def test_group_remove_member(group, endpoint):
    listener = MagicMock()
    group.add_listener(listener)

    group.add_member(endpoint, suppress_event=True)

    assert endpoint.unique_id in group
    assert FIXTURE_GRP_ID in endpoint.member_of
    group.remove_member(endpoint)
    assert endpoint.unique_id not in group
    assert FIXTURE_GRP_ID not in endpoint.member_of
    assert listener.member_added.call_count == 0
    assert listener.member_removed.call_count == 1


def test_group_magic_methods(group, endpoint):
    group.add_member(endpoint, suppress_event=True)

    assert endpoint.unique_id in group.members
    assert endpoint.unique_id in group
    assert group[endpoint.unique_id] is endpoint


def test_groups_properties(groups: zigpy.group.Groups):
    """Test groups properties."""
    assert groups.application is not None


def test_group_properties(group: zigpy.group.Group):
    """Test group properties."""
    assert group.application is not None
    assert group.groups is not None
    assert isinstance(group.endpoint, zigpy.group.GroupEndpoint)


def test_group_cluster_from_cluster_id():
    """Group cluster by cluster id."""

    cls = zigpy.group.GroupCluster.from_id(MagicMock(), 6)
    assert isinstance(cls, zigpy.zcl.Cluster)

    with pytest.raises(KeyError):
        zigpy.group.GroupCluster.from_id(MagicMock(), 0xFFFF)


def test_group_cluster_from_cluster_name():
    """Group cluster by cluster name."""

    cls = zigpy.group.GroupCluster.from_attr(MagicMock(), "on_off")
    assert isinstance(cls, zigpy.zcl.Cluster)

    with pytest.raises(AttributeError):
        zigpy.group.GroupCluster.from_attr(MagicMock(), "no_such_cluster")


async def test_group_ep_request(group_endpoint):
    on_off = zigpy.group.GroupCluster.from_attr(group_endpoint, "on_off")
    await on_off.on()

    assert group_endpoint.device.request.mock_calls == [
        call(
            260,  # profile
            0x0006,  # cluster
            1,  # sequence
            b"\x01\x01\x01",  # data
        )
    ]


def test_group_ep_reply(group_endpoint):
    group_endpoint.request = MagicMock()
    group_endpoint.reply(
        sentinel.cluster,
        sentinel.seq,
        sentinel.data,
        sentinel.extra_arg,
        extra_kwarg=sentinel.extra_kwarg,
    )
    assert group_endpoint.request.call_count == 1
    assert group_endpoint.request.call_args[0][0] is sentinel.cluster
    assert group_endpoint.request.call_args[0][1] is sentinel.seq
    assert group_endpoint.request.call_args[0][2] is sentinel.data
    assert group_endpoint.request.call_args[0][3] is sentinel.extra_arg
    assert group_endpoint.request.call_args[1]["extra_kwarg"] is sentinel.extra_kwarg


def test_group_ep_by_cluster_id(group_endpoint, monkeypatch):
    clusters = {}
    group_endpoint._clusters = MagicMock(return_value=clusters)
    group_endpoint._clusters.__getitem__.side_effect = clusters.__getitem__
    group_endpoint._clusters.__setitem__.side_effect = clusters.__setitem__

    group_cluster_mock = MagicMock()
    group_cluster_mock.from_id.return_value = sentinel.group_cluster
    monkeypatch.setattr(zigpy.group, "GroupCluster", group_cluster_mock)

    assert len(clusters) == 0
    cluster = group_endpoint[6]
    assert cluster is sentinel.group_cluster
    assert group_cluster_mock.from_id.call_count == 1

    assert len(clusters) == 1
    cluster = group_endpoint[6]
    assert cluster is sentinel.group_cluster
    assert group_cluster_mock.from_id.call_count == 1


def test_group_ep_by_cluster_attr(group_endpoint, monkeypatch):
    cluster_by_attr = {}
    group_endpoint._cluster_by_attr = MagicMock(return_value=cluster_by_attr)
    group_endpoint._cluster_by_attr.__getitem__.side_effect = (
        cluster_by_attr.__getitem__
    )
    group_endpoint._cluster_by_attr.__setitem__.side_effect = (
        cluster_by_attr.__setitem__
    )

    group_cluster_mock = MagicMock()
    group_cluster_mock.from_attr.return_value = sentinel.group_cluster
    monkeypatch.setattr(zigpy.group, "GroupCluster", group_cluster_mock)

    assert len(cluster_by_attr) == 0
    cluster = group_endpoint.on_off
    assert cluster is sentinel.group_cluster
    assert group_cluster_mock.from_attr.call_count == 1

    assert len(cluster_by_attr) == 1
    cluster = group_endpoint.on_off
    assert cluster is sentinel.group_cluster
    assert group_cluster_mock.from_attr.call_count == 1


async def test_group_request(group):
    group.application.send_packet = AsyncMock()
    data = b"\x01\x02\x03\x04\x05"
    res = await group.request(
        sentinel.profile,
        sentinel.cluster,
        sentinel.sequence,
        data,
    )
    assert group.application.send_packet.call_count == 1
    packet = group.application.send_packet.mock_calls[0].args[0]

    assert packet.dst == t.AddrModeAddress(
        addr_mode=t.AddrMode.Group, address=group.group_id
    )
    assert packet.profile_id is sentinel.profile
    assert packet.cluster_id is sentinel.cluster
    assert packet.tsn is sentinel.sequence
    assert packet.data.serialize() == data

    assert res.status is zigpy.zcl.foundation.Status.SUCCESS
    assert res.command_id == data[2]


def test_update_group_membership_remove_member(groups, endpoint):
    """New device is not member of the old groups."""

    groups[FIXTURE_GRP_ID].add_member(endpoint)

    assert endpoint.unique_id in groups[FIXTURE_GRP_ID]
    groups.update_group_membership(endpoint, set())

    assert endpoint.unique_id not in groups[FIXTURE_GRP_ID]


def test_update_group_membership_remove_add(groups, endpoint):
    """New device is not member of the old group, but member of new one."""

    groups[FIXTURE_GRP_ID].add_member(endpoint)

    assert endpoint.unique_id in groups[FIXTURE_GRP_ID]
    new_group_id = 0x1234
    assert new_group_id not in groups
    groups.update_group_membership(endpoint, {new_group_id})
    assert endpoint.unique_id not in groups[FIXTURE_GRP_ID]
    assert new_group_id in groups
    assert endpoint.unique_id in groups[new_group_id]


def test_update_group_membership_add_existing(groups, endpoint):
    """New device is member of new and existing groups."""

    groups[FIXTURE_GRP_ID].add_member(endpoint)

    assert endpoint.unique_id in groups[FIXTURE_GRP_ID]
    new_group_id = 0x1234
    groups.add_group(new_group_id)
    assert new_group_id in groups
    groups.update_group_membership(endpoint, {new_group_id, FIXTURE_GRP_ID})
    assert endpoint.unique_id in groups[FIXTURE_GRP_ID]
    assert new_group_id in groups
    assert endpoint.unique_id in groups[new_group_id]
