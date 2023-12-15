from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import enum
import logging
import sys
import typing 

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from zigpy import zdo
from zigpy.types.basic import LVBytes, Optional
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.clusters.general import (
    Basic,
)
from zigpy.zcl.clusters.greenpower import (
    GPNotificationSchema,
    GreenPowerProxy,
)
from zigpy.zgp.types import GPSecurityKeyType
if sys.version_info[:2] < (3, 11):
    from async_timeout import timeout as asyncio_timeout  # pragma: no cover
else:
    from asyncio import timeout as asyncio_timeout  # pragma: no cover

import zigpy.config as conf
import zigpy.application
import zigpy.device
import zigpy.endpoint
import zigpy.listeners
import zigpy.profiles.zgp
from zigpy.profiles.zgp import (
    GREENPOWER_BROADCAST_GROUP,
    GREENPOWER_CLUSTER_ID,
    GREENPOWER_DEFAULT_LINK_KEY,
    GREENPOWER_ENDPOINT_ID,
)
import zigpy.types as t
from zigpy.types import (
    BroadcastAddress,
)
from zigpy.zgp import (
    GreenPowerDeviceID,
    GreenPowerDeviceData,
    GPChannelSearchPayload,
    GPCommissioningPayload,
    GPCommunicationMode,
    GPDataFrame,
    GPProxyCommissioningModeExitMode,
    GPReplyPayload,
    GPSecurityLevel,
)
from zigpy.zgp.device import GreenPowerDevice
from zigpy.zgp.foundation import GPCommand
from zigpy.zgp.security import zgp_decrypt, zgp_encrypt

import zigpy.util
import zigpy.zcl
import zigpy.zdo.types

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication
    from zigpy.zcl.foundation import ZCLCommandDef

LOGGER = logging.getLogger(__name__)

class ControllerState(enum.Enum):
    Uninitialized = 0
    Initializing = 1
    Operational = 2
    Commissioning = 3
    Error = 255

class CommissioningMode(enum.Flag):
    NotCommissioning = 0
    Direct         = 0b001
    ProxyUnicast   = 0b010
    ProxyBroadcast = 0b100

