import abc
import asyncio
import logging
from typing import Any, Dict, Optional, Union

import zigpy.appdb
import zigpy.config
import zigpy.device
import zigpy.exceptions
import zigpy.group
import zigpy.ota
import zigpy.quirks
import zigpy.topology
import zigpy.types as t
import zigpy.util
import zigpy.zcl
import zigpy.zdo
import zigpy.zdo.types as zdo_types

DEFAULT_ENDPOINT_ID = 1
LOGGER = logging.getLogger(__name__)


class ControllerApplication(zigpy.util.ListenableMixin, abc.ABC):
    SCHEMA = zigpy.config.CONFIG_SCHEMA
    SCHEMA_DEVICE = zigpy.config.SCHEMA_DEVICE

    def __init__(self, config: Dict):
        self._send_sequence = 0
        self.devices: Dict[t.EUI64, zigpy.device.Device] = {}
        self.topology = None
        self._listeners = {}
        self._channel = None
        self._channels = None
        self._config = config
        self._dblistener = None
        self._ext_pan_id = None
        self._groups = zigpy.group.Groups(self)
        self._ieee = None
        self._listeners = {}
        self._nwk = None
        self._nwk_update_id = None
        self._ota = zigpy.ota.OTA(self)
        self._pan_id = None
        self._send_sequence = 0

    async def _load_db(self) -> None:
        """Restore save state."""
        database_file = self.config[zigpy.config.CONF_DATABASE]
        if not database_file:
            return

        self._dblistener = await zigpy.appdb.PersistingListener.new(database_file, self)
        self.add_listener(self._dblistener)
        self.groups.add_listener(self._dblistener)
        await self._dblistener.load()

    @classmethod
    async def new(
        cls, config: Dict, auto_form: bool = False, start_radio: bool = True
    ) -> "ControllerApplication":
        """Create new instance of application controller."""
        app = cls(config)
        await app._load_db()
        await app.ota.initialize()
        app.topology = zigpy.topology.Topology.new(app)
        if start_radio:
            try:
                await app.startup(auto_form)
            except Exception:
                LOGGER.error("Couldn't start application")
                await app.pre_shutdown()
                raise

        return app

    async def pre_shutdown(self) -> None:
        """Shutdown controller."""
        if self._dblistener:
            await self._dblistener.shutdown()
        await self.shutdown()

    @abc.abstractmethod
    async def shutdown(self):
        """Perform a complete application shutdown."""

    @abc.abstractmethod
    async def startup(self, auto_form=False):
        """Perform a complete application startup"""

    async def form_network(self):
        """Form a new network based on network configuration from config."""
        raise NotImplementedError

    def add_device(self, ieee, nwk):
        assert isinstance(ieee, t.EUI64)
        # TODO: Shut down existing device

        dev = zigpy.device.Device(self, ieee, nwk)
        self.devices[ieee] = dev
        return dev

    async def update_network(
        self,
        *,
        channel: Optional[t.uint8_t] = None,
        channels: Optional[t.Channels] = None,
        extended_pan_id: Optional[t.ExtendedPanId] = None,
        network_key: Optional[t.KeyData] = None,
        pan_id: Optional[t.PanId] = None,
        tc_link_key: Optional[t.KeyData] = None,
        update_id: int = 0,
    ):
        """Update network parameters.

        :param channel: Radio channel
        :param channels: Channels mask
        :param extended_pan_id: Extended pan id
        :param network_key: network key
        :param pan_id: Network pan id
        :param tc_link_key: Trust Center link key
        :param update_id: nwk_update_id parameter
        """
        raise NotImplementedError

    def device_initialized(self, device):
        """Used by a device to signal that it is initialized"""
        self.listener_event("raw_device_initialized", device)
        device = zigpy.quirks.get_device(device)
        self.devices[device.ieee] = device
        if self._dblistener is not None:
            device.add_context_listener(self._dblistener)
            device.neighbors.add_context_listener(self._dblistener)
        self.listener_event("device_initialized", device)

    async def remove(self, ieee: t.EUI64) -> None:
        """Try to remove a device from the network.

        :param ieee: address of the device to be removed
        """
        assert isinstance(ieee, t.EUI64)
        dev = self.devices.get(ieee)
        if not dev:
            LOGGER.debug("Device not found for removal: %s", ieee)
            return
        LOGGER.info("Removing device 0x%04x (%s)", dev.nwk, ieee)
        asyncio.create_task(self._remove_device(dev))
        if dev.node_desc.is_valid and dev.node_desc.is_end_device:
            parents = [
                parent
                for parent in self.devices.values()
                for nei in parent.neighbors
                if nei.device is dev
            ]
            for parent in parents:
                LOGGER.debug(
                    "Sending leave request for %s to %s parent", dev.ieee, parent.ieee
                )
                parent.zdo.create_catching_task(
                    parent.zdo.Mgmt_Leave_req(dev.ieee, 0x02)
                )

        self.listener_event("device_removed", dev)

    async def _remove_device(self, device: zigpy.device.Device) -> None:
        """Send a remove request then pop the device."""
        try:
            await asyncio.wait_for(
                device.zdo.leave(), timeout=30 if device.node_desc.is_end_device else 7
            )
        except (zigpy.exceptions.DeliveryError, asyncio.TimeoutError) as ex:
            LOGGER.debug("Sending 'zdo_leave_req' failed: %s", ex)

        self.devices.pop(device.ieee, None)

    async def force_remove(self, dev):
        raise NotImplementedError

    def deserialize(self, sender, endpoint_id, cluster_id, data):
        return sender.deserialize(endpoint_id, cluster_id, data)

    def handle_message(
        self,
        sender: zigpy.device.Device,
        profile: int,
        cluster: int,
        src_ep: int,
        dst_ep: int,
        message: bytes,
        *,
        dst_addressing: Optional[
            Union[t.Addressing.Group, t.Addressing.IEEE, t.Addressing.NWK]
        ] = None,
    ) -> None:
        self.listener_event(
            "handle_message", sender, profile, cluster, src_ep, dst_ep, message
        )
        if sender.status == zigpy.device.Status.NEW and dst_ep != 0:
            # only allow ZDO responses while initializing device
            LOGGER.debug(
                "Received frame on uninitialized device %s (%s) for endpoint: %s",
                sender.ieee,
                sender.status,
                dst_ep,
            )
            zigpy.quirks.handle_message_from_uninitialized_sender(
                sender, profile, cluster, src_ep, dst_ep, message
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
        return sender.handle_message(
            profile,
            cluster,
            src_ep,
            dst_ep,
            message,
            dst_addressing=dst_addressing,
        )

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
                dev.schedule_group_membership_scan()
            elif dev.initializing or dev.status == zigpy.device.Status.ENDPOINTS_INIT:
                LOGGER.debug("Skip initialization for existing device %s", ieee)
                dev.schedule_group_membership_scan()
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
        non_member_radius=3,
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

    @abc.abstractmethod
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

    @abc.abstractmethod
    async def permit_ncp(self, time_s=60):
        """Permit joining on NCP."""

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

    def update_config(self, partial_config: Dict[str, Any]) -> None:
        """Update existing config."""
        self.config = {**self.config, **partial_config}

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

    @config.setter
    def config(self, new_config) -> None:
        """Configuration setter."""
        self._config = self.SCHEMA(new_config)

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

    @classmethod
    @abc.abstractmethod
    async def probe(cls, device_config: Dict[str, Any]) -> bool:
        """API/Port probe method."""
