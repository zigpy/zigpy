from __future__ import annotations

import abc
import asyncio
import contextlib
import logging
import os
import random
import time
from typing import Any

import zigpy.appdb
import zigpy.backups
import zigpy.config as conf
import zigpy.device
import zigpy.exceptions
import zigpy.group
import zigpy.ota
import zigpy.profiles
import zigpy.quirks
import zigpy.state
import zigpy.topology
import zigpy.types as t
import zigpy.util
import zigpy.zcl
import zigpy.zdo
import zigpy.zdo.types as zdo_types

DEFAULT_ENDPOINT_ID = 1
LOGGER = logging.getLogger(__name__)


class ControllerApplication(zigpy.util.ListenableMixin, abc.ABC):
    SCHEMA = conf.CONFIG_SCHEMA
    SCHEMA_DEVICE = conf.SCHEMA_DEVICE

    def __init__(self, config: dict):
        self.devices: dict[t.EUI64, zigpy.device.Device] = {}
        self.state: zigpy.state.State = zigpy.state.State()
        self._listeners = {}
        self._config = self.SCHEMA(config)
        self._dblistener = None
        self._groups = zigpy.group.Groups(self)
        self._listeners = {}
        self._ota = zigpy.ota.OTA(self)
        self._send_sequence = 0

        self._concurrent_requests_semaphore = zigpy.util.DynamicBoundedSemaphore(
            self._config[conf.CONF_MAX_CONCURRENT_REQUESTS]
        )

        self.backups: zigpy.backups.BackupManager = zigpy.backups.BackupManager(self)
        self.topology: zigpy.topology.Topology = zigpy.topology.Topology(self)

    async def _load_db(self) -> None:
        """Restore save state."""
        database_file = self.config[conf.CONF_DATABASE]
        if not database_file:
            return

        self._dblistener = await zigpy.appdb.PersistingListener.new(database_file, self)
        self.add_listener(self._dblistener)
        self.groups.add_listener(self._dblistener)
        self.backups.add_listener(self._dblistener)
        self.topology.add_listener(self._dblistener)
        await self._dblistener.load()

    async def initialize(self, *, auto_form: bool = False):
        """
        Starts the network on a connected radio, optionally forming one with random
        settings if necessary.
        """

        last_backup = self.backups.most_recent_backup()

        try:
            await self.load_network_info(load_devices=False)
        except zigpy.exceptions.NetworkNotFormed:
            LOGGER.info("Network is not formed")

            if not auto_form:
                raise

            if last_backup is None:
                # Form a new network if we have no backup
                await self.form_network()
            else:
                # Otherwise, restore the most recent backup
                LOGGER.info("Restoring the most recent network backup")
                await self.backups.restore_backup(last_backup)

        LOGGER.debug("Network info: %s", self.state.network_info)
        LOGGER.debug("Node info: %s", self.state.node_info)

        new_state = self.backups.from_network_state()

        if (
            self.config[conf.CONF_NWK_VALIDATE_SETTINGS]
            and last_backup is not None
            and not new_state.is_compatible_with(last_backup)
        ):
            raise zigpy.exceptions.NetworkSettingsInconsistent(
                f"Radio network settings are not compatible with most recent backup!\n"
                f"Current settings: {new_state!r}\n"
                f"Last backup: {last_backup!r}"
            )

        await self.start_network()

        # Some radios erroneously permit joins on startup
        await self.permit(0)

        if self.config[conf.CONF_NWK_BACKUP_ENABLED]:
            self.backups.start_periodic_backups(
                # Config specifies the period in minutes, not seconds
                period=(60 * self.config[conf.CONF_NWK_BACKUP_PERIOD])
            )

        if self.config[conf.CONF_TOPO_SCAN_ENABLED]:
            # Config specifies the period in minutes, not seconds
            self.topology.start_periodic_scans(
                period=(60 * self.config[zigpy.config.CONF_TOPO_SCAN_PERIOD])
            )

    async def startup(self, *, auto_form: bool = False):
        """
        Starts a network, optionally forming one with random settings if necessary.
        """

        try:
            await self.connect()
            await self.initialize(auto_form=auto_form)
        except Exception as e:
            LOGGER.error("Couldn't start application", exc_info=e)
            await self.shutdown()
            raise

    @classmethod
    async def new(
        cls, config: dict, auto_form: bool = False, start_radio: bool = True
    ) -> ControllerApplication:
        """Create new instance of application controller."""
        app = cls(config)

        await app._load_db()
        await app.ota.initialize()

        if not start_radio:
            return app

        await app.startup(auto_form=auto_form)

        for device in app.devices.values():
            if not device.is_initialized:
                LOGGER.warning("Device is partially initialized: %s", device)

        return app

    async def form_network(self):
        """
        Writes random network settings to the coordinator.
        """

        # First, make the settings consistent and randomly generate missing values
        channel = self.config[conf.CONF_NWK][conf.CONF_NWK_CHANNEL]
        channels = self.config[conf.CONF_NWK][conf.CONF_NWK_CHANNELS]
        pan_id = self.config[conf.CONF_NWK][conf.CONF_NWK_PAN_ID]
        extended_pan_id = self.config[conf.CONF_NWK][conf.CONF_NWK_EXTENDED_PAN_ID]
        network_key = self.config[conf.CONF_NWK][conf.CONF_NWK_KEY]
        tc_address = self.config[conf.CONF_NWK][conf.CONF_NWK_TC_ADDRESS]

        if pan_id is None:
            pan_id = random.SystemRandom().randint(0x0001, 0xFFFE + 1)

        if extended_pan_id is None:
            # TODO: exclude `FF:FF:FF:FF:FF:FF:FF:FF` and possibly more reserved EPIDs
            extended_pan_id = t.ExtendedPanId(os.urandom(8))

        if network_key is None:
            network_key = t.KeyData(os.urandom(16))

        if tc_address is None:
            tc_address = t.EUI64.UNKNOWN

        # Override `channels` with a single channel if one is explicitly set
        if channel is not None:
            channels = t.Channels.from_channel_list([channel])

        network_info = zigpy.state.NetworkInfo(
            extended_pan_id=extended_pan_id,
            pan_id=pan_id,
            nwk_update_id=self.config[conf.CONF_NWK][conf.CONF_NWK_UPDATE_ID],
            nwk_manager_id=0x0000,
            channel=channel,
            channel_mask=channels,
            security_level=5,
            network_key=zigpy.state.Key(
                key=network_key,
                tx_counter=0,
                rx_counter=0,
                seq=self.config[conf.CONF_NWK][conf.CONF_NWK_KEY_SEQ],
            ),
            tc_link_key=zigpy.state.Key(
                key=self.config[conf.CONF_NWK][conf.CONF_NWK_TC_LINK_KEY],
                tx_counter=0,
                rx_counter=0,
                seq=0,
                partner_ieee=tc_address,
            ),
            children=[],
            key_table=[],
            nwk_addresses={},
            stack_specific={},
        )

        node_info = zigpy.state.NodeInfo(
            nwk=0x0000,
            ieee=t.EUI64.UNKNOWN,  # Use the device IEEE address
            logical_type=zdo_types.LogicalType.Coordinator,
        )

        LOGGER.debug("Forming a new network")

        await self.backups.restore_backup(
            backup=zigpy.backups.NetworkBackup(
                network_info=network_info,
                node_info=node_info,
            ),
            counter_increment=0,
            allow_incomplete=True,
        )

    async def shutdown(self) -> None:
        """Shutdown controller."""
        self.backups.stop_periodic_backups()
        self.topology.stop_periodic_scans()

        if self._dblistener:
            await self._dblistener.shutdown()

        await self.disconnect()

    def add_device(self, ieee: t.EUI64, nwk: t.NWK):
        """
        Creates a zigpy `Device` object with the provided IEEE and NWK addresses.
        """

        assert isinstance(ieee, t.EUI64)
        # TODO: Shut down existing device

        dev = zigpy.device.Device(self, ieee, nwk)
        self.devices[ieee] = dev
        return dev

    def device_initialized(self, device):
        """Used by a device to signal that it is initialized"""
        LOGGER.debug("Device is initialized %s", device)

        self.listener_event("raw_device_initialized", device)
        device = zigpy.quirks.get_device(device)
        self.devices[device.ieee] = device
        if self._dblistener is not None:
            device.add_context_listener(self._dblistener)
        self.listener_event("device_initialized", device)

    async def remove(
        self, ieee: t.EUI64, remove_children: bool = True, rejoin: bool = False
    ) -> None:
        """Try to remove a device from the network.

        :param ieee: address of the device to be removed
        """
        assert isinstance(ieee, t.EUI64)
        dev = self.devices.get(ieee)
        if not dev:
            LOGGER.debug("Device not found for removal: %s", ieee)
            return

        dev.cancel_initialization()

        LOGGER.info("Removing device 0x%04x (%s)", dev.nwk, ieee)
        asyncio.create_task(
            self._remove_device(dev, remove_children=remove_children, rejoin=rejoin)
        )
        if dev.node_desc is not None and dev.node_desc.is_end_device:
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
                opts = parent.zdo.LeaveOptions.RemoveChildren
                if rejoin:
                    opts |= parent.zdo.LeaveOptions.Rejoin
                parent.zdo.create_catching_task(
                    parent.zdo.Mgmt_Leave_req(dev.ieee, opts)
                )

        self.listener_event("device_removed", dev)

    async def _remove_device(
        self,
        device: zigpy.device.Device,
        remove_children: bool = True,
        rejoin: bool = False,
    ) -> None:
        """Send a remove request then pop the device."""
        try:
            await asyncio.wait_for(
                device.zdo.leave(remove_children=remove_children, rejoin=rejoin),
                timeout=30
                if device.node_desc is not None and device.node_desc.is_end_device
                else 7,
            )
        except (zigpy.exceptions.DeliveryError, asyncio.TimeoutError) as ex:
            LOGGER.debug("Sending 'zdo_leave_req' failed: %s", ex)

        self.devices.pop(device.ieee, None)

    def deserialize(
        self,
        sender: zigpy.device.Device,
        endpoint_id: t.uint8_t,
        cluster_id: t.uint16_t,
        data: bytes,
    ) -> tuple[Any, bytes]:
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
        dst_addressing: None
        | (t.Addressing.Group | t.Addressing.IEEE | t.Addressing.NWK) = None,
    ) -> None:
        """
        Called when the radio library receives a packet.

        Deprecated, will be removed.
        """
        self.listener_event(
            "handle_message", sender, profile, cluster, src_ep, dst_ep, message
        )

        if sender.is_initialized:
            return sender.handle_message(
                profile,
                cluster,
                src_ep,
                dst_ep,
                message,
                dst_addressing=dst_addressing,
            )

        LOGGER.debug(
            "Received frame on uninitialized device %s"
            " from ep %s to ep %s, cluster %s: %r",
            sender,
            src_ep,
            dst_ep,
            cluster,
            message,
        )

        if (
            dst_ep == 0
            or sender.all_endpoints_init
            or (
                sender.has_non_zdo_endpoints
                and cluster == zigpy.zcl.clusters.general.Basic.cluster_id
            )
        ):
            # Allow the following responses:
            #  - any ZDO
            #  - ZCL if endpoints are initialized
            #  - ZCL from Basic cluster if endpoints are initializing

            if not sender.initializing:
                sender.schedule_initialize()

            return sender.handle_message(
                profile,
                cluster,
                src_ep,
                dst_ep,
                message,
                dst_addressing=dst_addressing,
            )

        # Give quirks a chance to fast-initialize the device (at the moment only Xiaomi)
        zigpy.quirks.handle_message_from_uninitialized_sender(
            sender, profile, cluster, src_ep, dst_ep, message
        )

        # Reload the sender device object, in it was replaced by the quirk
        sender = self.get_device(ieee=sender.ieee)

        # If the quirk did not fast-initialize the device, start initialization
        if not sender.initializing and not sender.is_initialized:
            sender.schedule_initialize()

    def handle_join(self, nwk: t.NWK, ieee: t.EUI64, parent_nwk: t.NWK) -> None:
        """
        Called when a device joins or announces itself on the network.
        """

        ieee = t.EUI64(ieee)

        try:
            dev = self.get_device(ieee=ieee)
            LOGGER.info("Device 0x%04x (%s) joined the network", nwk, ieee)
            new_join = False
        except KeyError:
            dev = self.add_device(ieee, nwk)
            LOGGER.info("New device 0x%04x (%s) joined the network", nwk, ieee)
            new_join = True

        if dev.nwk != nwk:
            LOGGER.debug("Device %s changed id (0x%04x => 0x%04x)", ieee, dev.nwk, nwk)
            dev.nwk = nwk
            new_join = True

        # Not all stacks send a ZDO command when a device joins so the last_seen should
        # be updated
        dev.update_last_seen()

        if new_join:
            self.listener_event("device_joined", dev)
            dev.schedule_initialize()
        elif not dev.is_initialized:
            # Re-initialize partially-initialized devices but don't emit "device_joined"
            dev.schedule_initialize()
        else:
            # Rescan groups for devices that are not newly joining and initialized
            dev.schedule_group_membership_scan()

    def handle_leave(self, nwk: t.NWK, ieee: t.EUI64):
        """
        Called when a device has left the network.
        """
        LOGGER.info("Device 0x%04x (%s) left the network", nwk, ieee)

        try:
            dev = self.get_device(ieee=ieee)
        except KeyError:
            return
        else:
            self.listener_event("device_left", dev)

    def handle_relays(self, nwk: t.NWK, relays: list[t.NWK]) -> None:
        """
        Called when a list of relaying devices is received.
        """
        try:
            device = self.get_device(nwk=nwk)
        except KeyError:
            LOGGER.warning("Received relays from an unknown device: %s", nwk)
            asyncio.create_task(self._discover_unknown_device(nwk))
        else:
            # `relays` is a property with a setter that emits an event
            device.relays = relays

    @classmethod
    async def probe(cls, device_config: dict[str, Any]) -> bool | dict[str, Any]:
        """
        Probes the device specified by `device_config` and returns valid device settings
        if the radio supports the device. If the device is not supported, `False` is
        returned.
        """

        config = cls.SCHEMA({conf.CONF_DEVICE: cls.SCHEMA_DEVICE(device_config)})
        app = cls(config)

        try:
            await app.connect()
        except Exception:
            LOGGER.debug("Failed to probe with config %s", device_config, exc_info=True)
            return False
        else:
            return device_config
        finally:
            await app.disconnect()

    @abc.abstractmethod
    async def connect(self):
        """
        Connect to the radio hardware and verify that it is compatible with the library.
        This method should be stateless if the connection attempt fails.
        """
        raise NotImplementedError()  # pragma: no cover

    @abc.abstractmethod
    async def disconnect(self):
        """
        Disconnects from the radio hardware and shuts down the network.
        """
        raise NotImplementedError()  # pragma: no cover

    @abc.abstractmethod
    async def start_network(self):
        """
        Starts a Zigbee network with settings currently stored in the radio hardware.
        """
        raise NotImplementedError()  # pragma: no cover

    @abc.abstractmethod
    async def force_remove(self, dev: zigpy.device.Device):
        """
        Instructs the radio to remove a device with a lower-level leave command. Not all
        radios implement this.
        """
        raise NotImplementedError()  # pragma: no cover

    @abc.abstractmethod
    async def add_endpoint(self, descriptor: zdo_types.SimpleDescriptor):
        """
        Registers a new endpoint on the controlled device. Not all radios will implement
        this.
        """
        raise NotImplementedError()  # pragma: no cover

    async def register_endpoints(self):
        """
        Registers all necessary endpoints.
        The exact order in which this method is called depends on the radio module.
        """

        await self.add_endpoint(
            zdo_types.SimpleDescriptor(
                endpoint=1,
                profile=zigpy.profiles.zha.PROFILE_ID,
                device_type=zigpy.profiles.zha.DeviceType.IAS_CONTROL,
                device_version=0b0000,
                input_clusters=[
                    zigpy.zcl.clusters.general.Basic.cluster_id,
                    zigpy.zcl.clusters.general.OnOff.cluster_id,
                    zigpy.zcl.clusters.general.Time.cluster_id,
                    zigpy.zcl.clusters.general.Ota.cluster_id,
                    zigpy.zcl.clusters.security.IasAce.cluster_id,
                ],
                output_clusters=[
                    zigpy.zcl.clusters.general.PowerConfiguration.cluster_id,
                    zigpy.zcl.clusters.general.PollControl.cluster_id,
                    zigpy.zcl.clusters.security.IasZone.cluster_id,
                    zigpy.zcl.clusters.security.IasWd.cluster_id,
                ],
            )
        )

        await self.add_endpoint(
            zdo_types.SimpleDescriptor(
                endpoint=2,
                profile=zigpy.profiles.zll.PROFILE_ID,
                device_type=zigpy.profiles.zll.DeviceType.CONTROLLER,
                device_version=0b0000,
                input_clusters=[zigpy.zcl.clusters.general.Basic.cluster_id],
                output_clusters=[],
            )
        )

        for endpoint in self.config[conf.CONF_ADDITIONAL_ENDPOINTS]:
            await self.add_endpoint(endpoint)

    @contextlib.asynccontextmanager
    async def _limit_concurrency(self):
        """
        Async context manager to limit global coordinator request concurrency.
        """

        start_time = time.monotonic()
        was_locked = self._concurrent_requests_semaphore.locked()

        if was_locked:
            LOGGER.debug(
                "Max concurrency (%s) reached, delaying request (%s enqueued)",
                self._concurrent_requests_semaphore.max_value,
                self._concurrent_requests_semaphore.num_waiting,
            )

        async with self._concurrent_requests_semaphore:
            if was_locked:
                LOGGER.debug(
                    "Previously delayed request is now running, delayed by %0.2fs",
                    time.monotonic() - start_time,
                )

            yield

    @abc.abstractmethod
    async def send_packet(self, packet: t.ZigbeePacket) -> None:
        """
        Send a Zigbee packet using the appropriate addressing mode and provided options.
        """

        raise NotImplementedError()  # pragma: no cover

    def build_source_route_to(self, dest: zigpy.device.Device) -> list[t.NWK] | None:
        """
        Compute a source route to the destination device.
        """

        if dest.relays is None:
            return None

        # TODO: utilize topology scanner information
        return dest.relays[::-1]

    @zigpy.util.retryable_request
    async def request(
        self,
        device: zigpy.device.Device,
        profile: t.uint16_t,
        cluster: t.uint16_t,
        src_ep: t.uint8_t,
        dst_ep: t.uint8_t,
        sequence: t.uint8_t,
        data: bytes,
        *,
        expect_reply: bool = True,
        use_ieee: bool = False,
        extended_timeout: bool = False,
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
        :param extended_timeout: instruct the radio to use slower APS retries
        """

        if use_ieee:
            src = t.AddrModeAddress(
                addr_mode=t.AddrMode.IEEE, address=self.state.node_info.ieee
            )
            dst = t.AddrModeAddress(addr_mode=t.AddrMode.IEEE, address=device.ieee)
        else:
            src = t.AddrModeAddress(
                addr_mode=t.AddrMode.NWK, address=self.state.node_info.nwk
            )
            dst = t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=device.nwk)

        if self.config[conf.CONF_SOURCE_ROUTING]:
            source_route = self.build_source_route_to(dest=device)
        else:
            source_route = None

        tx_options = t.TransmitOptions.NONE

        if not expect_reply:
            tx_options |= t.TransmitOptions.ACK

        await self.send_packet(
            t.ZigbeePacket(
                src=src,
                src_ep=src_ep,
                dst=dst,
                dst_ep=dst_ep,
                tsn=sequence,
                profile_id=profile,
                cluster_id=cluster,
                data=t.SerializableBytes(data),
                extended_timeout=extended_timeout,
                source_route=source_route,
                tx_options=tx_options,
            )
        )

        return (zigpy.zcl.foundation.Status.SUCCESS, "")

    async def mrequest(
        self,
        group_id: t.uint16_t,
        profile: t.uint8_t,
        cluster: t.uint16_t,
        src_ep: t.uint8_t,
        sequence: t.uint8_t,
        data: bytes,
        *,
        hops: int = 0,
        non_member_radius: int = 3,
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
        """

        await self.send_packet(
            t.ZigbeePacket(
                src=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK, address=self.state.node_info.nwk
                ),
                src_ep=src_ep,
                dst=t.AddrModeAddress(addr_mode=t.AddrMode.Group, address=group_id),
                tsn=sequence,
                profile_id=profile,
                cluster_id=cluster,
                data=t.SerializableBytes(data),
                tx_options=t.TransmitOptions.NONE,
                radius=hops,
                non_member_radius=non_member_radius,
            )
        )

        return (zigpy.zcl.foundation.Status.SUCCESS, "")

    async def broadcast(
        self,
        profile: t.uint16_t,
        cluster: t.uint16_t,
        src_ep: t.uint8_t,
        dst_ep: t.uint8_t,
        grpid: t.uint16_t,
        radius: int,
        sequence: t.uint8_t,
        data: bytes,
        broadcast_address: t.BroadcastAddress = t.BroadcastAddress.RX_ON_WHEN_IDLE,
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
        """

        await self.send_packet(
            t.ZigbeePacket(
                src=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK, address=self.state.node_info.nwk
                ),
                src_ep=src_ep,
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.Broadcast, address=broadcast_address
                ),
                dst_ep=dst_ep,
                tsn=sequence,
                profile_id=profile,
                cluster_id=cluster,
                data=t.SerializableBytes(data),
                tx_options=t.TransmitOptions.NONE,
                radius=radius,
            )
        )

        return (zigpy.zcl.foundation.Status.SUCCESS, "")

    async def _discover_unknown_device(self, nwk: t.NWK) -> None:
        """
        Discover the IEEE address of a device with an unknown NWK.
        """

        return await zigpy.zdo.broadcast(
            app=self,
            command=zdo_types.ZDOCmd.IEEE_addr_req,
            grpid=None,
            radius=0,
            NWKAddrOfInterest=nwk,
            RequestType=zdo_types.AddrRequestType.Single,
            StartIndex=0,
        )

    def _maybe_parse_zdo(self, packet: t.ZigbeePacket) -> None:
        """
        Attempt to parse an incoming packet as ZDO, to extract useful notifications.
        """

        # The current zigpy device may not exist if we receive a packet early
        try:
            zdo = self._device.zdo
        except KeyError:
            zdo = zigpy.zdo.ZDO(None)

        try:
            zdo_hdr, zdo_args = zdo.deserialize(
                cluster_id=packet.cluster_id, data=packet.data.serialize()
            )
        except ValueError:
            LOGGER.debug("Could not parse ZDO message from packet")
            return

        # Interpret useful global ZDO responses and notifications
        if zdo_hdr.command_id == zdo_types.ZDOCmd.Device_annce:
            nwk, ieee, _ = zdo_args
            self.handle_join(nwk=nwk, ieee=ieee, parent_nwk=None)
        elif zdo_hdr.command_id in (
            zdo_types.ZDOCmd.NWK_addr_rsp,
            zdo_types.ZDOCmd.IEEE_addr_rsp,
        ):
            status, ieee, nwk, _, _, _ = zdo_args

            if status == zdo_types.Status.SUCCESS:
                LOGGER.debug("Discovered IEEE address for NWK=%s: %s", nwk, ieee)
                self.handle_join(nwk=nwk, ieee=ieee, parent_nwk=None)

    def packet_received(self, packet: t.ZigbeePacket) -> None:
        """
        Notify zigpy of a received Zigbee packet.
        """

        LOGGER.debug("Received a packet: %r", packet)
        assert packet.src is not None
        assert packet.dst is not None

        # Peek into ZDO packets to handle possible ZDO notifications
        if zigpy.zdo.ZDO_ENDPOINT in (packet.src_ep, packet.dst_ep):
            self._maybe_parse_zdo(packet)

        try:
            device = self.get_device_with_address(packet.src)
        except KeyError:
            LOGGER.warning("Unknown device %r", packet.src)

            if packet.src.addr_mode == t.AddrMode.NWK:
                # Manually send a ZDO IEEE address request to discover the device
                asyncio.create_task(self._discover_unknown_device(packet.src.address))

            return

        device.radio_details(lqi=packet.lqi, rssi=packet.rssi)

        self.handle_message(
            sender=device,
            profile=packet.profile_id,
            cluster=packet.cluster_id,
            src_ep=packet.src_ep,
            dst_ep=packet.dst_ep,
            message=packet.data.serialize(),
            dst_addressing=packet.dst.addr_mode,
        )

    def get_device_with_address(
        self, address: t.AddrModeAddress
    ) -> zigpy.device.Device:
        """
        Gets a `Device` object using the provided address mode address.
        """

        if address.addr_mode == t.AddrMode.NWK:
            return self.get_device(nwk=address.address)
        elif address.addr_mode == t.AddrMode.IEEE:
            return self.get_device(ieee=address.address)
        else:
            raise ValueError(f"Invalid address: {address!r}")

    @abc.abstractmethod
    async def permit_ncp(self, time_s: int = 60):
        """
        Permit joining on NCP.
        Not all radios will require this method.
        """
        raise NotImplementedError()  # pragma: no cover

    @abc.abstractmethod
    async def permit_with_key(self, node: t.EUI64, code: bytes, time_s: int = 60):
        """
        Permit a node to join with the provided install code bytes.
        """
        raise NotImplementedError()  # pragma: no cover

    @abc.abstractmethod
    async def write_network_info(
        self,
        *,
        network_info: zigpy.state.NetworkInfo,
        node_info: zigpy.state.NodeInfo,
    ) -> None:
        """
        Writes network and node state to the radio hardware.
        Any information not supported by the radio should be logged as a warning.
        """
        raise NotImplementedError()  # pragma: no cover

    @abc.abstractmethod
    async def load_network_info(self, *, load_devices: bool = False) -> None:
        """
        Loads network and node information from the radio hardware.

        :param load_devices: if `False`, supplementary network information that may take
                             a while to load should be skipped. For example, device NWK
                             addresses and link keys.
        """
        raise NotImplementedError()  # pragma: no cover

    @abc.abstractmethod
    async def reset_network_info(self) -> None:
        """
        Leaves the current network.
        """

        raise NotImplementedError()  # pragma: no cover

    async def permit(self, time_s: int = 60, node: t.EUI64 | str | None = None):
        """Permit joining on a specific node or all router nodes."""
        assert 0 <= time_s <= 254
        if node is not None:
            if not isinstance(node, t.EUI64):
                node = t.EUI64([t.uint8_t(p) for p in node])
            if node != self.state.node_info.ieee:
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
            self,  # app
            zdo_types.ZDOCmd.Mgmt_Permit_Joining_req,  # command
            0x0000,  # grpid
            0x00,  # radius
            time_s,
            0,
            broadcast_address=t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
        )
        return await self.permit_ncp(time_s)

    def get_sequence(self) -> t.uint8_t:
        self._send_sequence = (self._send_sequence + 1) % 256
        return self._send_sequence

    def get_device(
        self, ieee: t.EUI64 = None, nwk: t.NWK | int = None
    ) -> zigpy.device.Device:
        """
        Looks up a device in the `devices` dictionary based either on its NWK or IEEE
        address.
        """

        if ieee is not None:
            return self.devices[ieee]

        # If there two coordinators are loaded from the database, we want the active one
        if nwk == self.state.node_info.nwk:
            return self.devices[self.state.node_info.ieee]

        # TODO: Make this not terrible
        # Unlike its IEEE address, a device's NWK address can change at runtime so this
        # is not as simple as building a second mapping
        for dev in self.devices.values():
            if dev.nwk == nwk:
                return dev

        raise KeyError(f"Device not found: nwk={nwk!r}, ieee={ieee!r}")

    def get_endpoint_id(self, cluster_id: int, is_server_cluster: bool = False) -> int:
        """Returns coordinator endpoint id for specified cluster id."""
        return DEFAULT_ENDPOINT_ID

    def get_dst_address(self, cluster) -> zdo_types.MultiAddress:
        """Helper to get a dst address for bind/unbind operations.

        Allows radios to provide correct information especially for radios which listen
        on specific endpoints only.
        :param cluster: cluster instance to be bound to coordinator
        :returns: returns a "destination address"
        """
        dstaddr = zdo_types.MultiAddress()
        dstaddr.addrmode = 3
        dstaddr.ieee = self.state.node_info.ieee
        dstaddr.endpoint = self.get_endpoint_id(cluster.cluster_id, cluster.is_server)
        return dstaddr

    def update_config(self, partial_config: dict[str, Any]) -> None:
        """Update existing config."""
        self.config = {**self.config, **partial_config}

    @property
    def config(self) -> dict:
        """Return current configuration."""
        return self._config

    @config.setter
    def config(self, new_config) -> None:
        """Configuration setter."""
        self._config = self.SCHEMA(new_config)

    @property
    def groups(self):
        return self._groups

    @property
    def ota(self):
        return self._ota

    @property
    def _device(self):
        """The device being controlled."""
        return self.get_device(ieee=self.state.node_info.ieee)

    @zigpy.util.deprecated("await `app.shutdown()`")
    async def pre_shutdown(self):
        await self.shutdown()

    @property
    @zigpy.util.deprecated("use `app.state.node_info.nwk`")
    def nwk(self):
        return self.state.node_info.nwk

    @property
    @zigpy.util.deprecated("use `app.state.node_info.ieee`")
    def ieee(self):
        return self.state.node_info.ieee

    @property
    @zigpy.util.deprecated("use `app.state.network_info.pan_id`")
    def pan_id(self):
        return self.state.network_info.pan_id

    @property
    @zigpy.util.deprecated("use `app.state.network_info.extended_pan_id`")
    def extended_pan_id(self):
        return self.state.network_info.extended_pan_id

    @property
    @zigpy.util.deprecated("use `app.state.network_info.network_key`")
    def network_key(self):
        return self.state.network_info.network_key

    @property
    @zigpy.util.deprecated("use `app.state.network_info.channel`")
    def channel(self):
        return self.state.network_info.channel

    @property
    @zigpy.util.deprecated("use `app.state.network_info.channel_mask`")
    def channels(self):
        return self.state.network_info.channel_mask

    @property
    @zigpy.util.deprecated("use `app.state.network_info.nwk_update_id`")
    def nwk_update_id(self):
        return self.state.network_info.nwk_update_id
