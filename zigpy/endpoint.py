import enum
import logging

import zigpy.appdb
import zigpy.profiles
import zigpy.util
import zigpy.zcl

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
        self.in_clusters = {}
        self.out_clusters = {}
        self._cluster_attr = {}
        self.status = Status.NEW
        self._listeners = {}

    async def initialize(self):
        if self.status == Status.ZDO_INIT:
            return

        self.info("Discovering endpoint information")
        try:
            sdr = await self._device.zdo.request(
                0x0004,
                self._device.nwk,
                self._endpoint_id,
                tries=3,
                delay=2,
            )
            if sdr[0] != 0:
                raise Exception("Failed to retrieve service descriptor: %s", sdr)
        except Exception as exc:
            self.warn("Failed ZDO request during device initialization: %s", exc)
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
            listener = zigpy.appdb.ClusterPersistingListener(
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
            self.warn("Message on unknown cluster 0x%04x", cluster)
            self.listener_event("unknown_cluster_message", is_reply,
                                command_id, args)
            return

        handler(is_reply, tsn, command_id, args)

    def request(self, cluster, sequence, data, expect_reply=True):
        if (self.profile_id == zigpy.profiles.zll.PROFILE_ID and
                cluster != zigpy.zcl.clusters.lightlink.LightLink.cluster_id):
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

    def __getattr__(self, name):
        try:
            return self._cluster_attr[name]
        except KeyError:
            raise AttributeError
