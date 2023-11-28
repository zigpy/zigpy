from __future__ import annotations
import itertools
import typing

import zigpy.device
import zigpy.exceptions
import zigpy.listeners
import zigpy.profiles.zgp
import zigpy.types as t
from zigpy.zcl.clusters.greenpower import GPNotificationSchema
import zigpy.zcl.foundation as foundation
from zigpy.zgp.foundation import GPDeviceDescriptors
from zigpy.zgp.types import (
    GreenPowerDeviceID,
    GreenPowerExtData
)

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

class GreenPowerDevice(zigpy.device.Device):
    @classmethod
    def match(cls, device: typing.Self) -> bool:
        return True
    
    def __init__(self, application: ControllerApplication, ext: GreenPowerExtData):
        super().__init__(application, ext.ieee, ext.nwk)
        device_type = ext.device_id
        self._gp_ext = ext
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
        
        ep.add_output_cluster(zigpy.profiles.zgp.GREENPOWER_CLUSTER_ID)
        self.status = zigpy.device.Status.ENDPOINTS_INIT

    @property
    def ext_data(self) -> GreenPowerExtData:
        return self._gp_ext

    @property
    def gpd_id(self) -> GreenPowerDeviceID:
        return self._gp_ext.gpd_id    

    @property
    def is_green_power_device(self) -> bool:
        return True

    @property
    def is_initialized(self) -> bool:
        # Tx only paths are just done when we get em
        return True 

    @zigpy.util.retryable_request(tries=5, delay=0.5)
    async def _initialize(self) -> None:
        # Rx capable path will involve this bad boy for sure?
        pass

    def handle_notification(self, notification: GPNotificationSchema):
        
        pass

    def packet_received(self, packet: t.ZigbeePacket) -> None:
        assert packet.src_ep == zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID
        assert packet.cluster_id == zigpy.profiles.zgp.GREENPOWER_CLUSTER_ID

        # Set radio details that can be read from any type of packet
        self.last_seen = packet.timestamp
        if packet.lqi is not None:
            self.lqi = packet.lqi
        if packet.rssi is not None:
            self.rssi = packet.rssi

        # We don't get ZDO for ZGP devices, assume ZCL
        endpoint = self.endpoints[packet.src_ep]
        data = packet.data.serialize()
        hdr, _ = foundation.ZCLHeader.deserialize(data)

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

        if hdr.command_id == 0x00 and packet.src_ep == zigpy.profiles.zgp.GREENPOWER_ENDPOINT_ID:
            notif: GPNotificationSchema = args
            self.handle_notification(notif)
            if notif.distance is not None:
                # at some point do we want to use this as rssi instead?
                pass
            

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