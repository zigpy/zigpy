"""Conversion of ZCL-tunneled Green Power frames into GP packets.

Proxies forward GPDFs they receive to sinks as GP Notification and GP
Commissioning Notification commands of the Green Power cluster (ZGP spec
A.3.3.4.1 and A.3.3.4.3). This module unpacks those tunneled commands back
into `ZigbeeGpPacket`s.
"""

from __future__ import annotations

import zigpy.profiles.zgp
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.greenpower import (
    CommissioningNotificationSchema,
    GreenPowerProxy,
    NotificationSchema,
)
from zigpy.zgp.types import GP_CLUSTER_ID, GP_ENDPOINT

TUNNELED_GPDF_COMMANDS: dict[
    int, type[NotificationSchema | CommissioningNotificationSchema]
] = {
    GreenPowerProxy.ServerCommandDefs.notification.id: NotificationSchema,
    GreenPowerProxy.ServerCommandDefs.commissioning_notification.id: (
        CommissioningNotificationSchema
    ),
}


def is_gp_tunnel_packet(packet: t.ZigbeePacket) -> bool:
    """Check whether a packet is a GPDF tunneled over ZCL by a proxy.

    Only the two notification commands are tunnels. All other Green Power cluster
    traffic (pairing, commissioning mode, attribute reads, ...) is normal ZCL and
    flows through regular device dispatch.
    """
    if not (
        packet.profile_id == zigpy.profiles.zgp.PROFILE_ID
        and packet.cluster_id == GP_CLUSTER_ID
        and packet.src_ep == GP_ENDPOINT
    ):
        return False

    try:
        hdr, _ = foundation.ZCLHeader.deserialize(packet.data.serialize())
    except ValueError:
        return False

    return (
        hdr.frame_control.is_cluster
        and hdr.frame_control.direction == foundation.Direction.Client_to_Server
        and hdr.command_id in TUNNELED_GPDF_COMMANDS
    )


def gp_packet_from_zcl(packet: t.ZigbeePacket) -> t.ZigbeeGpPacket:
    """Convert a ZCL-tunneled GP notification into a `ZigbeeGpPacket`."""
    hdr, data = foundation.ZCLHeader.deserialize(packet.data.serialize())

    if not hdr.frame_control.is_cluster:
        raise ValueError(f"Not a cluster-specific command: {hdr}")

    # The notification and notification response commands share a command ID and
    # are only distinguished by direction
    if hdr.frame_control.direction != foundation.Direction.Client_to_Server:
        raise ValueError(f"Not a client-to-server command: {hdr}")

    if hdr.command_id not in TUNNELED_GPDF_COMMANDS:
        raise ValueError(f"Not a tunneled GPDF command: {hdr}")

    command, rest = TUNNELED_GPDF_COMMANDS[hdr.command_id].deserialize(data)

    if rest:
        raise ValueError(f"Trailing data in tunneled GPDF: {rest!r}")

    if (
        isinstance(command, CommissioningNotificationSchema)
        and command.options.security_failed
    ):
        raise ValueError(f"Security processing of the tunneled GPDF failed: {command}")

    lqi = rssi = None

    if command.options.proxy_info_present:
        # Spread the proxy's 2-bit link quality over the full 0-255 LQI range
        lqi = t.uint8_t(int(command.gpp_gpd_link.link_quality) * 85)
        rssi = t.int8s(command.gpp_gpd_link.rssi_dbm)

    # A Green Power 1.0 proxy sends a `Distance` byte instead of the GPP-GPD link.
    # How to interpret it is explicitly application-specific, so it is dropped.

    return t.ZigbeeGpPacket(
        timestamp=packet.timestamp,
        application_id=command.options.application_id,
        src_id=command.gpd_id,
        ieee=command.gpd_ieee,
        endpoint=command.gpd_endpoint,
        command_id=command.command_id,
        payload=t.SerializableBytes(bytes(command.payload)),
        frame_counter=command.frame_counter,
        security_level=command.options.security_level,
        security_key_type=command.options.security_key_type,
        lqi=lqi,
        rssi=rssi,
    )
