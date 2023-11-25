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
    GreenPowerProxy,
)
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
    GREENPOWER_DEFAULT_LINK_KEY,
    GREENPOWER_ENDPOINT_ID,
)
import zigpy.types as t
from zigpy.types import (
    BroadcastAddress,
)
from zigpy.zgp import (
    GreenPowerDeviceID,
    GPCommissioningPayload,
    GPCommunicationMode,
    GPProxyCommissioningModeExitMode,
    GPDataFrame,
    GPSecurityLevel,
    SinkTableEntry,
)
from zigpy.zgp.commands import (
    GPCommand,
    GPCommandDescriptor,
    GPCommandToZCLMapping,
)
from zigpy.zgp.devices import (
    GPClustersByDeviceType,
)
from zigpy.zgp.ext_data import (
    GreenPowerExtData,
    GreenPowerExtDB
)

import zigpy.util
import zigpy.zcl
import zigpy.zdo.types

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

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
        self._application: ControllerApplication = application
        self.__controller_state: ControllerState = ControllerState.Uninitialized
        self._commissioning_mode: CommissioningMode = CommissioningMode.NotCommissioning
        self._proxy_unicast_target: zigpy.device.Device = None
        self._timeout_task: asyncio.Task = None
        self._ext_db = GreenPowerExtDB(self._application)

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

    def handle_message(self, device: zigpy.device.Device, profile_id: t.uint16_t, cluster_id: t.uint16_t, src_ep: t.uint8_t, dst_ep: t.uint8_t, data: bytes):
        if profile_id == zigpy.profiles.zgp.PROFILE_ID and src_ep == GREENPOWER_ENDPOINT_ID and cluster_id == GreenPowerProxy.cluster_id:
            hdr, args = self._gp_endpoint.deserialize(cluster_id, data)
            if hdr.command_id == GreenPowerProxy.ServerCommandDefs.notification.id:
                notif: GreenPowerProxy.GPNotificationSchema = args
                # notif.command_id
                pass

        pass

    async def initialize(self):
        await self._ext_db.load()
        self._application.add_listener(self)
        #self._application._callback_for_response(zigpy.listeners.ANY_DEVICE, [
        #    GreenPowerProxy.ServerCommandDefs.notification.schema()
        #], self._on_zcl_notification)

        try:
            await self._application._device.endpoints[GREENPOWER_ENDPOINT_ID].add_to_group(GREENPOWER_BROADCAST_GROUP)
        except (IndexError, KeyError):
            LOGGER.warn("No GP endpoint to add to GP Group; GP broadcasts will not function")
        
        try:
            self._gp_cluster.update_attribute(GreenPowerProxy.AttributeDefs.max_sink_table_entries.id, 0xFF)
            self._push_sink_table()
            self._gp_cluster.update_attribute(GreenPowerProxy.AttributeDefs.link_key.id, GREENPOWER_DEFAULT_LINK_KEY)
        except:
            LOGGER.warn("GP Controller failed to write initialization attrs")
        
        self._controller_state = ControllerState.Operational
        LOGGER.info("Green Power Controller initialized!")

    def _on_zcl_notification(self, hdr, command):
        LOGGER.info("Got green power ZCL notification")

    def _on_zcl_commissioning_notification(self, hdr, command):
        LOGGER.info("Got green power ZCL commissioning notification")

    async def remove_device(self, device: zigpy.device.Device):
        if not self._is_gp_device(device):
            LOGGER.warning("Green Power Controller got a request to remove a device that is not a GP device; refusing.")
            return
        entry = self._ext_db.get(device.ieee)
        pairing = GreenPowerProxy.GPPairingSchema(options=0)
        pairing.remove_gpd = 1
        pairing.gpd_id = entry.gpd_id
        pairing.communication_mode = entry.communication_mode
        if entry.communication_mode in (GPCommunicationMode.GroupcastForwardToCommGroup, GPCommunicationMode.GroupcastForwardToDGroup):
            # decommission groupcast
            LOGGER.debug("Sending broadcast GPD decommissioning.")
            await self._zcl_broadcast(GreenPowerProxy.ClientCommandDefs.pairing, pairing.as_dict())
            LOGGER.debug("Broadcast GPD decommissioning sent.")
        elif entry.communication_mode is (GPCommunicationMode.Unicast, GPCommunicationMode.UnicastLightweight):
            unicast_device = self._application.get_device(ieee=entry.unicast_sink)
            if unicast_device is not None:
                LOGGER.debug("Sending removal to unicast proxy.")
                await unicast_device.endpoints[GREENPOWER_ENDPOINT_ID].out_clusters[GreenPowerProxy.cluster_id].pairing(pairing)
                LOGGER.debug("Removal from unicast proxy complete.")
            else:
                LOGGER.debug("No assicated unicast proxy found; skipping!")
        await self._ext_db.remove(device)

    def handle_unknown_tunneled_green_power_frame(self, packet: t.ZigbeePacket):
        # if we're not listening for commissioning packets, don't worry too much about it
        # we can't really scan for these things so don't worry about the ZDO followup either
        if self._controller_state != ControllerState.Commissioning or self._commissioning_mode == CommissioningMode.Direct:
            return

        hdr, rest = foundation.ZCLHeader.deserialize(packet.data.value)
        if hdr.command_id == GreenPowerProxy.ServerCommandDefs.commissioning_notification.id:
            # here we go
            notif, rest = GreenPowerProxy.GPCommissioningNotificationSchema.deserialize(rest)
            if notif.security_level == GPSecurityLevel.NoSecurity and notif.command_id == GPCommand.Commissioning:
                LOGGER.debug("Received valid GP commissioning packet from %s", str(notif.gpd_id))
                comm_payload, rest = GPCommissioningPayload.deserialize(notif.payload)
                asyncio.ensure_future(
                    self._handle_commissioning_data_frame(notif.gpd_id, comm_payload, True),
                    loop=asyncio.get_running_loop()
                )


    async def _create_device(self, src_id: GreenPowerDeviceID, payload: GPCommissioningPayload, sink_table_entry: SinkTableEntry, from_zcl: bool) -> zigpy.device.Device:
        device_type = payload.device_type
        ieee = t.EUI64(src_id.serialize() + bytes([0,0,0,0]))
        device = self._application.add_device(ieee, t.uint16_t(src_id & 0xFFFF))
        device.skip_configuration = True
        device.status =  zigpy.device.Status.NEW
        
        device.node_desc = zdo.types.NodeDescriptor(2, 64, 128, 4174, 82, 82, 0, 82, 0)
        device.manufacturer = "GreenPower"
        ep: zigpy.endpoint.Endpoint = device.add_endpoint(1)
        ep.profile_id = zigpy.profiles.zha.PROFILE_ID
        ep.device_type = zigpy.profiles.zha.DeviceType.GREEN_POWER
        ep.status = zigpy.endpoint.Status.ZDO_INIT
        
        cluster: Cluster = ep.add_input_cluster(Basic.cluster_id)
        cluster._attr_cache[Basic.AttributeDefs.manufacturer.id] = device.manufacturer
        cluster._attr_last_updated[Basic.AttributeDefs.manufacturer.id] = datetime.now(timezone.utc)
        if device_type is not None and device_type in GPClustersByDeviceType:
            descriptor = GPClustersByDeviceType[device_type]
            device.model = descriptor.name
            cluster._attr_cache[Basic.AttributeDefs.model.id] = device.model
            cluster._attr_last_updated[Basic.AttributeDefs.model.id] = datetime.now(timezone.utc)
            for cluster_desc in descriptor.in_clusters:
                LOGGER.debug("Add input cluster id %s on device %s", cluster_desc.cluster_id, ieee)
                ep.add_input_cluster(cluster_desc.cluster_id)
            for cluster_desc in descriptor.out_clusters:
                LOGGER.debug("Add output cluster id %s on device %s", cluster_desc.cluster_id, ieee)
                ep.add_output_cluster(cluster_desc.cluster_id)
        else:
            device.model = "GreenPowerDevice"
            cluster.update_attribute(Basic.AttributeDefs.model.id, device.model)
        
        ep = device.add_endpoint(GREENPOWER_ENDPOINT_ID)
        ep.status = zigpy.endpoint.Status.ZDO_INIT
        ep.profile_id = zigpy.profiles.zgp.PROFILE_ID
        ep.device_type = device_type
        
        cluster = ep.add_output_cluster(GreenPowerProxy.cluster_id)
        device.status = zigpy.device.Status.ENDPOINTS_INIT
        self._application.device_initialized(device)
        return device

    async def _handle_commissioning_data_frame(self, src_id: GreenPowerDeviceID, commission_payload: GPCommissioningPayload, from_zcl: bool) -> bool:
        new_join = True
        ieee = t.EUI64(src_id.serialize() + bytes([0,0,0,0]))
        if self._get_gp_device_with_srcid(src_id) is not None:
            # well this is bad. we have a sink table entry but an incoming commissioning request?
            # do we update the info in here? unregister and re-register?? Figure this out...
            new_join = False
            device = self._application.get_device(ieee)
            return False # XXX for now

        comm_mode = GPCommunicationMode.GroupcastForwardToCommGroup if CommissioningMode.ProxyBroadcast in self._commissioning_mode else GPCommunicationMode.UnicastLightweight

        sink_table_entry = SinkTableEntry(
            options=0,
            gpd_id=src_id,
            device_id=commission_payload.device_type,
            radius=0xFF
        )
        sink_table_entry.communication_mode = comm_mode
        sink_table_entry.sequence_number_cap = commission_payload.mac_seq_num_cap
        sink_table_entry.rx_on_cap = commission_payload.rx_on_cap
        sink_table_entry.security_use = commission_payload.security_level != GPSecurityLevel.NoSecurity
        if commission_payload.gpd_key is not None:
            encrypted_key = self._encrypt_key(src_id, commission_payload.gpd_key)
        if comm_mode == GPCommunicationMode.GroupcastForwardToCommGroup:
            sink_table_entry.group_list = LVBytes(
                GREENPOWER_BROADCAST_GROUP.to_bytes(2, "little") + 0xFF.to_bytes(1) + 0xFF.to_bytes(1)
            )
        if sink_table_entry.security_use:
            sink_table_entry.sec_options = commission_payload.security_level | (commission_payload.key_type << 2)
        if sink_table_entry.security_use or sink_table_entry.sequence_number_cap:
            sink_table_entry.sec_frame_counter = commission_payload.gpd_outgoing_counter
        if commission_payload.gpd_key is not None:
            sink_table_entry.key = encrypted_key

        if new_join:
            device = await self._create_device(src_id, commission_payload, sink_table_entry, from_zcl)
            
        # self._push_sink_table()

        ext_data: GreenPowerExtData = GreenPowerExtData(
            ieee=device.ieee,
            gpd_id=src_id,
            sink_table_entry=sink_table_entry,
            counter=0,
            unicast_sink=t.EUI64.UNKNOWN,
            key=t.KeyData.UNKNOWN
        )

        if CommissioningMode.ProxyBroadcast in self._commissioning_mode or CommissioningMode.ProxyUnicast in self._commissioning_mode:
            pairing = GreenPowerProxy.GPPairingSchema(options=0)
            pairing.add_sink = 1
            pairing.communication_mode = comm_mode
            pairing.gpd_id = src_id
            pairing.gpd_mac_seq_num_cap = commission_payload.mac_seq_num_cap
            pairing.security_frame_counter_present = 1 # always true for pairing p.106 l.25
            pairing.frame_counter = commission_payload.gpd_outgoing_counter_present and commission_payload.gpd_outgoing_counter or 0
            ext_data.counter = pairing.frame_counter
            pairing.security_level = commission_payload.security_level
            pairing.security_key_type = commission_payload.key_type
            pairing.device_id = commission_payload.device_type

            if commission_payload.gpd_key is not None:
                pairing.security_key_present = 1
                pairing.key = encrypted_key
                ext_data.key = commission_payload.gpd_key

            if CommissioningMode.ProxyUnicast in self._commissioning_mode:
                pairing.sink_IEEE = self._application.state.node_info.ieee
                pairing.sink_nwk_addr = self._application.state.node_info.nwk
                ext_data.unicast_sink = self._proxy_unicast_target.ieee
                await self._proxy_unicast_target.endpoints[GREENPOWER_ENDPOINT_ID].out_clusters[GreenPowerProxy.cluster_id].pairing(pairing)
            elif CommissioningMode.ProxyBroadcast in self._commissioning_mode:
                pairing.sink_group = GREENPOWER_BROADCAST_GROUP
                await self._zcl_broadcast(GreenPowerProxy.ClientCommandDefs.pairing, pairing.as_dict())

            await self._ext_db.add(ext_data)

            return True
        else:
            """Direct commissioning mode... deal later"""
            return False
        
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
            if not device.endpoints[zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID]:
                LOGGER.warning("Device %s does not have green power support and cannot be used to commssion GP devices", str(device.ieee))
                return
            
            await device.endpoints[zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID].out_clusters[GreenPowerProxy.cluster_id].proxy_commissioning_mode(
                options = GreenPowerProxy.GPProxyCommissioningModeOptions(
                    enter=1,
                    exit_mode=GPProxyCommissioningModeExitMode.OnExpireOrExplicitExit
                ),
                window = time_s
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
            await self._proxy_unicast_target.endpoints[GREENPOWER_ENDPOINT_ID].out_clusters[GreenPowerProxy.cluster_id].proxy_commissioning_mode(
                options=GreenPowerProxy.GPProxyCommissioningModeOptions(enter=0),
            )
            LOGGER.debug("Successfully sent commissioning close request to %s", str(self._proxy_unicast_target.ieee))
            # we need to give the network and devices time to settle
            # just in case we have to immediately request more commissioning
            await asyncio.sleep(0.2)
        self._controller_state = ControllerState.Operational
        self._commissioning_mode = CommissioningMode.NotCommissioning
        self._proxy_unicast_target = None

    def _encrypt_key(self, gpd_id: GreenPowerDeviceID, key: t.KeyData) -> bytes:
        # A.1.5.9.1
        link_key_bytes = GREENPOWER_DEFAULT_LINK_KEY.serialize()
        key_bytes = key.serialize()
        src_bytes = gpd_id.to_bytes(4, "little")
        nonce = src_bytes + src_bytes + src_bytes + 0x05.to_bytes(1)
        assert len(nonce) == 13

        aesccm = AESCCM(link_key_bytes, tag_length=16)
        result = aesccm.encrypt(nonce, key_bytes, None)
        return result[0:16]

    async def _permit_timeout(self, time_s: int):
        """After timeout we just fall out of commissioning mode"""
        await asyncio.sleep(time_s)
        LOGGER.info("Green Power Controller commissioning window closing after timeout")
        self._controller_state = ControllerState.Operational
        self._commissioning_mode = CommissioningMode.NotCommissioning
        self._timeout_task = None

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

    async def _zcl_broadcast(
        self,
        command: zigpy.foundation.ZCLCommandDef,
        kwargs: dict = {},
        address: t.BroadcastAddress = BroadcastAddress.RX_ON_WHEN_IDLE,
        dst_ep: t.uint16_t = zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID,
        cluster_id: t.uint16_t = GreenPowerProxy.cluster_id,
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
                src_ep=zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID,
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

    def _is_gp_device(self, device: zigpy.device.Device) -> bool:
        return self._ext_db.contains(device.ieee)

    def _get_all_gp_devices(self) -> typing.List[zigpy.device.Device]:
        return [
            d for ieee,d in self._application.devices.items() if self._is_gp_device(d)
        ]
    
    def _get_gp_device_with_srcid(self, src_id: GreenPowerDeviceID) -> zigpy.device.Device | None:
        for ieee,device in self._application.devices.items():
            entry = self._ext_db.get(ieee)
            if entry is not None and entry.gpd_id == src_id:
                return device
        return None

    def _push_sink_table(self):
        sink_table_bytes: bytes = bytes()
        for entry in self._ext_db._all_data:
            sink_table_bytes = sink_table_bytes + entry.sink_table_entry.serialize()
        result = t.LongOctetString(t.uint16_t(len(sink_table_bytes)).serialize() + sink_table_bytes)
        self._gp_cluster.update_attribute(GreenPowerProxy.AttributeDefs.sink_table.id, result)



                


