import enum
import logging

import zigpy.profiles
import zigpy.util
import zigpy.zcl
from zigpy.zcl.clusters.general import Basic, Groups
from zigpy.zcl.foundation import Status as ZCLStatus

LOGGER = logging.getLogger(__name__)


class Status(enum.IntEnum):
    """The status of an Endpoint"""
    # No initialization is done
    NEW = 0
    # Endpoint information (device type, clusters, etc) init done
    ZDO_INIT = 1


class Endpoint(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):
    """An endpoint on a device on the network"""
    def __init__(self, device, endpoint_id):
        self._device = device
        self._endpoint_id = endpoint_id
        self.device_type = None
        self.in_clusters = {}
        self.out_clusters = {}
        self._cluster_attr = {}
        self.status = Status.NEW
        self._listeners = {}
        self._member_of = {}
        self.profile_id = None
        self.manufacturer = None
        self.model = None

    async def initialize(self):
        if self.status == Status.ZDO_INIT:
            return

        self.info("Discovering endpoint information")
        try:
            sdr = await self._device.zdo.Simple_Desc_req(
                self._device.nwk,
                self._endpoint_id,
                tries=3,
                delay=2,
            )
            if sdr[0] != 0:
                raise Exception("Failed to retrieve service descriptor: %s", sdr)
        except Exception as exc:
            self.warn("Failed ZDO request during endpoint initialization: %s", exc)
            return

        self.info("Discovered endpoint information: %s", sdr[2])
        sd = sdr[2]
        self.profile_id = sd.profile
        self.device_type = sd.device_type
        try:
            if self.profile_id == 260:
                self.device_type = zigpy.profiles.zha.DeviceType(self.device_type)
            elif self.profile_id == 49246:
                self.device_type = zigpy.profiles.zll.DeviceType(self.device_type)
        except ValueError:
            pass

        for cluster in sd.input_clusters:
            self.add_input_cluster(cluster)
        for cluster in sd.output_clusters:
            self.add_output_cluster(cluster)

        if Basic.cluster_id in self.in_clusters:
            await self.initialize_endpoint_info()

        self.status = Status.ZDO_INIT

    def add_input_cluster(self, cluster_id, cluster=None):
        """Adds an endpoint's input cluster

        (a server cluster supported by the device)
        """
        if cluster_id in self.in_clusters and cluster is None:
            return self.in_clusters[cluster_id]

        if cluster is None:
            cluster = zigpy.zcl.Cluster.from_id(self, cluster_id)
        self.in_clusters[cluster_id] = cluster
        if hasattr(cluster, 'ep_attribute'):
            self._cluster_attr[cluster.ep_attribute] = cluster

        if hasattr(self._device.application, '_dblistener'):
            listener = zigpy.zcl.ClusterPersistingListener(
                self._device.application._dblistener,
                cluster,
            )
            cluster.add_listener(listener)

        return cluster

    def add_output_cluster(self, cluster_id, cluster=None):
        """Adds an endpoint's output cluster

        (a client cluster supported by the device)
        """
        if cluster_id in self.out_clusters and cluster is None:
            return self.out_clusters[cluster_id]

        if cluster is None:
            cluster = zigpy.zcl.Cluster.from_id(self, cluster_id)
        self.out_clusters[cluster_id] = cluster
        return cluster

    async def add_to_group(self, grp_id: int, name: str = None):
        if Groups.cluster_id not in self.in_clusters:
            self.debug("Cannot add 0x%04x group, no groups cluster", grp_id)
            return ZCLStatus.FAILURE
        res = await self.groups.add(grp_id, name)
        if res[0] != ZCLStatus.SUCCESS:
            self.debug("Couldn't add to 0x%04x group: %s", grp_id, res[0])
            return res[0]

        group = self.device.application.groups.add_group(grp_id, name)
        group.add_member(self)
        return res[0]

    async def remove_from_group(self, grp_id: int):
        if Groups.cluster_id not in self.in_clusters:
            self.debug("Cannot remove 0x%04x group, no groups cluster", grp_id)
            return ZCLStatus.FAILURE
        res = await self.groups.remove(grp_id)
        if res[0] != ZCLStatus.SUCCESS:
            self.debug("Couldn't add to 0x%04x group: %s", grp_id, res[0])
            return res[0]

        if grp_id in self.device.application.groups:
            self.device.application.groups[grp_id].remove_member(self)
        return res[0]

    async def initialize_endpoint_info(self):
        attributes = {
            'manufacturer': None,
            'model': None,
        }

        async def read(attribute_names):
            """Read attributes and update extra_info convenience function."""
            result, _ = await self.in_clusters[0].read_attributes(
                attribute_names,
                allow_cache=True,
            )
            attributes.update(result)

        await read(['manufacturer', 'model'])

        if attributes['manufacturer'] is None or attributes['model'] is None:
            # Some devices fail at returning multiple results. Attempt separately.
            await read(['manufacturer'])
            await read(['model'])

        for key, value in attributes.items():
            if isinstance(value, bytes):
                try:
                    value = value.split(b'\x00')[0]
                    attributes[key] = value.decode('ascii').strip()
                except UnicodeDecodeError:
                    # Unsure what the best behaviour here is. Unset the key?
                    pass

        self.manufacturer = attributes['manufacturer']
        self.model = attributes['model']

        self.debug("Manufacturer: %s", self.manufacturer)
        self.debug("Model: %s", self.model)

    def deserialize(self, cluster_id, data):
        """Deserialize data for ZCL"""
        frame_control, data = data[0], data[1:]
        frame_type = frame_control & 0b0011
        direction = (frame_control & 0b1000) >> 3
        is_reply = bool(direction)
        if frame_control & 0b0100:
            # Manufacturer specific value present
            data = data[2:]
        tsn, command_id, data = data[0], data[1], data[2:]

        if cluster_id not in self.in_clusters and cluster_id not in self.out_clusters:
            LOGGER.debug("Ignoring unknown cluster ID 0x%04x",
                         cluster_id)
            return tsn, command_id + 256, is_reply, data

        cluster = self.in_clusters.get(cluster_id, self.out_clusters.get(cluster_id, None))
        return cluster.deserialize(tsn, frame_type, is_reply, command_id, data)

    def handle_message(self, is_reply, profile, cluster, tsn, command_id, args):
        handler = None
        if cluster in self.in_clusters:
            handler = self.in_clusters[cluster].handle_message
        elif cluster in self.out_clusters:
            handler = self.out_clusters[cluster].handle_message
        else:
            self.debug("Message on unknown cluster 0x%04x", cluster)
            self.listener_event("unknown_cluster_message", is_reply,
                                command_id, args)
            return

        handler(is_reply, tsn, command_id, args)

    def request(self, cluster, sequence, data, expect_reply=True, command_id=0x00):
        if (self.profile_id == zigpy.profiles.zll.PROFILE_ID and not (
                cluster == zigpy.zcl.clusters.lightlink.LightLink.cluster_id and command_id < 0x40)):
            profile_id = zigpy.profiles.zha.PROFILE_ID
        else:
            profile_id = self.profile_id

        return self.device.request(
            profile_id,
            cluster,
            self._endpoint_id,
            self._endpoint_id,
            sequence,
            data,
            expect_reply=expect_reply
        )

    def reply(self, cluster, sequence, data):
        return self.device.reply(
            self.profile_id,
            cluster,
            self._endpoint_id,
            self._endpoint_id,
            sequence,
            data,
        )

    def log(self, lvl, msg, *args):
        msg = '[0x%04x:%s] ' + msg
        args = (self._device.nwk, self._endpoint_id) + args
        return LOGGER.log(lvl, msg, *args)

    @property
    def device(self):
        return self._device

    @property
    def endpoint_id(self):
        return self._endpoint_id

    @property
    def member_of(self):
        return self._member_of

    @property
    def unique_id(self):
        return self.device.ieee, self.endpoint_id

    def __getattr__(self, name):
        try:
            return self._cluster_attr[name]
        except KeyError:
            raise AttributeError
