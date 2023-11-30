from __future__ import annotations
import asyncio
import itertools
import typing

import zigpy.device
import zigpy.exceptions
import zigpy.listeners
from zigpy.profiles.zgp import (
    GREENPOWER_ENDPOINT_ID,
    GREENPOWER_CLUSTER_ID,
)
import zigpy.types as t
from zigpy.zcl.clusters.greenpower import GPNotificationSchema, GreenPowerProxy
import zigpy.zcl.foundation as foundation
from zigpy.zgp.foundation import GPDeviceDescriptors
from zigpy.zgp.types import (
    GPCommunicationMode,
    GreenPowerDeviceID,
    GreenPowerDeviceData
)

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication
    from zigpy.zcl.clusters.greenpower import GPNotificationResponseOptions

class StrippedNotifSchema(foundation.CommandSchema):
    gpd_id: GreenPowerDeviceID
    command_id: t.uint8_t

class GreenPowerDevice(zigpy.device.Device):
    @classmethod
    def match(cls, device: typing.Self) -> bool:
        return True
    
    def __init__(self, application: ControllerApplication, data: GreenPowerDeviceData):
        super().__init__(application, data.ieee, data.nwk)
        device_type = data.device_id
        self._green_power_data = data
        self.skip_configuration = True
        self.status = zigpy.device.Status.NEW
        # self.node_desc = zdo.types.NodeDescriptor(2, 64, 128, 4174, 82, 82, 0, 82, 0)
        self.manufacturer = "GreenPower"
        if device_type is not None and device_type in GPDeviceDescriptors:
            self.model = GPDeviceDescriptors[device_type]
        else:
            self.model = "GreenPowerDevice"
        
        ep = self.add_endpoint(zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID)
        ep.status = 1 # XXX: resolve circular imports
        ep.profile_id = zigpy.profiles.zgp.PROFILE_ID
        ep.device_type = zigpy.profiles.zgp.DeviceType.PROXY_BASIC
        
        ep.add_input_cluster(zigpy.profiles.zgp.GREENPOWER_CLUSTER_ID)
        self.status = zigpy.device.Status.ENDPOINTS_INIT

    @property
    def green_power_data(self) -> GreenPowerDeviceData | None:
        return self._green_power_data

    @property
    def gpd_id(self) -> GreenPowerDeviceID:
        return self._green_power_data.gpd_id

    @property
    def is_initialized(self) -> bool:
        # Tx only paths are just done when we get em
        return True 

    @zigpy.util.retryable_request(tries=5, delay=0.5)
    async def _initialize(self) -> None:
        # Rx capable path will involve this bad boy for sure?
        pass

    def packet_received(self, packet: t.ZigbeePacket) -> None:
        assert packet.src_ep == GREENPOWER_ENDPOINT_ID
        assert packet.cluster_id == GREENPOWER_CLUSTER_ID

        # Set radio details that can be read from any type of packet
        self.last_seen = packet.timestamp
        if packet.lqi is not None:
            self.lqi = packet.lqi
        if packet.rssi is not None:
            self.rssi = packet.rssi

        endpoint = self.endpoints[packet.src_ep]
        cluster = endpoint.in_clusters[packet.cluster_id]

        # We don't get ZDO for ZGP devices, assume ZCL
        data = packet.data.serialize()
        try:
            hdr, args = endpoint.deserialize(packet.cluster_id, data)
        except Exception as exc:
            error = zigpy.exceptions.ParsingError()
            error.__cause__ = exc

            self.debug("Failed to parse packet %r", packet, exc_info=error)
        else:
            error = None

        if error is not None:
            return

        # We've gotta convert this to something nice that we can hand to
        # ZGP. TODO: command payloads too, but I don't know if we'll need that at all
        if isinstance(args, GPNotificationSchema):
            asyncio.ensure_future(
                self._send_notif_response_packet(args),
                loop=asyncio.get_running_loop()
            )
            args = StrippedNotifSchema(
                gpd_id=args.gpd_id,
                command_id=args.command_id,
            )

        cluster.handle_message(
            hdr, args, 
            dst_addressing=packet.dst.addr_mode if packet.dst is not None else None
        )
        
        # Pass the request off to a listener, if one is registered
        for listener in itertools.chain(
            self._application._req_listeners[zigpy.listeners.ANY_DEVICE],
            self._application._req_listeners[self],
        ):
            # Resolve only until the first future listener
            if listener.resolve(hdr, args) and isinstance(
                listener, zigpy.listeners.FutureListener
            ):
                break

    async def _send_notif_response_packet(self, notif: GPNotificationSchema):
        if self.green_power_data.communication_mode in (GPCommunicationMode.Unicast, GPCommunicationMode.UnicastLightweight):
            target_device = self.application.get_device(self.green_power_data.unicast_proxy)
            if target_device is not None:
                # send notification response
                endpoint = target_device.endpoints[GREENPOWER_ENDPOINT_ID]
                cluster = endpoint.out_clusters[GREENPOWER_CLUSTER_ID]
                await self._application._greenpower.send_no_response_command(
                    target_device, 
                    GreenPowerProxy.ClientCommandDefs.notification_response, 
                    {
                        "options":cluster.GPNotificationResponseOptions(first_to_forward=1),
                        "gpd_id":self.gpd_id,
                        "frame_counter":notif.frame_counter
                    }
                )
            else:
                self.error("Could not respove unicast proxy device to reply with response; failing!")
