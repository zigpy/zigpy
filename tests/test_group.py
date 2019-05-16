from unittest import mock

import pytest

import zigpy.types as t
from zigpy.application import ControllerApplication
import zigpy.device
import zigpy.group
import zigpy.endpoint


FIXTURE_GRP_ID = 0x1001
FIXTURE_GRP_NAME = 'fixture group'


@pytest.fixture
def endpoint():
    app_mock = mock.MagicMock(spec_set=ControllerApplication)
    ieee = t.EUI64(map(t.uint8_t, [0, 1, 2, 3, 4, 5, 6, 7]))
    dev = zigpy.device.Device(app_mock, ieee, 65535)
    return zigpy.endpoint.Endpoint(dev, 3)


@pytest.fixture
def groups():
    app_mock = mock.MagicMock(spec_set=ControllerApplication)
    groups = zigpy.group.Groups(app_mock)
    groups.listener_event = mock.MagicMock()
    groups.add_group(FIXTURE_GRP_ID, FIXTURE_GRP_NAME, suppress_event=True)
    return groups


@pytest.fixture
def group():
    groups_mock = mock.MagicMock(spec_set=zigpy.group.Groups)
    return zigpy.group.Group(FIXTURE_GRP_ID, FIXTURE_GRP_NAME, groups_mock)


def test_add_group(groups, monkeypatch):
    monkeypatch.setattr(zigpy.group, 'Group',
                        mock.MagicMock(spec_set=zigpy.group.Group,
                                       return_value=mock.sentinel.group))
    grp_id, grp_name = 0x1234, "Group Name for 0x1234 group."

    assert grp_id not in groups
    ret = groups.add_group(grp_id, grp_name)
    assert groups.listener_event.call_count == 1
    assert ret is mock.sentinel.group

    groups.listener_event.reset_mock()
    ret = groups.add_group(grp_id, grp_name)
    assert groups.listener_event.call_count == 0
    assert ret is mock.sentinel.group


def test_add_group_no_evt(groups, monkeypatch):
    monkeypatch.setattr(zigpy.group, 'Group',
                        mock.MagicMock(spec_set=zigpy.group.Group,
                                       return_value=mock.sentinel.group))
    grp_id, grp_name = 0x1234, "Group Name for 0x1234 group."

    assert grp_id not in groups
    ret = groups.add_group(grp_id, grp_name, suppress_event=True)
    assert groups.listener_event.call_count == 0
    assert ret is mock.sentinel.group

    groups.listener_event.reset_mock()
    ret = groups.add_group(grp_id, grp_name)
    assert groups.listener_event.call_count == 0
    assert ret is mock.sentinel.group


def test_pop_group_id(groups, endpoint):
    group = groups[FIXTURE_GRP_ID]
    group.add_member(endpoint)
    group.remove_member = mock.MagicMock()
    groups.listener_event.reset_mock()

    assert FIXTURE_GRP_ID in groups
    grp = groups.pop(FIXTURE_GRP_ID)

    assert isinstance(grp, zigpy.group.Group)
    assert FIXTURE_GRP_ID not in groups
    assert groups.listener_event.call_count == 1
    assert group.remove_member.call_count == 1
    assert group.remove_member.call_args[0][0] is endpoint

    with pytest.raises(KeyError):
        groups.pop(FIXTURE_GRP_ID)


def test_pop_group(groups, endpoint):
    assert FIXTURE_GRP_ID in groups
    group = groups[FIXTURE_GRP_ID]
    group.add_member(endpoint)
    group.remove_member = mock.MagicMock()
    groups.listener_event.reset_mock()

    grp = groups.pop(group)
    assert isinstance(grp, zigpy.group.Group)
    assert FIXTURE_GRP_ID not in groups
    assert groups.listener_event.call_count == 1
    assert group.remove_member.call_count == 1
    assert group.remove_member.call_args[0][0] is endpoint

    with pytest.raises(KeyError):
        groups.pop(grp)


def test_group_add_member(group, endpoint):
    listener = mock.MagicMock()
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
    listener = mock.MagicMock()
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
    listener = mock.MagicMock()
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
