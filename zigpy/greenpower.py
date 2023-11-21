from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import enum
import logging
import sys
import typing 
import warnings

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from zigpy import zdo
from zigpy.types.basic import LVBytes, Optional

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
    GPCommand,
    GREENPOWER_BROADCAST_GROUP,
    GREENPOWER_DEFAULT_LINK_KEY,
    GREENPOWER_ENDPOINT_ID,
)
import zigpy.types as t
from zigpy.types import (
    BroadcastAddress,
    GPCommissioningPayload,
    GPCommunicationMode,
    GPDataFrame,
    GPDeviceType,
    GPFrameType,
    GPSecurityLevel,
    SinkTableEntry,
)
import zigpy.util
import zigpy.zcl
import zigpy.zdo.types

from zigpy.zcl import Cluster, foundation
import zigpy.zcl.clusters.closures
import zigpy.zcl.clusters.lighting
import zigpy.zcl.clusters.measurement
from zigpy.zcl.clusters.general import (
    Basic,
    Scenes,
    OnOff,
    LevelControl,
)
from zigpy.zcl.clusters.greenpower import (
    GreenPowerProxy,
)

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

class GPDeviceTypeDescriptor:
    name: str
    in_clusters: typing.List[zigpy.zcl.Cluster]
    out_clusters: typing.List[zigpy.zcl.Cluster]
    def __init__(self, name: str, in_clusters: typing.List[zigpy.zcl.Cluster] = [], out_clusters: typing.List[zigpy.zcl.Cluster] = []) -> None:
        self.name = name
        self.in_clusters = in_clusters
        self.out_clusters = out_clusters

GPEndpointsByDeviceType: typing.Dict[GPDeviceType, GPDeviceTypeDescriptor] = {
    GPDeviceType.SWITCH_SIMPLE_ONE_STATE: GPDeviceTypeDescriptor("Simple Generic 1-state", out_clusters=[OnOff]),
    GPDeviceType.SWITCH_SIMPLE_TWO_STATE: GPDeviceTypeDescriptor("Simple Generic 2-state", out_clusters=[OnOff]),
    GPDeviceType.SWITCH_ON_OFF: GPDeviceTypeDescriptor("On/Off Switch", out_clusters=[Scenes, OnOff]),
    GPDeviceType.SWITCH_LEVEL_CONTROL: GPDeviceTypeDescriptor("Level Control Switch",out_clusters=[LevelControl]),
    GPDeviceType.SENSOR_SIMPLE: GPDeviceTypeDescriptor("Simple Sensor"),
    GPDeviceType.SWITCH_ADVANCED_ONE_STATE: GPDeviceTypeDescriptor("Advanced Generic 1-state Switch", out_clusters=[Scenes, OnOff]),
    GPDeviceType.SWITCH_ADVANCED_TWO_STATE: GPDeviceTypeDescriptor("Advanced Generic 2-state Switch", out_clusters=[Scenes, OnOff]),
    GPDeviceType.SWITCH_GENERIC: GPDeviceTypeDescriptor("Generic Switch", out_clusters=[Scenes, OnOff]),
    GPDeviceType.SWITCH_COLOR_DIMMER: GPDeviceTypeDescriptor("Color Dimmer Switch",out_clusters=[zigpy.zcl.clusters.lighting.Color]),
    GPDeviceType.SENSOR_LIGHT: GPDeviceTypeDescriptor("Light Sensor", in_clusters=[zigpy.zcl.clusters.measurement.IlluminanceMeasurement]),
    GPDeviceType.SENSOR_OCCUPANCY: GPDeviceTypeDescriptor("Occupancy Sensor", in_clusters=[zigpy.zcl.clusters.measurement.OccupancySensing]),
    GPDeviceType.DOOR_LOCK_CONTROLLER: GPDeviceTypeDescriptor("Door Lock Controller", out_clusters=[zigpy.zcl.clusters.closures.DoorLock]),
    GPDeviceType.SENSOR_TEMPERATURE: GPDeviceTypeDescriptor("Temperature Sensor", in_clusters=[zigpy.zcl.clusters.measurement.TemperatureMeasurement]),
    GPDeviceType.SENSOR_PRESSURE: GPDeviceTypeDescriptor("Pressure Sensor", in_clusters=[zigpy.zcl.clusters.measurement.PressureMeasurement]),
    GPDeviceType.SENSOR_FLOW: GPDeviceTypeDescriptor("Flow Sensor", in_clusters=[zigpy.zcl.clusters.measurement.FlowMeasurement]),
    GPDeviceType.SENSOR_ENVIRONMENT_INDOOR: GPDeviceTypeDescriptor("Indoor Environment Sensor")
}

