from __future__ import annotations

import itertools
import logging
import typing

import zigpy.device
import zigpy.exceptions
import zigpy.listeners
import zigpy.profiles.zgp
from zigpy.profiles.zgp import GREENPOWER_CLUSTER_ID, GREENPOWER_ENDPOINT_ID
import zigpy.types as t
from zigpy.zcl.clusters.greenpower import GPNotificationSchema, GreenPowerProxy
import zigpy.zcl.foundation as foundation
from zigpy.zgp.foundation import GPCommand, GPDeviceDescriptors
from zigpy.zgp.types import (
    GPAttributeReportingPayload,
    GPCommunicationMode,
    GreenPowerDeviceData,
    GreenPowerDeviceID,
)

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

LOGGER = logging.getLogger(__name__)


class StrippedNotifSchema(foundation.CommandSchema):
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
        ep.status = 1  # XXX: resolve circular imports
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
        """We assume the green power controller has done our accounting for us"""
        return GREENPOWER_ENDPOINT_ID in self.endpoints

    @zigpy.util.retryable_request(tries=5, delay=0.5)
    async def _initialize(self) -> None:
        """Expand this to build clusters if provided in commissioning notification"""

    def packet_received(self, packet: t.ZigbeePacket) -> None:
        if packet.src_ep != GREENPOWER_ENDPOINT_ID:
            LOGGER.warn(
                "Not GP endpoint message sent to %s:%d; why?",
                self.green_power_data.gpd_id._hex_repr(),
                packet.src_ep,
            )
            return
        # assert packet.src_ep == GREENPOWER_ENDPOINT_ID
        if packet.cluster_id != GREENPOWER_CLUSTER_ID:
            LOGGER.warn(
                "Not GP cluster message sent to %s:%d; why?",
                self.green_power_data.gpd_id._hex_repr(),
                packet.cluster_id,
            )
            return

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

        if isinstance(args, GPNotificationSchema):
            if args.command_id == GPCommand.AttributeReporting:
                attrs, _ = GPAttributeReportingPayload.deserialize(args.payload)
                # we need EP1 for attr reporting, should be added in Quirks
                ep = self.endpoints[1]
                cluster = ep.in_clusters[attrs.cluster_id]
                for report in attrs.reports:
                    LOGGER.debug(
                        "Updating %s attr %s:%s with value %s",
                        self.gpd_id,
                        attrs.cluster_id._hex_repr(),
                        report.attribute_id._hex_repr(),
                        str(report.data),
                    )
                    cluster.update_attribute(
                        attrid=report.attribute_id,
                        value=report.data,
                    )
                # XXX: not sure about this, but I think this is right; I don't think
                # we should be propagating the attr updates all the way to ZHA, that
                # should happen at some other layer, right?
                return
            elif args.command_id == GPCommand.ManufacturerSpecificReporting:
                LOGGER.debug("GP Device skipping manu. specific attr reporting!")
                return

            # We've gotta convert this to something nice that we can hand to
            # ZHA, otherwise it'll get mad about LVBytes.
            # TODO: command payloads too, but I don't know if we'll need that at all
            args = StrippedNotifSchema(
                command_id=args.command_id,
            )

        cluster.handle_message(
            hdr,
            args,
            dst_addressing=packet.dst.addr_mode if packet.dst is not None else None,
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

    # Nobody seems to support notify response, tho the spec calls for it.
    # For future reference: this should happen on unicast comm mode notifs
    async def _send_notif_response_packet(self, notif: GPNotificationSchema):
        if self.green_power_data.communication_mode in (
            GPCommunicationMode.Unicast,
            GPCommunicationMode.UnicastLightweight,
        ):
            target_device = self.application.get_device(
                self.green_power_data.unicast_proxy
            )
            if target_device is not None:
                # send notification response
                endpoint = target_device.endpoints[GREENPOWER_ENDPOINT_ID]
                cluster = endpoint.out_clusters[GREENPOWER_CLUSTER_ID]
                await self._application._greenpower.send_no_response_command(
                    target_device,
                    GreenPowerProxy.ClientCommandDefs.notification_response,
                    {
                        "options": cluster.GPNotificationResponseOptions(
                            first_to_forward=1
                        ),
                        "gpd_id": self.gpd_id,
                        "frame_counter": notif.frame_counter,
                    },
                )
            else:
                self.error(
                    "Could not respove unicast proxy device to reply with response; failing!"
                )