class GreenPowerController(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):
    """Controller that tracks the current GPS state"""
    def __init__(self, application: ControllerApplication):
        super().__init__()
        self._application: ControllerApplication = application
        self.__controller_state: ControllerState = ControllerState.Uninitialized
        self._commissioning_mode: CommissioningMode = CommissioningMode.NotCommissioning
        self._proxy_unicast_target: zigpy.device.Device = None
        self._timeout_task: asyncio.Task = None
        self._rxon_inflight: dict[GreenPowerDeviceID, GreenPowerDeviceData] = {}

    @property 
    def _controller_state(self):
        return self.__controller_state

    @_controller_state.setter
    def _controller_state(self, value):
        if self.__controller_state != value:
            LOGGER.debug(
                "Green power controller transition states '%s' to '%s'", 
                str(self.__controller_state), 
                str(value))
            self.__controller_state = value

    @property
    def _gp_endpoint(self) -> zigpy.endpoint.Endpoint:
        return self._application._device.endpoints[GREENPOWER_ENDPOINT_ID]

    @property
    def _gp_cluster(self) -> zigpy.zcl.Cluster:
        return self._gp_endpoint.in_clusters[GreenPowerProxy.cluster_id]

    async def initialize(self):
        try:
            self._gp_cluster.update_attribute(GreenPowerProxy.AttributeDefs.max_sink_table_entries.id, 0xFF)
            self._gp_cluster.update_attribute(GreenPowerProxy.AttributeDefs.link_key.id, GREENPOWER_DEFAULT_LINK_KEY)
            self._push_sink_table()
        except Exception as e:
            LOGGER.warn("GP Controller failed to write initialization attrs: %s", e)
        
        try:
            # group = self._application.groups.add_group(GREENPOWER_BROADCAST_GROUP, "Green Power Broadcast")
            # group.add_member(self._gp_endpoint)
            await self._gp_endpoint.add_to_group(GREENPOWER_BROADCAST_GROUP)
        except Exception as e:
            LOGGER.debug("GP endpoint failed to add to broadcast group: %s", e)

        self._controller_state = ControllerState.Operational
        LOGGER.info("Green Power Controller initialized!")

    def packet_received(self, packet: t.ZigbeePacket) -> None:
        assert packet.src_ep == GREENPOWER_ENDPOINT_ID
        assert packet.cluster_id == GREENPOWER_CLUSTER_ID

        hdr, args = self._gp_endpoint.deserialize(packet.cluster_id, packet.data.serialize())

        # try our best to resolve who is talking and what they're asking,
        # so we can filter based on frame counter
        gp_device: GreenPowerDevice = None
        try:
            device: zigpy.device.Device = self._application.get_device_with_address(packet.src)
            # unicast forward, resolve to GPD
            if not device.is_green_power_device:
                # by this time we should be able to inspect the incoming args and resolve
                # the GP device, but if not bail out and handle it down the pipe
                gp_device = self._get_gp_device_with_srcid(args.gpd_id)
            else:
                gp_device = device
        except KeyError:
            pass
        
        # peek in and see if we're dealing with an infrastructure command, or a standard
        # notification packet. if it's infrastructure, route the message
        if hdr.command_id == GreenPowerProxy.ServerCommandDefs.commissioning_notification.id:
            self.handle_commissioning_packet(packet)
            return
        elif hdr.command_id == GreenPowerProxy.ServerCommandDefs.pairing_search.id:
            self.handle_pairing_search(packet)
            return
        elif hdr.command_id == GreenPowerProxy.ServerCommandDefs.notification.id:
            if gp_device is None:
                LOGGER.warn("GP controller got non-infrastructure packet from non-GP device %s", str(packet.src))
                return

            # XXX: wraparound?
            if args.frame_counter != 0 and gp_device.green_power_data.frame_counter >= args.frame_counter:
                LOGGER.debug("Passing duplicate green power frame %s", str(args.frame_counter))
                return

            gp_device.green_power_data.frame_counter = args.frame_counter
            self.listener_event("gpd_counter_updated", gp_device.ieee, gp_device.green_power_data.frame_counter)

            # At this point we're through the infrastructure stuff, forward the notification packet
            # into the GP device proper for processing
            gp_device.packet_received(packet)

    async def remove_device(self, device: GreenPowerDevice):
        if not device.is_green_power_device:
            LOGGER.warning("Green Power Controller got a request to remove a device that is not a GP device; refusing.")
            return
        LOGGER.debug("Green Power Controller removing device %s", str(device.gpd_id))
        entry = device.green_power_data
        pairing = GreenPowerProxy.GPPairingSchema(options=0)
        pairing.remove_gpd = 1
        pairing.gpd_id = entry.gpd_id
        pairing.communication_mode = entry.communication_mode
        # as it happens, we don't have to be too careful here, we can just broadcast the leave
        # message and be done with it
        await self._zcl_broadcast(GreenPowerProxy.ClientCommandDefs.pairing, pairing.as_dict())
        LOGGER.debug("Green Power Controller removed %s successfully", str(device.gpd_id))

    def handle_commissioning_packet(self, packet: t.ZigbeePacket):
        # if we're not listening for commissioning packets, don't worry too much about it
        # we can't really scan for these things so don't worry about the ZDO followup either
        if self._controller_state != ControllerState.Commissioning or self._commissioning_mode == CommissioningMode.Direct:
            return

        hdr, rest = foundation.ZCLHeader.deserialize(packet.data.serialize())
        if hdr.command_id == GreenPowerProxy.ServerCommandDefs.commissioning_notification.id:
            # here we go
            notif, rest = GreenPowerProxy.GPCommissioningNotificationSchema.deserialize(rest)
            LOGGER.debug("Parsing ZGP command %s from %s", notif.command_id._hex_repr(), notif.gpd_id)

            # So... according to Figure 70, Success GPDF is sent before ZGP Pairing is sent, which in my mind means
            # we should have NoSecurity set. The SWS200, however, starts sending Success frames with
            # security flags before Pairing is sent, meaning we get a security_failed flag. Try to ignore it.
            # (Check Encrypted first to make sure we're not responding incorrectly to unrelated stuff)
            if notif.security_level != GPSecurityLevel.Encrypted and notif.command_id == GPCommand.CommissionSuccess:
                LOGGER.debug("Received commission success packet %s", str(notif.gpd_id))
                asyncio.create_task(
                    self._handle_success(notif),
                    name="Handle Success"
                )
                return

            if notif.security_failed:
                LOGGER.debug("Got GP commissioning frame with bad security parameters; passing")
                return
            
            if notif.security_level == GPSecurityLevel.NoSecurity:
                if notif.command_id == GPCommand.ChannelSearch:
                    LOGGER.debug("Channel search packet from %s", str(notif.gpd_id))
                    cs_payload, rest = GPChannelSearchPayload.deserialize(notif.payload)
                    asyncio.create_task(
                        self._handle_channel_Search(cs_payload, packet, notif),
                        name="Handle Channel Search"
                    )
                elif notif.command_id == GPCommand.Commissioning:
                    LOGGER.debug("Received valid GP commissioning packet from %s", str(notif.gpd_id))
                    comm_payload, rest = GPCommissioningPayload.deserialize(notif.payload)
                    asyncio.create_task(
                        self._handle_commissioning_data_frame(notif.gpd_id, comm_payload, packet, notif),
                        name="Handle Commission Data Frame"
                    )

    def handle_pairing_search(self, packet: t.ZigbeePacket):
        # I guess... 
        return

    async def handle_received_green_power_frame(self, frame: GPDataFrame):
        """Build this out later to allow for direct interaction and commissioning"""

    async def permit(self, time_s: int = 60, device: zigpy.device.Device = None):
        assert 0 <= time_s <= 254

        if time_s == 0:
            await self._stop_permit()
            return

        assert self._controller_state != ControllerState.Uninitialized

        # this flow kinda stinks, but ZHA doesn't give us a message to
        # stop commissioning near as I can tell. it just waits for the
        # window to close
        if self._controller_state == ControllerState.Commissioning:
            await self._stop_permit()
            # really, really let it settle, as devices hate the close/open
            await asyncio.sleep(0.2)

        assert self._controller_state == ControllerState.Operational
        
        # We can direct commission without a lot of help
        if device == self._application._device:
            self._commissioning_mode = CommissioningMode.Direct
        elif device is not None:
            # No GP endpoint nothing doing sorry
            if not device.endpoints[GREENPOWER_ENDPOINT_ID]:
                LOGGER.warning("Device %s does not have green power support and cannot be used to commssion GP devices", str(device.ieee))
                return
            
            await self.send_no_response_command(
                device,
                GreenPowerProxy.ClientCommandDefs.proxy_commissioning_mode,
                {
                    "options": GreenPowerProxy.GPProxyCommissioningModeOptions(
                        enter=1,
                        exit_mode=GPProxyCommissioningModeExitMode.OnExpireOrExplicitExit
                    ),
                    "window": time_s
                }
            )
            LOGGER.debug("Successfully sent commissioning open request to %s", str(device.ieee))
            self._controller_state = ControllerState.Commissioning
            self._commissioning_mode = CommissioningMode.ProxyUnicast
            self._proxy_unicast_target = device
        else:
            await self._send_commissioning_broadcast_command(time_s)
            self._controller_state = ControllerState.Commissioning
            self._commissioning_mode = CommissioningMode.ProxyBroadcast
        
        # kickstart the timeout task
        self._timeout_task = asyncio.get_running_loop().create_task(self._permit_timeout(time_s))

    async def _stop_permit(self):
        # this may happen if the application experiences an unexpected
        # shutdown before we're initialized, or during startup when the NCP
        # state is being ensured. more common paths are asserted, not tested.
        if self._controller_state == ControllerState.Uninitialized:
            LOGGER.debug("GreenPowerController ignoring stop permit request on uninitialized state")
            return
        
        if self._controller_state != ControllerState.Commissioning:
            LOGGER.debug(
                "GreenPowerController not valid to stop commissioning, current state: %s",
                str(self._controller_state)
            )
            return
        
        if self._timeout_task != None:
            self._timeout_task.cancel()
            self._timeout_task = None
        else:
            LOGGER.error("Green Power Controller in commissioning state with no timeout task!")

        if CommissioningMode.ProxyBroadcast in self._commissioning_mode:
            await self._send_commissioning_broadcast_command(0)
        elif CommissioningMode.ProxyUnicast in self._commissioning_mode:
            await self.send_no_response_command(
                self._proxy_unicast_target,
                GreenPowerProxy.ClientCommandDefs.proxy_commissioning_mode,
                {"options": GreenPowerProxy.GPProxyCommissioningModeOptions(enter=0)}
            )
            LOGGER.debug("Successfully sent commissioning close request to %s", str(self._proxy_unicast_target.ieee))
            # we need to give the network and devices time to settle
            # just in case we have to immediately request more commissioning
            await asyncio.sleep(0.2)
        self._controller_state = ControllerState.Operational
        self._commissioning_mode = CommissioningMode.NotCommissioning
        self._proxy_unicast_target = None

    async def _permit_timeout(self, time_s: int):
        """After timeout we just fall out of commissioning mode"""
        await asyncio.sleep(time_s)
        LOGGER.info("Green Power Controller commissioning window closing after timeout")
        self._controller_state = ControllerState.Operational
        self._commissioning_mode = CommissioningMode.NotCommissioning
        self._timeout_task = None

    async def _handle_success(self, notif: GreenPowerProxy.GPCommissioningNotificationSchema) -> bool:
        src_id = notif.gpd_id
        # If we can't resolve the greenpowerdata, well, that stinks but nothing doing.
        if not src_id in self._rxon_inflight:
            LOGGER.debug("Success frame recieved from unknown GPD %s; passing!", notif.gpd_id)
            return False
        
        LOGGER.debug("Parsing success frame from %s", notif.gpd_id)
        gp_data = self._rxon_inflight[src_id]
        new_join = True
        if device := self._get_gp_device_with_srcid(src_id):
            new_join = False

        if new_join:
            device = GreenPowerDevice(self._application, gp_data)
            self._application.device_initialized(device)
            device = self._application.get_device(gp_data.ieee) # quirks may have overwritten this
        else:
            device.green_power_data = gp_data
        
        return await self._send_pairing(gp_data)

    async def _handle_channel_Search(self, search_payload: GPChannelSearchPayload, packet: t.ZigbeePacket, notif: GreenPowerProxy.GPCommissioningNotificationSchema) -> bool:
        response = GreenPowerProxy.GPResponseSchema(options=0)
        if notif.proxy_info_present:
            response.temp_master_short_addr = notif.gpp_short_addr
        else:
            LOGGER.warn("Cannot commission with no temp master addr!")
            return False
        
        response.temp_master_tx_channel = search_payload.next_channel
        response.gpd_id = notif.gpd_id
        response.gpd_command_id = GPCommand.ChannelSearchResponse
        # Spare having to create an intermediary representation for this one thing; the format is:
        # [CommandID = ChannelSearchResponse, options = net channel - 11] (aka channel packed into 4 bits)
        response.gpd_command_payload = t.LVBytes(
            GPCommand.ChannelSearchResponse.to_bytes(1) + 
            (self._application.state.network_info.channel - 11).to_bytes(1)
        )
        await self._zcl_broadcast(GreenPowerProxy.ClientCommandDefs.response, response.as_dict())
        return False

    async def _send_rx_cap_pair_response(self, notif: GreenPowerProxy.GPCommissioningNotificationSchema, commission_payload: GPCommissioningPayload, green_power_data: GreenPowerDeviceData) -> bool:
        # First, build the response schema for the GPP...
        response = GreenPowerProxy.GPResponseSchema(options=0)
        if notif.proxy_info_present:
            response.temp_master_short_addr = notif.gpp_short_addr
        else:
            LOGGER.warn("Cannot commission with no temp master addr!")
            return False
        response.temp_master_tx_channel = self._application.state.network_info.channel - 11
        response.gpd_id = notif.gpd_id
        response.gpd_command_id = GPCommand.CommissioningResponse
        
        # Great now we can build the reply to the GPD itself
        payload: GPReplyPayload = GPReplyPayload(options=0)
        # XXX: these are None for the time being
        payload.security_key_type = green_power_data.security_key_type
        payload.security_level = green_power_data.security_level
        if commission_payload.pan_id_req:
            payload.pan_id_present = 1
            payload.pan_id = self._application.state.network_info.pan_id
        if commission_payload.gp_sec_key_req:
            # XXX: Cleartext key, this isn't good!
            payload.set_key_no_encryption(self._application.state.network_info.network_key)
            # XXX: next steps: encrypt it, need an exemplary capture
            # payload.set_key_with_encryption(green_power_data.raw_key, notif.gpd_id, commission_payload.gpd_outgoing_counter)
        response.gpd_command_payload = t.LVBytes(payload.serialize())
        await self._zcl_broadcast(GreenPowerProxy.ClientCommandDefs.response, response.as_dict())
        return True
    
    async def _send_pairing(self, green_power_data: GreenPowerDeviceData) -> bool:
        comm_mode = green_power_data.communication_mode
        if CommissioningMode.ProxyBroadcast in self._commissioning_mode or CommissioningMode.ProxyUnicast in self._commissioning_mode:
            LOGGER.debug("Sending pairing info for %s", green_power_data.gpd_id)
            pairing = GreenPowerProxy.GPPairingSchema(options=0)
            pairing.add_sink = 1
            pairing.gpd_fixed = green_power_data.fixed_location
            pairing.communication_mode = comm_mode
            pairing.gpd_id = green_power_data.gpd_id
            pairing.gpd_mac_seq_num_cap = green_power_data.sequence_number_cap
            pairing.security_frame_counter_present = 1 # always true for pairing p.106 l.25
            pairing.frame_counter = green_power_data.frame_counter
            pairing.security_level = green_power_data.security_level
            pairing.security_key_type = green_power_data.security_key_type
            pairing.device_id = green_power_data.device_id

            if green_power_data.raw_key != t.KeyData.UNKNOWN:
                pairing.security_key_present = 1
                pairing.key = green_power_data.encrypt_key_for_gpp()

            if CommissioningMode.ProxyUnicast in self._commissioning_mode:
                pairing.sink_IEEE = self._application.state.node_info.ieee
                pairing.sink_nwk_addr = self._application.state.node_info.nwk
                await self.send_no_response_command(
                    self._proxy_unicast_target,
                    GreenPowerProxy.ClientCommandDefs.pairing,
                    pairing.as_dict()
                )
            elif CommissioningMode.ProxyBroadcast in self._commissioning_mode:
                pairing.sink_group = GREENPOWER_BROADCAST_GROUP
                await self._zcl_broadcast(GreenPowerProxy.ClientCommandDefs.pairing, pairing.as_dict())

            return True
        else:
            """Direct commissioning mode... deal later"""
            return False

    async def __dup_comm_frame_timeout(self, src_id: GreenPowerDeviceID, sleep_time: float = 5):
        await asyncio.sleep(sleep_time)
        self._rxon_inflight.pop(src_id)

    async def _handle_commissioning_data_frame(self, src_id: GreenPowerDeviceID, commission_payload: GPCommissioningPayload, packet: t.ZigbeePacket | None = None, notif: GreenPowerProxy.GPCommissioningNotificationSchema | None = None) -> bool:
        # This is a duplicate we should ignore; we haven't yet resolved our outgoing for Rx-cap 
        if src_id in self._rxon_inflight:
            LOGGER.debug("Commission data frame already processed for %s; passing!", src_id)
            return False
        
        new_join = True
        ieee = t.EUI64(src_id.serialize() + bytes([0,0,0,0]))
        device: GreenPowerDevice = None
        rx_on = commission_payload.rx_on_cap

        if CommissioningMode.ProxyBroadcast in self._commissioning_mode:
            comm_mode = GPCommunicationMode.GroupcastForwardToCommGroup  
        else: 
            comm_mode = GPCommunicationMode.UnicastLightweight
        
        green_power_data = GreenPowerDeviceData(
            gpd_id=src_id,
            device_id=commission_payload.device_type,
            unicast_proxy=self._proxy_unicast_target and self._proxy_unicast_target.ieee or t.EUI64.UNKNOWN,
            security_level=commission_payload.security_level,
            security_key_type=commission_payload.key_type,
            communication_mode=comm_mode,
            frame_counter=commission_payload.gpd_outgoing_counter if commission_payload.gpd_outgoing_counter_present else 0,
            raw_key=commission_payload.get_validated_key(src_id),
            assigned_alias=False,
            fixed_location=commission_payload.fixed_loc,
            rx_on_cap=rx_on,
            sequence_number_cap=commission_payload.mac_seq_num_cap,
            manufacturer_id=commission_payload.manufacturer_id if commission_payload.manufacturer_id_present else 0,
            model_id=commission_payload.model_id if commission_payload.model_id_present else 0,
        )

        if self._get_gp_device_with_srcid(src_id) is not None:
            new_join = False
            device = self._application.get_device(ieee)
            LOGGER.debug("Skipping commissioning packet for known device %s", str(src_id))
            return False # handle the frame counter checks first!
            # signal to proxy devices that we're updating the proxy tables...
            # await self.remove_device(device)

        if rx_on:
            self._rxon_inflight[src_id] = green_power_data
            timeouttask = asyncio.create_task(self.__dup_comm_frame_timeout(src_id))

            result = await self._send_rx_cap_pair_response(notif, commission_payload, green_power_data)
            if not result:
                LOGGER.warn("Failed to send Rx response packet!")
                timeouttask.cancel()
                self._rxon_inflight.pop(src_id)
                return False
            # ok fine so we do this a little early to head duplicates off at the pass
            LOGGER.debug("Successfully sent RX cap response. Flagging as waiting for success.")
            return False

        if new_join:
            device = GreenPowerDevice(self._application, green_power_data)
            self._application.device_initialized(device)
            device = self._application.get_device(ieee) # quirks may have overwritten this
        else:
            device.green_power_data = green_power_data
        
        return await self._send_pairing(green_power_data)
        
    async def _send_commissioning_broadcast_command(self, time_s: int):
        named_arguments = None
        if time_s > 0:
            named_arguments = {
                "options": GreenPowerProxy.GPProxyCommissioningModeOptions(
                    enter=1,
                    exit_mode=GPProxyCommissioningModeExitMode.OnExpireOrExplicitExit
                ),
                "window": time_s
            }
        else:
            named_arguments = {
                "options": GreenPowerProxy.GPProxyCommissioningModeOptions(enter=0)
            }

        await self._zcl_broadcast(GreenPowerProxy.ClientCommandDefs.proxy_commissioning_mode, named_arguments)

    async def send_no_response_command(
        self,
        device: zigpy.device.Device,
        command: ZCLCommandDef,
        kwargs: dict = {}
    ):
        tsn = self._application.get_sequence()
        hdr, request = Cluster._create_request(
            self=None,
            general=False,
            command_id=command.id,
            schema=command.schema,
            tsn=tsn,
            disable_default_response=True,
            direction=command.direction,
            args=(),
            kwargs=kwargs,
        )
        await self._application.send_packet(
            t.ZigbeePacket(
                src=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK, address=self._application.state.node_info.nwk
                ),
                src_ep=GREENPOWER_ENDPOINT_ID,
                dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=device.nwk),
                dst_ep=GREENPOWER_ENDPOINT_ID,
                tsn=tsn,
                profile_id=zigpy.profiles.zgp.PROFILE_ID,
                cluster_id=GREENPOWER_CLUSTER_ID,
                data=t.SerializableBytes(hdr.serialize() + request.serialize()),
                tx_options=t.TransmitOptions.NONE,
                radius=30,
            )
        )

    async def _zcl_broadcast(
        self,
        command: ZCLCommandDef,
        kwargs: dict = {},
        address: t.BroadcastAddress = BroadcastAddress.RX_ON_WHEN_IDLE,
        dst_ep: t.uint16_t = GREENPOWER_ENDPOINT_ID,
        cluster_id: t.uint16_t = GREENPOWER_CLUSTER_ID,
        profile_id: t.uint16_t = zigpy.profiles.zgp.PROFILE_ID,
        radius=30,
    ):
        tsn = self._application.get_sequence()

        hdr, request = Cluster._create_request(
            self=None,
            general=False,
            command_id=command.id,
            schema=command.schema,
            tsn=tsn,
            disable_default_response=True,
            direction=command.direction,
            args=(),
            kwargs=kwargs,
        )

        # Broadcast
        await self._application.send_packet(
            t.ZigbeePacket(
                src=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK, address=self._application.state.node_info.nwk
                ),
                src_ep=GREENPOWER_ENDPOINT_ID,
                dst=t.AddrModeAddress(addr_mode=t.AddrMode.Broadcast, address=address),
                dst_ep=dst_ep,
                tsn=tsn,
                profile_id=profile_id,
                cluster_id=cluster_id,
                data=t.SerializableBytes(hdr.serialize() + request.serialize()),
                tx_options=t.TransmitOptions.NONE,
                radius=radius,
            )
        )
        # Let the broadcast work its way thru the net
        await asyncio.sleep(0.2)

    def _get_all_gp_devices(self) -> typing.List[GreenPowerDevice]:
        return [d for _,d in self._application.devices.items() if d.is_green_power_device]

    def _get_gp_device_with_srcid(self, src_id: GreenPowerDeviceID) -> GreenPowerDevice | None:
        return next((d for d in self._get_all_gp_devices() if d.gpd_id == src_id), None)

    def _push_sink_table(self):
        sink_table_bytes: bytes = bytes()
        for device in self._get_all_gp_devices():
            sink_table_bytes = sink_table_bytes + device.green_power_data.sink_table_entry.serialize()
        result = t.LongOctetString(t.uint16_t(len(sink_table_bytes)).serialize() + sink_table_bytes)
        self._gp_cluster.update_attribute(GreenPowerProxy.AttributeDefs.sink_table.id, result)



                


