import enum
import logging
import zigpy.appdb
import zigpy.profiles
import zigpy.util
import zigpy.zcl

LOGGER = logging.getLogger(__name__)


class Status(enum.IntEnum):

    """The status of an Endpoint."""

    # No initialization is done
    NEW = 0
    # Endpoint information (device type, clusters, etc) init done
    ZDO_INIT = 1


class Endpoint(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):

    """An endpoint on a device on the network."""

    def __init__(self, device, endpoint_id):
        self._device = device
        self._endpoint_id = endpoint_id
        self.model = device.model
        self.manufacturer = device.manufacturer
        self.groups = list()
        self.in_clusters = dict()
        self.out_clusters = dict()
        self._cluster_attr = dict()
        self.status = Status.NEW
        self._listeners = dict()

    async def initialize(self):
        self.info('[0x%04x:%s] Start discovering endpoint information',
                  self._device.nwk, self._endpoint_id)
        if self.status == Status.ZDO_INIT:
            return

        self.info('[0x%04x:%s] Discovering endpoint information',
                  self._device.nwk, self._endpoint_id)
        try:
            sdr = await self._device.zdo.request(
                0x0004,
                self._device.nwk,
                self._endpoint_id,
                tries=3,
                delay=0.1,
            )
            if sdr[0] != 0:
                raise Exception('Failed to retrieve service descriptor: %s', sdr)
        except Exception as exc:
            self.info('Failed endpoint discovery during device initialization: %s', exc)
            return

        
        sd = sdr[2]
        self.profile_id = sd.profile
        self.device_type = sd.device_type
        try:
            if self.profile_id == 260:
                self.device_type = zigpy.profiles.zha.DeviceType(self.device_type)
            elif self.profile_id == 49246:
                self.device_type = zigpy.profiles.zll.DeviceType(self.device_type)
            else:
                self.warn('unhandled profle: %s',  self.profile_id)
        except ValueError:
            self.info('unknown device type')
        except AttributeError:
            self.info('undefined device type')
            self.device_type = "UNKNOWN"
        self.info('[0x%04x:%s] Discovered endpoint information: %s',
                  self._device.nwk, self._endpoint_id, sdr[2]
                  )
        for cluster in sd.input_clusters:
            self.add_input_cluster(cluster)
        for cluster in sd.output_clusters:
            self.add_output_cluster(cluster)

        self.status = Status.ZDO_INIT
        self.debug('[0x%04x:%s] Added endpoint information: %s',
                   self._device.nwk, self._endpoint_id, sdr[2])

    def add_input_cluster(self, cluster_id, cluster=None):
        """Adds an endpoint's input cluster.

        (a server cluster supported by the device)

        """
        if cluster_id in self.in_clusters and cluster is None:
            return self.in_clusters[cluster_id]

        if cluster is None:
            cluster = zigpy.zcl.Cluster.from_id(self, cluster_id)
        self.in_clusters[cluster_id] = cluster
        if hasattr(cluster, 'ep_attribute'):
            self._cluster_attr[cluster.ep_attribute] = cluster

        listener = zigpy.appdb.ClusterPersistingListener(
            self._device.application._dblistener,
            cluster,
        )
        cluster.add_listener(listener)

        return cluster

    def add_output_cluster(self, cluster_id, cluster=None):
        """Adds an endpoint's output cluster.

        (a client cluster supported by the device)

        """
        if cluster_id in self.out_clusters and cluster is None:
            return self.out_clusters[cluster_id]

        if cluster is None:
            cluster = zigpy.zcl.Cluster.from_id(self, cluster_id)
        self.out_clusters[cluster_id] = cluster
        return cluster

    def deserialize(self, cluster_id, data):
        """Deserialize data for ZCL."""
        frame_control, data = data[0], data[1:]
        frame_type = frame_control & 0b0011
        direction = (frame_control & 0b1000) >> 3
        is_reply = bool(direction) # reply =server2client
        if frame_control & 0b0100:
            # Manufacturer specific value present
            data = data[2:]
        tsn, command_id, data = data[0], data[1], data[2:]

        if cluster_id not in self.in_clusters and cluster_id not in self.out_clusters:
            LOGGER.debug('Ignoring unknown cluster ID 0x%04x',
                         cluster_id)
            return tsn, command_id + 256, is_reply, data

#        cluster = self.in_clusters.get(cluster_id, self.out_clusters.get(cluster_id, None))
        cluster = self.in_clusters.get(cluster_id, None) if is_reply else self.out_clusters.get(cluster_id, None)
        return cluster.deserialize(tsn, frame_type, is_reply, command_id, data)

    def handle_message(self, is_reply, profile, cluster, tsn, command_id,
        args, **kwargs):
        handler = None
        # is_reply is direction bit, set -> server2client else client2server
        if cluster in self.in_clusters and is_reply:
            handler = self.in_clusters[cluster].handle_message
        elif cluster in self.out_clusters and not is_reply:
            handler = self.out_clusters[cluster].handle_message
        elif command_id == 10 and cluster in self.in_clusters:
            handler = self.in_clusters[cluster].handle_message
        else:
            self.info('[0x%04x:%s] Message on unknown %s cluster 0x%04x: %s-%s-%s',
            self._device.nwk, self._endpoint_id, 
            "Server2Client" if is_reply else "Client2Server", 
            cluster, command_id,  args, kwargs
            )
            self.listener_event('unknown_cluster_message', is_reply,
                                command_id, args)
            return

        handler(is_reply, tsn, command_id, args, **kwargs)

    def request(self, cluster, sequence, data, expect_reply=True,  command_id=None):
        if (self.profile_id == zigpy.profiles.zll.PROFILE_ID and
            not (cluster == zigpy.zcl.clusters.lightlink.LightLink.cluster_id and
                     command_id <= 0x3f)):
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
