import asyncio
import logging
import os.path
from typing import Optional

import voluptuous as vol
import zigpy.appdb
import zigpy.device
import zigpy.group
import zigpy.quirks
import zigpy.ota
import zigpy.types as t
import zigpy.util
import zigpy.zcl
import zigpy.zdo
import zigpy.zdo.types as zdo_types

CONFIG_SCHEMA = vol.Schema({}, extra=vol.ALLOW_EXTRA)
DEFAULT_ENDPOINT_ID = 1
LOGGER = logging.getLogger(__name__)
OTA_DIR = "zigpy_ota/"


class ControllerApplication(zigpy.util.ListenableMixin):
    def __init__(self, database_file=None, config={}):
        self._send_sequence = 0
        self.devices = {}
        self._groups = zigpy.group.Groups(self)
        self._listeners = {}
        self._config = CONFIG_SCHEMA(config)
        self._channel = None
        self._channels = None
        self._ext_pan_id = None
        self._ieee = None
        self._nwk = None
        self._nwk_update_id = None
        self._pan_id = None

        self._ota = zigpy.ota.OTA(self)
        if database_file is None:
            ota_dir = None
        else:
            ota_dir = os.path.dirname(database_file)
            ota_dir = os.path.join(ota_dir, OTA_DIR)
        self.ota.initialize(ota_dir)

        self._dblistener = None
        if database_file is not None:
            self._dblistener = zigpy.appdb.PersistingListener(database_file, self)
            self.add_listener(self._dblistener)
            self.groups.add_listener(self._dblistener)
            self._dblistener.load()

    async def shutdown(self):
        """Perform a complete application shutdown."""
        pass

    async def startup(self, auto_form=False):
        """Perform a complete application startup"""
        raise NotImplementedError

    async def form_network(self, channel=15, pan_id=None, extended_pan_id=None):
        """Form a new network"""
        raise NotImplementedError

    def add_device(self, ieee, nwk):
        assert isinstance(ieee, t.EUI64)
        # TODO: Shut down existing device

        dev = zigpy.device.Device(self, ieee, nwk)
        self.devices[ieee] = dev
        return dev

    async def update_network(
        self,
        channel: Optional[t.uint8_t] = None,
        channels: Optional[t.uint32_t] = None,
        pan_id: Optional[t.PanId] = None,
        extended_pan_id: Optional[t.ExtendedPanId] = None,
        network_key: Optional[t.KeyData] = None,
    ):
        """Update network parameters.

        :param channel: Radio channel
        :param channels: Channels mask
        :param pan_id: Network pan id
        :param extended_pan_id: Extended pan id
        :param network_key: network key
        """
        raise NotImplementedError

    def device_initialized(self, device):
        """Used by a device to signal that it is initialized"""
        self.listener_event("raw_device_initialized", device)
        device = zigpy.quirks.get_device(device)
        self.devices[device.ieee] = device
        if self._dblistener is not None:
            device.add_context_listener(self._dblistener)
        self.listener_event("device_initialized", device)

    async def remove(self, ieee):
        assert isinstance(ieee, t.EUI64)
        dev = self.devices.get(ieee)
        if not dev:
            LOGGER.debug("Device not found for removal: %s", ieee)
            return
        LOGGER.info("Removing device 0x%04x (%s)", dev.nwk, ieee)
        zdo_worked = False
        try:
            resp = await dev.zdo.leave()
            zdo_worked = resp[0] == 0
        except (zigpy.exceptions.DeliveryError, asyncio.TimeoutError) as ex:
            LOGGER.debug("Sending 'zdo_leave_req' failed: %s", ex)

        if not zdo_worked:
            await self.force_remove(dev)
        self.devices.pop(ieee, None)

        self.listener_event("device_removed", dev)

    async def force_remove(self, dev):
        raise NotImplementedError

    def deserialize(self, sender, endpoint_id, cluster_id, data):
        return sender.deserialize(endpoint_id, cluster_id, data)

    def handle_message(self, sender, profile, cluster, src_ep, dst_ep, message):
        if sender.status == zigpy.device.Status.NEW and dst_ep != 0:
            # only allow ZDO responses while initializing device
            LOGGER.debug(
                "Received frame on uninitialized device %s (%s) for endpoint: %s",
                sender.ieee,
                sender.status,
                dst_ep,
            )
            return
        elif (
            sender.status == zigpy.device.Status.ZDO_INIT
            and dst_ep != 0
            and cluster != 0
        ):
            # only allow access to basic cluster while initializing endpoints
            LOGGER.debug(
                "Received frame on uninitialized device %s endpoint %s for cluster: %s",
                sender.ieee,
                dst_ep,
                cluster,
            )
            return
        return sender.handle_message(profile, cluster, src_ep, dst_ep, message)

    def handle_join(self, nwk, ieee, parent_nwk):
        ieee = t.EUI64(ieee)
        LOGGER.info("Device 0x%04x (%s) joined the network", nwk, ieee)
        if ieee in self.devices:
            dev = self.get_device(ieee)
            if dev.nwk != nwk:
                LOGGER.debug(
                    "Device %s changed id (0x%04x => 0x%04x)", ieee, dev.nwk, nwk
                )
                dev.nwk = nwk
            elif dev.initializing or dev.status == zigpy.device.Status.ENDPOINTS_INIT:
                LOGGER.debug("Skip initialization for existing device %s", ieee)
                return
        else:
            dev = self.add_device(ieee, nwk)

        self.listener_event("device_joined", dev)
        dev.schedule_initialize()

    def handle_leave(self, nwk, ieee):
        LOGGER.info("Device 0x%04x (%s) left the network", nwk, ieee)
        dev = self.devices.get(ieee, None)
        if dev is not None:
            self.listener_event("device_left", dev)

    async def mrequest(
        self,
        group_id,
        profile,
        cluster,
        src_ep,
        sequence,
        data,
        *,
        hops=0,
        non_member_radius=3
    ):
        """Submit and send data out as a multicast transmission.

        :param group_id: destination multicast address
        :param profile: Zigbee Profile ID to use for outgoing message
        :param cluster: cluster id where the message is being sent
        :param src_ep: source endpoint id
        :param sequence: transaction sequence number of the message
        :param data: Zigbee message payload
        :param hops: the message will be delivered to all nodes within this number of
                     hops of the sender. A value of zero is converted to MAX_HOPS
        :param non_member_radius: the number of hops that the message will be forwarded
                                  by devices that are not members of the group. A value
                                  of 7 or greater is treated as infinite
        :returns: return a tuple of a status and an error_message. Original requestor
                  has more context to provide a more meaningful error message
        """
        raise NotImplementedError

    @zigpy.util.retryable_request
    async def request(
        self,
        device,
        profile,
        cluster,
        src_ep,
        dst_ep,
        sequence,
        data,
        expect_reply=True,
        use_ieee=False,
    ):
        """Submit and send data out as an unicast transmission.

        :param device: destination device
        :param profile: Zigbee Profile ID to use for outgoing message
        :param cluster: cluster id where the message is being sent
        :param src_ep: source endpoint id
        :param dst_ep: destination endpoint id
        :param sequence: transaction sequence number of the message
        :param data: Zigbee message payload
        :param expect_reply: True if this is essentially a request
        :param use_ieee: use EUI64 for destination addressing
        :returns: return a tuple of a status and an error_message. Original requestor
                  has more context to provide a more meaningful error message
        """
        raise NotImplementedError

    async def broadcast(
        self,
        profile,
        cluster,
        src_ep,
        dst_ep,
        grpid,
        radius,
        sequence,
        data,
        broadcast_address,
    ):
        """Submit and send data out as an unicast transmission.

        :param profile: Zigbee Profile ID to use for outgoing message
        :param cluster: cluster id where the message is being sent
        :param src_ep: source endpoint id
        :param dst_ep: destination endpoint id
        :param: grpid: group id to address the broadcast to
        :param radius: max radius of the broadcast
        :param sequence: transaction sequence number of the message
        :param data: zigbee message payload
        :param timeout: how long to wait for transmission ACK
        :param broadcast_address: broadcast address.
        :returns: return a tuple of a status and an error_message. Original requestor
                  has more context to provide a more meaningful error message
        """
        raise NotImplementedError

    async def permit_ncp(self, time_s=60):
        """Permit joining on NCP."""
        raise NotImplementedError

    async def permit(self, time_s=60, node=None):
        """Permit joining on a specific node or all router nodes."""
        assert 0 <= time_s <= 254
        if node is not None:
            if not isinstance(node, t.EUI64):
                node = t.EUI64([t.uint8_t(p) for p in node])
            if node != self._ieee:
                try:
                    dev = self.get_device(ieee=node)
                    r = await dev.zdo.permit(time_s)
                    LOGGER.debug("Sent 'mgmt_permit_joining_req' to %s: %s", node, r)
                except KeyError:
                    LOGGER.warning("Device '%s' not found", node)
                except zigpy.exceptions.DeliveryError as ex:
                    LOGGER.warning("Couldn't open '%s' for joining: %s", node, ex)
            else:
                await self.permit_ncp(time_s)
            return

        await zigpy.zdo.broadcast(
            self,
            0x0036,
            0x0000,
            0x00,
            time_s,
            0,
            broadcast_address=t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
        )
        return await self.permit_ncp(time_s)

    def permit_with_key(self, node, code, time_s=60):
        raise NotImplementedError

    def get_sequence(self):
        self._send_sequence = (self._send_sequence + 1) % 256
        return self._send_sequence

    def get_device(self, ieee=None, nwk=None):
        if ieee is not None:
            return self.devices[ieee]

        for dev in self.devices.values():
            # TODO: Make this not terrible
            if dev.nwk == nwk:
                return dev

        raise KeyError

    def get_endpoint_id(self, cluster_id: int, is_server_cluster: bool = False):
        """Returns coordinator endpoint id for specified cluster id."""
        return DEFAULT_ENDPOINT_ID

    def get_dst_address(self, cluster):
        """Helper to get a dst address for bind/unbind operations.

        Allows radios to provide correct information especially for radios which listen
        on specific endpoints only.
        :param cluster: cluster instance to be bound to coordinator
        :returns: returns a "destination address"
        """
        dstaddr = zdo_types.MultiAddress()
        dstaddr.addrmode = 3
        dstaddr.ieee = self.ieee
        dstaddr.endpoint = self.get_endpoint_id(cluster.cluster_id, cluster.is_server)
        return dstaddr

    @property
    def channel(self):
        """Current radio channel."""
        return self._channel

    @property
    def channels(self):
        """Channel mask."""
        return self._channels

    @property
    def config(self) -> dict:
        """Return current configuration."""
        return self._config

    @property
    def extended_pan_id(self):
        """Extended PAN Id."""
        return self._ext_pan_id

    @property
    def groups(self):
        return self._groups

    @property
    def ieee(self):
        return self._ieee

    @property
    def nwk(self):
        return self._nwk

    @property
    def nwk_update_id(self):
        """NWK Update ID."""
        return self._nwk_update_id

    @property
    def ota(self):
        return self._ota

    @property
    def pan_id(self):
        """Network PAN Id."""
        return self._pan_id
