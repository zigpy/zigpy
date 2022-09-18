from __future__ import annotations

import asyncio
import enum
import logging
from typing import Any

import zigpy.exceptions
import zigpy.profiles
from zigpy.types.named import EUI64
from zigpy.typing import AddressingMode, DeviceType
import zigpy.util
import zigpy.zcl
from zigpy.zcl.clusters.general import Basic
from zigpy.zcl.foundation import Status as ZCLStatus, ZCLHeader
from zigpy.zdo.types import Status as zdo_status

LOGGER = logging.getLogger(__name__)


class Status(enum.IntEnum):
    """The status of an Endpoint"""

    # No initialization is done
    NEW = 0
    # Endpoint information (device type, clusters, etc) init done
    ZDO_INIT = 1
    # Endpoint Inactive
    ENDPOINT_INACTIVE = 3


class Endpoint(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):
    """An endpoint on a device on the network"""

    def __init__(self, device: DeviceType, endpoint_id: int):
        self._device: DeviceType = device
        self._endpoint_id: int = endpoint_id
        self._listeners: dict = {}

        self.status: Status = Status.NEW
        self.profile_id: int | None = None
        self.device_type: zigpy.profiles.zha.DeviceType | None = None
        self.in_clusters: dict = {}
        self.out_clusters: dict = {}
        self._cluster_attr: dict = {}

        self._member_of: dict = {}

        self._manufacturer: str | None = None
        self._model: str | None = None

    async def initialize(self) -> None:
        self.info("Discovering endpoint information")

        if self.profile_id is not None or self.status == Status.ENDPOINT_INACTIVE:
            self.info("Endpoint descriptor already queried")
        else:
            status, _, sd = await self._device.zdo.Simple_Desc_req(
                self._device.nwk, self._endpoint_id, tries=3, delay=2
            )

            if status == zdo_status.NOT_ACTIVE:
                # These endpoints are essentially junk but this lets the device join
                self.status = Status.ENDPOINT_INACTIVE
                return
            elif status != zdo_status.SUCCESS:
                raise zigpy.exceptions.InvalidResponse(
                    "Failed to retrieve service descriptor: %s", status
                )

            self.info("Discovered endpoint information: %s", sd)
            self.profile_id = sd.profile
            self.device_type = sd.device_type

            if self.profile_id == zigpy.profiles.zha.PROFILE_ID:
                self.device_type = zigpy.profiles.zha.DeviceType(self.device_type)
            elif self.profile_id == zigpy.profiles.zll.PROFILE_ID:
                self.device_type = zigpy.profiles.zll.DeviceType(self.device_type)

            for cluster in sd.input_clusters:
                self.add_input_cluster(cluster)

            for cluster in sd.output_clusters:
                self.add_output_cluster(cluster)

        self.status = Status.ZDO_INIT

    def add_input_cluster(
        self, cluster_id: int, cluster: zigpy.zcl.Cluster | None = None
    ) -> zigpy.zcl.Cluster:
        """Adds an endpoint's input cluster

        (a server cluster supported by the device)
        """
        if cluster is None:
            if cluster_id in self.in_clusters:
                return self.in_clusters[cluster_id]

            cluster = zigpy.zcl.Cluster.from_id(self, cluster_id, is_server=True)

        self.in_clusters[cluster_id] = cluster

        if hasattr(cluster, "ep_attribute"):
            self._cluster_attr[cluster.ep_attribute] = cluster

        if hasattr(self._device.application, "_dblistener"):
            listener = zigpy.zcl.ClusterPersistingListener(
                self._device.application._dblistener, cluster
            )
            cluster.add_listener(listener)

        return cluster

    def add_output_cluster(
        self, cluster_id: int, cluster: zigpy.zcl.Cluster | None = None
    ) -> zigpy.zcl.Cluster:
        """Adds an endpoint's output cluster

        (a client cluster supported by the device)
        """
        if cluster is None:
            if cluster_id in self.out_clusters:
                return self.out_clusters[cluster_id]

            cluster = zigpy.zcl.Cluster.from_id(self, cluster_id, is_server=False)

        self.out_clusters[cluster_id] = cluster
        return cluster

    async def add_to_group(self, grp_id: int, name: str | None = None) -> ZCLStatus:
        try:
            res = await self.groups.add(grp_id, name)
        except AttributeError:
            self.debug("Cannot add 0x%04x group, no groups cluster", grp_id)
            return ZCLStatus.FAILURE

        if res[0] not in (ZCLStatus.SUCCESS, ZCLStatus.DUPLICATE_EXISTS):
            self.debug("Couldn't add to 0x%04x group: %s", grp_id, res[0])
            return res[0]

        group = self.device.application.groups.add_group(grp_id, name)
        group.add_member(self)
        return res[0]

    async def remove_from_group(self, grp_id: int) -> ZCLStatus:
        try:
            res = await self.groups.remove(grp_id)
        except AttributeError:
            self.debug("Cannot remove 0x%04x group, no groups cluster", grp_id)
            return ZCLStatus.FAILURE

        if res[0] not in (ZCLStatus.SUCCESS, ZCLStatus.NOT_FOUND):
            self.debug("Couldn't remove to 0x%04x group: %s", grp_id, res[0])
            return res[0]

        if grp_id in self.device.application.groups:
            self.device.application.groups[grp_id].remove_member(self)
        return res[0]

    async def group_membership_scan(self) -> None:
        """Sync up group membership."""
        try:
            res = await self.groups.get_membership([])
        except AttributeError:
            return
        except (asyncio.TimeoutError, zigpy.exceptions.ZigbeeException):
            self.debug("Failed to sync-up group membership")
            return

        groups = {group for group in res[1]}
        self.device.application.groups.update_group_membership(self, groups)

    async def get_model_info(self) -> tuple[str | None, str | None]:
        if Basic.cluster_id not in self.in_clusters:
            return None, None

        # Some devices can't handle multiple attributes in the same read request
        for names in (["manufacturer", "model"], ["manufacturer"], ["model"]):
            try:
                success, failure = await self.basic.read_attributes(
                    names, allow_cache=True
                )
            except asyncio.TimeoutError:
                # Only swallow the `TimeoutError` on the double attribute read
                if len(names) == 2:
                    continue

                raise

            if "model" in success:
                self._model = success["model"]

            if "manufacturer" in success:
                self._manufacturer = success["manufacturer"]

        return self._model, self._manufacturer

    def deserialize(self, cluster_id, data):
        """Deserialize data for ZCL"""
        if cluster_id not in self.in_clusters and cluster_id not in self.out_clusters:
            raise KeyError(f"No cluster ID 0x{cluster_id:04x} on {self.unique_id}")

        cluster = self.in_clusters.get(cluster_id, self.out_clusters.get(cluster_id))
        return cluster.deserialize(data)

    def handle_message(
        self,
        profile: int,
        cluster: int,
        hdr: ZCLHeader,
        args: list,
        *,
        dst_addressing: AddressingMode | None = None,
    ) -> None:
        if cluster in self.in_clusters:
            handler = self.in_clusters[cluster].handle_message
        elif cluster in self.out_clusters:
            handler = self.out_clusters[cluster].handle_message
        else:
            self.debug("Message on unknown cluster 0x%04x", cluster)
            self.listener_event("unknown_cluster_message", hdr.command_id, args)
            return

        handler(hdr, args, dst_addressing=dst_addressing)

    async def request(
        self, cluster, sequence, data, expect_reply=True, command_id=0x00
    ):
        if self.profile_id == zigpy.profiles.zll.PROFILE_ID and not (
            cluster == zigpy.zcl.clusters.lightlink.LightLink.cluster_id
            and command_id < 0x40
        ):
            profile_id = zigpy.profiles.zha.PROFILE_ID
        else:
            profile_id = self.profile_id

        return await self.device.request(
            profile_id,
            cluster,
            self._endpoint_id,
            self._endpoint_id,
            sequence,
            data,
            expect_reply=expect_reply,
        )

    async def reply(self, cluster, sequence, data, command_id=0x00):
        if self.profile_id == zigpy.profiles.zll.PROFILE_ID and not (
            cluster == zigpy.zcl.clusters.lightlink.LightLink.cluster_id
            and command_id < 0x40
        ):
            profile_id = zigpy.profiles.zha.PROFILE_ID
        else:
            profile_id = self.profile_id

        return await self.device.reply(
            profile_id, cluster, self._endpoint_id, self._endpoint_id, sequence, data
        )

    def log(self, lvl: int, msg: str, *args: Any, **kwargs: Any) -> None:
        msg = "[0x%04x:%s] " + msg
        args = (self._device.nwk, self._endpoint_id) + args
        LOGGER.log(lvl, msg, *args, **kwargs)

    @property
    def device(self) -> DeviceType:
        return self._device

    @property
    def endpoint_id(self) -> int:
        return self._endpoint_id

    @property
    def manufacturer(self) -> str:
        if self._manufacturer is not None:
            return self._manufacturer
        return self.device.manufacturer

    @manufacturer.setter
    def manufacturer(self, value) -> None:
        self.warning(
            "Overriding manufacturer from quirks is not supported and "
            "will be removed in the next zigpy version"
        )
        self._manufacturer = value

    @property
    def manufacturer_id(self) -> int | None:
        """Return device's manufacturer id code."""
        return self.device.manufacturer_id

    @property
    def member_of(self) -> dict:
        return self._member_of

    @property
    def model(self) -> str:
        if self._model is not None:
            return self._model
        return self.device.model

    @model.setter
    def model(self, value) -> None:
        self.warning(
            "Overriding model from quirks is not supported and "
            "will be removed in the next version"
        )
        self._model = value

    @property
    def unique_id(self) -> tuple[EUI64, int]:
        return self.device.ieee, self.endpoint_id

    def __getattr__(self, name):
        try:
            return self._cluster_attr[name]
        except KeyError:
            raise AttributeError

    def __repr__(self) -> str:
        def cluster_repr(clusters):
            return ", ".join(
                [f"{c.ep_attribute}:0x{c.cluster_id:04X}" for c in clusters]
            )

        return (
            f"<{type(self).__name__}"
            f" id={self.endpoint_id}"
            f" in=[{cluster_repr(self.in_clusters.values())}]"
            f" out=[{cluster_repr(self.out_clusters.values())}]"
            f" status={self.status!r}"
            f">"
        )
