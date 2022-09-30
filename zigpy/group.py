from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from zigpy import types as t
from zigpy.endpoint import Endpoint
import zigpy.profiles.zha as zha_profile
from zigpy.util import ListenableMixin, LocalLogMixin
import zigpy.zcl
from zigpy.zcl import foundation

if TYPE_CHECKING:
    from zigpy.application import ControllerApplication

LOGGER = logging.getLogger(__name__)


class Group(ListenableMixin, dict):
    def __init__(
        self,
        group_id: int,
        name: str | None = None,
        groups: Groups | None = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)

        self._groups: Groups = groups
        self._group_id: t.Group = t.Group(group_id)
        self._name: str = name
        self._endpoint: GroupEndpoint = GroupEndpoint(self)
        if groups is not None:
            self.add_listener(groups)

    def add_member(self, ep: Endpoint, suppress_event: bool = False) -> Group:
        if not isinstance(ep, Endpoint):
            raise ValueError(f"{ep} is not {Endpoint.__class__.__name__} class")
        if ep.unique_id in self:
            return self[ep.unique_id]
        self[ep.unique_id] = ep
        ep.member_of[self.group_id] = self
        if not suppress_event:
            self.listener_event("member_added", self, ep)
        return self

    def remove_member(self, ep: Endpoint, suppress_event: bool = False) -> Group:
        self.pop(ep.unique_id, None)
        ep.member_of.pop(self.group_id, None)
        if not suppress_event:
            self.listener_event("member_removed", self, ep)
        return self

    async def request(self, profile, cluster, sequence, data, *args, **kwargs):
        """Send multicast request."""
        await self.application.send_packet(
            t.ZigbeePacket(
                src_ep=self.application.get_endpoint_id(
                    cluster, is_server_cluster=False
                ),
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.Group, address=self.group_id
                ),
                tsn=sequence,
                profile_id=profile,
                cluster_id=cluster,
                data=t.SerializableBytes(data),
                radius=0,
                non_member_radius=3,
            )
        )

        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Default_Response
        ].schema(
            status=foundation.Status.SUCCESS,
            command_id=data[2],
        )

    def __repr__(self) -> str:
        return "<{} group_id={} name='{}' members={}>".format(
            self.__class__.__name__, self.group_id, self.name, super().__repr__()
        )

    @property
    def application(self) -> ControllerApplication:
        """Expose application to FakeEndpoint/GroupCluster."""
        return self.groups.application

    @property
    def groups(self) -> Groups:
        return self._groups

    @property
    def group_id(self) -> t.Group:
        return self._group_id

    @property
    def members(self) -> Group:
        return self

    @property
    def name(self) -> str:
        if self._name is None:
            return f"No name group {self.group_id}"
        return self._name

    @property
    def endpoint(self) -> GroupEndpoint:
        return self._endpoint


class Groups(ListenableMixin, dict):
    def __init__(self, app: ControllerApplication, *args: Any, **kwargs: Any):
        self._application: ControllerApplication = app
        self._listeners: dict = {}
        super().__init__(*args, **kwargs)

    def add_group(
        self, group_id: int, name: str | None = None, suppress_event: bool = False
    ) -> Group:
        if group_id in self:
            return self[group_id]
        LOGGER.debug("Adding group: %s, %s", group_id, name)
        group = Group(group_id, name, self)
        self[group_id] = group
        if not suppress_event:
            self.listener_event("group_added", group)
        return group

    def member_added(self, group: Group, ep: Endpoint) -> None:
        self.listener_event("group_member_added", group, ep)

    def member_removed(self, group: Group, ep: Endpoint) -> None:
        self.listener_event("group_member_removed", group, ep)

    def pop(self, item, *args: Any) -> Group | None:
        if isinstance(item, Group):
            group = super().pop(item.group_id, *args)
            if isinstance(group, Group):
                for member in (*group.values(),):
                    group.remove_member(member)
                self.listener_event("group_removed", group)
            return group
        group = super().pop(item, *args)
        if isinstance(group, Group):
            for member in (*group.values(),):
                group.remove_member(member)
        self.listener_event("group_removed", group)
        return group

    remove_group = pop

    def update_group_membership(self, ep: Endpoint, groups: set[int]) -> None:
        """Sync up device group membership."""
        old_groups = {
            group.group_id for group in self.values() if ep.unique_id in group.members
        }

        for grp_id in old_groups - groups:
            self[grp_id].remove_member(ep)

        for grp_id in groups - old_groups:
            group = self.add_group(grp_id)
            group.add_member(ep)

    @property
    def application(self) -> ControllerApplication:
        """Return application controller."""
        return self._application


class GroupCluster(zigpy.zcl.Cluster):
    """Virtual cluster for group requests."""

    @classmethod
    def from_id(
        cls, group_endpoint: GroupEndpoint, cluster_id: int, is_server=True
    ) -> zigpy.zcl.Cluster:
        """Instantiate from ZCL cluster by cluster id."""
        if is_server is not True:
            raise ValueError("Only server clusters are supported for group requests")
        if cluster_id in cls._registry:
            return cls._registry[cluster_id](group_endpoint, is_server=True)
        group_endpoint.debug(
            "0x%04x cluster id is not supported for group requests", cluster_id
        )
        raise KeyError(f"Unsupported 0x{cluster_id:04x} cluster id for groups")

    @classmethod
    def from_attr(
        cls, group_endpoint: GroupEndpoint, ep_name: str
    ) -> zigpy.zcl.Cluster:
        """Instantiate by Cluster name."""

        for cluster in cls._registry.values():
            if hasattr(cluster, "ep_attribute") and cluster.ep_attribute == ep_name:
                return cluster(group_endpoint, is_server=True)
        raise AttributeError(f"Unsupported {ep_name} group cluster")


class GroupEndpoint(LocalLogMixin):
    """Group request handlers.

    wrapper for virtual clusters.
    """

    def __init__(self, group: Group):
        """Instantiate GroupRequest."""
        self._group: Group = group
        self._clusters: dict = {}
        self._cluster_by_attr: dict = {}

    @property
    def endpoint_id(self) -> None:
        return None

    @property
    def clusters(self) -> dict:
        """Group clusters.

        most of the times, group requests are addressed from client -> server clusters.
        """
        return self._clusters

    @property
    def device(self) -> Group:
        """Group is our fake zigpy device"""
        return self._group

    def request(self, cluster, sequence, data, *args, **kwargs):
        """Send multicast request."""
        return self.device.request(zha_profile.PROFILE_ID, cluster, sequence, data)

    def reply(self, cluster, sequence, data, *args, **kwargs):
        """Send multicast reply.

        do we really need this one :shrug:
        """
        return self.request(cluster, sequence, data, *args, **kwargs)

    def log(self, lvl: int, msg: str, *args: Any, **kwargs: Any) -> None:
        msg = "[0x%04x] " + msg
        args = (self._group.group_id,) + args
        LOGGER.log(lvl, msg, *args, **kwargs)

    def __getitem__(self, item: int):
        """Return or instantiate a group cluster."""
        try:
            return self.clusters[item]
        except KeyError:
            self.debug("trying to create new group %s cluster id", item)

        cluster = GroupCluster.from_id(self, item)
        self.clusters[item] = cluster
        return cluster

    def __getattr__(self, name: str):
        """Return or instantiate a group cluster by cluster name."""
        try:
            return self._cluster_by_attr[name]
        except KeyError:
            self.debug("trying to create a new group '%s' cluster", name)

        cluster = GroupCluster.from_attr(self, name)
        self._cluster_by_attr[name] = cluster
        return cluster