class GreenPowerController(zigpy.util.LocalLogMixin, zigpy.util.ListenableMixin):
    """Controller that tracks the current GPS state"""
    def __init__(self, application: ControllerApplication):
        self._application: ControllerApplication = application
        self.__controller_state: ControllerState = ControllerState.Uninitialized
        self._commissioning_mode: CommissioningMode = CommissioningMode.NotCommissioning
        self._proxy_unicast_target: zigpy.device.Device = None
        self._timeout_task: asyncio.Task = None

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
    def _gp_cluster(self) -> zigpy.zcl.Cluster:
        return self._application._device.endpoints[GREENPOWER_ENDPOINT_ID].in_clusters[GreenPowerProxy.cluster_id]

    async def initialize(self):
        self._application._callback_for_response(zigpy.listeners.ANY_DEVICE, [
            GreenPowerProxy.ServerCommandDefs.notification.schema()
        ], self._on_zcl_notification)
        self._application._callback_for_response(zigpy.listeners.ANY_DEVICE, [
            GreenPowerProxy.ServerCommandDefs.commissioning_notification.schema()
        ], self._on_zcl_commissioning_notification)

        try:
            await self._application._device.endpoints[GREENPOWER_ENDPOINT_ID].add_to_group(GREENPOWER_BROADCAST_GROUP)
        except (IndexError, KeyError):
            LOGGER.warn("No GP endpoint to add to GP Group; GP broadcasts will not function")
        
        try:
            await self._gp_cluster.write_attributes({
                "max_sink_table_entries": 0xFF,
                "sink_table": self._sink_table_as_bytes(),
            })
        except:
            LOGGER.warn("GP Controller failed to write initialization attrs")
        
        self._controller_state = ControllerState.Operational
        LOGGER.info("Green Power Controller initialized!")

    def _get_sink_table_entry(self, gpd_id: t.GreenPowerDeviceID):
        return next((e for e in self._sink_table if e.device_id == gpd_id), None)

    def _on_zcl_notification(self, hdr, command):
        LOGGER.info("Got green power ZCL notification")

    def _on_zcl_commissioning_notification(self, hdr, command):
        LOGGER.info("Got green power ZCL commissioning notification")

    def handle_unknown_tunneled_green_power_frame(self, packet: t.ZigbeePacket):
        # if we're not listening for commissioning packets, don't worry too much about it
        # we can't really scan for these things so don't worry about the ZDO followup either
        if self._controller_state != ControllerState.Commissioning or self._commissioning_mode == CommissioningMode.Direct:
            return

        hdr, rest = foundation.ZCLHeader.deserialize(packet.data.value)
        if hdr.command_id == GreenPowerProxy.ServerCommandDefs.commissioning_notification.id:
            # here we go
            notif, rest = GreenPowerProxy.GPCommissioningNotificationSchema.deserialize(rest)
            
            if notif.security_failed:
                LOGGER.debug("Unknown device failed security checks: %s", str(notif.gpd_id))
            
            if notif.security_level == GPSecurityLevel.NoSecurity and notif.command_id == GPCommand.Commissioning:
                LOGGER.debug("Received valid GP commissioning packet from %s", str(notif.gpd_id))
                comm_payload, rest = GPCommissioningPayload.deserialize(notif.payload)
                asyncio.ensure_future(
                    self._handle_commissioning_data_frame(notif.gpd_id, comm_payload, True),
                    loop=asyncio.get_running_loop()
                )


    async def _create_device(self, src_id: t.GreenPowerDeviceID, payload: GPCommissioningPayload, sink_table_entry: SinkTableEntry, from_zcl: bool) -> zigpy.device.Device:
        device_type = payload.device_type
        ieee = t.EUI64(bytes([0,0,0,0]) + src_id.serialize())
        device = self._application.add_device(ieee, t.uint16_t(src_id & 0xFFFF))
        device.status = zigpy.device.Status.ENDPOINTS_INIT
        device._skip_configuration = True
        device.node_desc = zdo.types.NodeDescriptor(
            logical_type=zigpy.zdo.types.LogicalType.EndDevice,
            frequency_band=zigpy.zdo.types._NodeDescriptorEnums.FrequencyBand.Freq2400MHz,
            mac_capability_flags=zigpy.zdo.types._NodeDescriptorEnums.MACCapabilityFlags.AllocateAddress,
            manufacturer_code=4174,
            maximum_buffer_size=82,
            maximum_incoming_transfer_size=82,
            server_mask=0,
            maximum_outgoing_transfer_size=82,
            descriptor_capability_field=0,
        )
        ep: zigpy.endpoint.Endpoint = device.add_endpoint(1)
        ep.status = zigpy.endpoint.Status.ZDO_INIT
        ep.profile_id = zigpy.profiles.zha.PROFILE_ID
        ep.device_type = zigpy.profiles.zha.DeviceType.GREEN_POWER
        ep.add_input_cluster(Basic.cluster_id)
        cluster: Cluster = ep.in_clusters[Basic.cluster_id]
        cluster.update_attribute(Basic.AttributeDefs.manufacturer.id, "GreenPower")
        if device_type is not None and device_type in GPEndpointsByDeviceType:
            descriptor = GPEndpointsByDeviceType[device_type]
            ep.in_clusters[Basic.cluster_id].update_attribute(Basic.AttributeDefs.model.id, descriptor.name)
            for cluster in descriptor.in_clusters:
                LOGGER.debug("Add input cluster id %s on device %s", cluster.cluster_id, ieee)
                ep.add_input_cluster(cluster.cluster_id)
            for cluster in descriptor.out_clusters:
                LOGGER.debug("Add output cluster id %s on device %s", cluster.cluster_id, ieee)
                ep.add_output_cluster(cluster.cluster_id)
        else:
            ep.in_clusters[Basic.cluster_id].update_attribute(Basic.AttributeDefs.model.id, "GreenPowerDevice")
        ep = device.add_endpoint(GREENPOWER_ENDPOINT_ID)
        ep.status = zigpy.endpoint.Status.ZDO_INIT
        ep.profile_id = zigpy.profiles.zha.PROFILE_ID
        ep.device_type = zigpy.profiles.zha.DeviceType.GREEN_POWER
        cluster = ep.add_input_cluster(GreenPowerProxy.cluster_id)
        if payload.gpd_key is not None:
            cluster.update_attribute(GreenPowerProxy.AttributeDefs.__internal_gpd_key.id, payload.gpd_key)
        cluster.update_attribute(GreenPowerProxy.AttributeDefs.__internal_gpd_sinktableentry, sink_table_entry)
        cluster.update_attribute(GreenPowerProxy.AttributeDefs.__internal_gpd_id, src_id)
        self._application.device_initialized(device)
        return device


    async def _handle_commissioning_data_frame(self, src_id: t.GreenPowerDeviceID, commission_payload: GPCommissioningPayload, from_zcl: bool) -> bool:
        if self._get_gp_device_with_srcid(src_id) is not None:
            # well this is bad. we have a sink table entry but an incoming commissioning request?
            # do we update the info in here? unregister and re-register?? Figure this out...
            return False

        comm_mode = t.GPCommunicationMode.GroupcastForwardToCommGroup if CommissioningMode.ProxyBroadcast in self._commissioning_mode else t.GPCommunicationMode.UnicastLightweight

        entry = SinkTableEntry(
            options=0,
            gpd_id=src_id,
            device_id=commission_payload.device_type,
            radius=0xFF
        )
        entry.communication_mode = comm_mode
        entry.sequence_number_cap = commission_payload.mac_seq_num_cap
        entry.rx_on_cap = commission_payload.rx_on_cap
        entry.security_use = commission_payload.security_level != GPSecurityLevel.NoSecurity
        if commission_payload.gpd_key is not None:
            encrypted_key = self._encrypt_key(src_id, commission_payload.gpd_key)
        if comm_mode == t.GPCommunicationMode.GroupcastForwardToCommGroup:
            entry.group_list = LVBytes(
                bytearray(GREENPOWER_BROADCAST_GROUP.to_bytes(2, "little")).append((0xFF,0xFF))
            )
        if entry.security_use:
            entry.sec_options = commission_payload.security_level | (commission_payload.key_type << 2)
        if entry.security_use or entry.sequence_number_cap:
            entry.sec_frame_counter = commission_payload.gpd_outgoing_counter
        if commission_payload.gpd_key is not None:
            entry.key = encrypted_key

        device = await self._create_device(src_id, commission_payload, entry, from_zcl)
        await self._push_sink_table()

        if CommissioningMode.ProxyBroadcast in self._commissioning_mode or CommissioningMode.ProxyUnicast in self._commissioning_mode:
            pairing_options = GreenPowerProxy.GPPairingOptions()
            pairing_options.add_sink = 1
            pairing_options.communication_mode = comm_mode
            pairing_options.gpd_mac_seq_num_cap = commission_payload.mac_seq_num_cap
            pairing_options.security_level = commission_payload.security_level
            pairing_options.security_key_type = commission_payload.key_type

            pairing_schema = dict(options=pairing_options)
            if commission_payload.gpd_key is not None:
                pairing_options.security_key_present = 1
                pairing_schema["key"] = encrypted_key

            if CommissioningMode.ProxyUnicast in self._commissioning_mode:
                pairing_schema["sink_IEEE"] = self._application.state.node_info.ieee
                pairing_schema["sink_nwk_addr"] = self._application.state.node_info.nwk
                await self._proxy_unicast_target.endpoints[GREENPOWER_ENDPOINT_ID].out_clusters[GreenPowerProxy.cluster_id].pairing(pairing_schema)
            elif CommissioningMode.ProxyBroadcast in self._commissioning_mode:
                pairing_schema["sink_group"] = GREENPOWER_BROADCAST_GROUP
                await self._zcl_broadcast(GreenPowerProxy.ClientCommandDefs.pairing, pairing_schema)

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
                return
            
            await device.endpoints[zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID].out_clusters[GreenPowerProxy.cluster_id].proxy_commissioning_mode(
                options = GreenPowerProxy.GPProxyCommissioningModeOptions(
                    enter=1,
                    exit_mode=t.GPProxyCommissioningModeExitMode.OnExpireOrExplicitExit
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

    def _encrypt_key(self, gpd_id: t.GreenPowerDeviceID, key: t.KeyData) -> bytes:
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
                    exit_mode=t.GPProxyCommissioningModeExitMode.OnExpireOrExplicitExit
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

    def _get_all_gp_devices(self) -> typing.List[zigpy.device.Device]:
        devices: typing.List[zigpy.device.Device] = []
        for ieee,device in self._application.devices.items():
            try:
                table_entry = device.endpoints[GREENPOWER_ENDPOINT_ID].in_clusters[GreenPowerProxy.cluster_id].get(GreenPowerProxy.AttributeDefs.__internal_gpd_sinktableentry.id, None)
                if table_entry is not None:
                    devices.append(device)
            except (KeyError, AttributeError):
                continue
        return devices
    
    def _get_gp_device_with_srcid(self, src_id: t.GreenPowerDeviceID) -> zigpy.device.Device | None:
        for ieee,device in self._application.devices.items():
            try:
                dev_src_id = device.endpoints[GREENPOWER_ENDPOINT_ID].in_clusters[GreenPowerProxy.cluster_id].get(GreenPowerProxy.AttributeDefs.__internal_gpd_id.id, None)
                if src_id == dev_src_id:
                    return device
            except (KeyError, AttributeError):
                continue
        return None

    def _sink_table_as_bytes(self) -> t.LongOctetString:
        src_bytes = bytearray()
        for device in self._get_all_gp_devices():
            b = device.endpoints[GREENPOWER_ENDPOINT_ID].in_clusters[GreenPowerProxy.cluster_id].get(GreenPowerProxy.AttributeDefs.__internal_gpd_sinktableentry.id, None)
            if b is not None:
                src_bytes.append(b)
        return t.LongOctetString(src_bytes)
    
    async def _push_sink_table(self):
        await self._gp_cluster.write_attributes({
            "sink_table": self._sink_table_as_bytes()
        })


                


