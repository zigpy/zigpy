"""Works With All Hubs"""

from __future__ import annotations

from typing import Final

import zigpy.types as t
from zigpy.zcl import Cluster
from zigpy.zcl.foundation import (
    ZCL_CLUSTER_REVISION_ATTR,
    ZCL_REPORTING_STATUS_ATTR,
    BaseAttributeDefs,
    BaseCommandDefs,
    Status,
    ZCLAttributeDef,
    ZCLCommandDef,
)


class WwahIasZoneEnrollmentMode(t.enum8):
    """IAS Zone Enrollment Mode."""

    TripToPair = 0x00
    AutoEnrollmentResponse = 0x01
    Request = 0x02


class WwahPowerNotificationReason(t.enum8):
    """Power Notification Reason."""

    Unknown = 0x00
    Battery = 0x01
    Brownout = 0x02
    Watchdog = 0x03
    ResetPin = 0x04
    MemoryHardwareFault = 0x05
    SoftwareException = 0x06  # Spelled `SofwareException` in the SDK
    OtaBootloadSuccess = 0x07
    SoftwareReset = 0x08
    PowerButton = 0x09
    Temperature = 0x0A
    BootloadFailure = 0x0B


class WwahBeaconSurvey(t.Struct):
    """WWAH Beacon Survey structure."""

    device_short: t.uint16_t
    rssi: t.uint8_t
    classification_mask: t.uint8_t


class WwahClusterStatusToUseTC(t.Struct):
    """WWAH Cluster Status to Use TC structure."""

    cluster_id: t.ClusterId
    status: Status


# This cluster uses the Amazon manufacturer code for all commands and attributes
class WorksWithAllHubs(Cluster):
    """Works With All Hubs cluster"""

    cluster_id: Final[t.uint16_t] = 0xFC57
    ep_attribute: Final = "works_with_all_hubs"

    class AttributeDefs(BaseAttributeDefs):
        # 0x0000 and 0x0001 were removed from the spec
        disable_ota_downgrades: Final = ZCLAttributeDef(
            id=0x0002,
            type=t.Bool,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        mgmt_leave_without_rejoin_enabled: Final = ZCLAttributeDef(
            id=0x0003,
            type=t.Bool,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        nwk_retry_count: Final = ZCLAttributeDef(
            id=0x0004,
            type=t.uint8_t,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        mac_retry_count: Final = ZCLAttributeDef(
            id=0x0005,
            type=t.uint8_t,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        router_checkin_enabled: Final = ZCLAttributeDef(
            id=0x0006,
            type=t.Bool,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        touchlink_interpan_enabled: Final = ZCLAttributeDef(
            id=0x0007,
            type=t.Bool,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        wwah_parent_classification_enabled: Final = ZCLAttributeDef(
            id=0x0008,
            type=t.Bool,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        wwah_app_event_retry_enabled: Final = ZCLAttributeDef(
            id=0x0009,
            type=t.Bool,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        wwah_app_event_retry_queue_size: Final = ZCLAttributeDef(
            id=0x000A,
            type=t.uint8_t,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        wwah_rejoin_enabled: Final = ZCLAttributeDef(
            id=0x000B,
            type=t.Bool,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        mac_poll_failure_wait_time: Final = ZCLAttributeDef(
            id=0x000C,
            type=t.uint8_t,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        configuration_mode_enabled: Final = ZCLAttributeDef(
            id=0x000D,
            type=t.Bool,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        current_debug_report_id: Final = ZCLAttributeDef(
            id=0x000E,
            type=t.uint8_t,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        tc_security_on_ntwk_key_rotation_enabled: Final = ZCLAttributeDef(
            id=0x000F,
            type=t.Bool,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        wwah_bad_parent_recovery_enabled: Final = ZCLAttributeDef(
            id=0x0010,
            type=t.Bool,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        pending_network_update_channel: Final = ZCLAttributeDef(
            id=0x0011,
            type=t.uint8_t,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        pending_network_update_panid: Final = ZCLAttributeDef(
            id=0x0012,
            type=t.PanId,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        ota_max_offline_duration: Final = ZCLAttributeDef(
            id=0x0013,
            type=t.uint16_t,
            access="r",
            mandatory=False,
            manufacturer_code=0x1217,
        )
        cluster_revision: Final = ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        # Client-to-Server commands (sent by client, received by server)
        # Enable enforcement of APS-level security for all cluster commands.
        enable_aps_link_key_authorization: Final = ZCLCommandDef(
            id=0x00,
            schema={"cluster_id": t.LVList[t.ClusterId, t.uint8_t]},
            manufacturer_code=0x1217,
        )

        # Disable enforcement of APS-level security for all cluster commands.
        disable_aps_link_key_authorization: Final = ZCLCommandDef(
            id=0x01,
            schema={"cluster_id": t.LVList[t.ClusterId, t.uint8_t]},
            manufacturer_code=0x1217,
        )

        # Query status of APS-level security enforcement for a specified cluster.
        aps_link_key_authorization_query: Final = ZCLCommandDef(
            id=0x02,
            schema={"cluster_id": t.ClusterId},
            manufacturer_code=0x1217,
        )

        # Trigger device to request a new APS link key from the Trust Center.
        request_new_aps_link_key: Final = ZCLCommandDef(
            id=0x03,
            schema={},
            manufacturer_code=0x1217,
        )

        enable_wwah_app_event_retry_algorithm: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "first_backoff_time_seconds": t.uint8_t,
                "backoff_seq_common_ratio": t.uint8_t,
                "max_backoff_time_seconds": t.uint32_t,
                "max_redelivery_attempts": t.uint8_t,
            },
            manufacturer_code=0x1217,
        )

        disable_wwah_app_event_retry_algorithm: Final = ZCLCommandDef(
            id=0x05,
            schema={},
            manufacturer_code=0x1217,
        )

        # Trigger device to request current attribute values from Time Cluster server.
        request_time: Final = ZCLCommandDef(
            id=0x06,
            schema={},
            manufacturer_code=0x1217,
        )

        enable_wwah_rejoin_algorithm: Final = ZCLCommandDef(
            id=0x07,
            schema={
                "fast_rejoin_timeout_seconds": t.uint16_t,
                "duration_between_rejoins_seconds": t.uint16_t,
                "fast_rejoin_first_backoff_seconds": t.uint16_t,
                "max_backoff_time_seconds": t.uint16_t,
                "max_backoff_iterations": t.uint16_t,
            },
            manufacturer_code=0x1217,
        )

        disable_wwah_rejoin_algorithm: Final = ZCLCommandDef(
            id=0x08,
            schema={},
            manufacturer_code=0x1217,
        )

        # Set the enrollment method of an IAS Zone server.
        set_ias_zone_enrollment_method: Final = ZCLCommandDef(
            id=0x09,
            schema={"enrollment_mode": WwahIasZoneEnrollmentMode},
            manufacturer_code=0x1217,
        )

        clear_binding_table: Final = ZCLCommandDef(
            id=0x0A,
            schema={},
            manufacturer_code=0x1217,
        )

        # Enable device to periodically check connectivity with Zigbee Coordinator.
        enable_periodic_router_check_ins: Final = ZCLCommandDef(
            id=0x0B,
            schema={"check_in_interval": t.uint16_t},
            manufacturer_code=0x1217,
        )

        # Disable device from periodically checking connectivity with Zigbee Coordinator.
        disable_periodic_router_check_ins: Final = ZCLCommandDef(
            id=0x0C,
            schema={},
            manufacturer_code=0x1217,
        )

        set_mac_poll_failure_wait_time: Final = ZCLCommandDef(
            id=0x0D,
            schema={"wait_time": t.uint8_t},
            manufacturer_code=0x1217,
        )

        # Set pending network update parameters.
        set_pending_network_update: Final = ZCLCommandDef(
            id=0x0E,
            schema={"channel": t.uint8_t, "pan_id": t.PanId},
            manufacturer_code=0x1217,
        )

        # Require all unicast commands to have APS ACKs enabled.
        require_aps_acks_on_unicasts: Final = ZCLCommandDef(
            id=0x0F,
            schema={"cluster_id": t.LVList[t.ClusterId, t.uint8_t]},
            manufacturer_code=0x1217,
        )

        # Roll back changes made by Require APS ACK on Unicasts.
        remove_aps_acks_on_unicasts_requirement: Final = ZCLCommandDef(
            id=0x10,
            schema={},
            manufacturer_code=0x1217,
        )

        # Query whether unicast commands are required to have APS ACKs enabled.
        aps_ack_requirement_query: Final = ZCLCommandDef(
            id=0x11,
            schema={},
            manufacturer_code=0x1217,
        )

        debug_report_query: Final = ZCLCommandDef(
            id=0x12,
            schema={"debug_report_id": t.uint8_t},
            manufacturer_code=0x1217,
        )

        # Causes device to perform a scan for beacons advertising the device's network.
        survey_beacons: Final = ZCLCommandDef(
            id=0x13,
            schema={"standard_beacons": t.Bool},
            manufacturer_code=0x1217,
        )

        # Disallow OTA downgrade of all device firmware components.
        disable_ota_downgrades: Final = ZCLCommandDef(
            id=0x14,
            schema={},
            manufacturer_code=0x1217,
        )

        # Causes device to ignore MGMT Leave Without Rejoin commands.
        disable_mgmt_leave_without_rejoin: Final = ZCLCommandDef(
            id=0x15,
            schema={},
            manufacturer_code=0x1217,
        )

        # Causes device to ignore Touchlink Interpan messages.
        disable_touchlink_interpan_message_support: Final = ZCLCommandDef(
            id=0x16,
            schema={},
            manufacturer_code=0x1217,
        )

        enable_wwah_parent_classification: Final = ZCLCommandDef(
            id=0x17,
            schema={},
            manufacturer_code=0x1217,
        )

        disable_wwah_parent_classification: Final = ZCLCommandDef(
            id=0x18,
            schema={},
            manufacturer_code=0x1217,
        )

        # Process only network key rotation commands sent via unicast and encrypted by Trust Center Link Key.
        enable_tc_security_on_ntwk_key_rotation: Final = ZCLCommandDef(
            id=0x19,
            schema={},
            manufacturer_code=0x1217,
        )

        enable_wwah_bad_parent_recovery: Final = ZCLCommandDef(
            id=0x1A,
            schema={},
            manufacturer_code=0x1217,
        )

        disable_wwah_bad_parent_recovery: Final = ZCLCommandDef(
            id=0x1B,
            schema={},
            manufacturer_code=0x1217,
        )

        enable_configuration_mode: Final = ZCLCommandDef(
            id=0x1C,
            schema={},
            manufacturer_code=0x1217,
        )

        disable_configuration_mode: Final = ZCLCommandDef(
            id=0x1D,
            schema={},
            manufacturer_code=0x1217,
        )

        # Use only the Trust Center as cluster server for the set of clusters specified.
        use_trust_center_for_cluster_server: Final = ZCLCommandDef(
            id=0x1E,
            schema={"cluster_id": t.LVList[t.ClusterId, t.uint8_t]},
            manufacturer_code=0x1217,
        )

        # Causes device to send an appropriate Trust Center for Cluster Server Query Response command.
        trust_center_for_cluster_server_query: Final = ZCLCommandDef(
            id=0x1F,
            schema={},
            manufacturer_code=0x1217,
        )

    class ClientCommandDefs(BaseCommandDefs):
        aps_link_key_authorization_query_response: Final = ZCLCommandDef(
            id=0x00,
            schema={"cluster_id": t.ClusterId, "aps_link_key_auth_status": t.Bool},
            manufacturer_code=0x1217,
        )

        powering_off_notification: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "power_notification_reason": WwahPowerNotificationReason,
                "manufacturer_id": t.uint16_t,
                "manufacturer_reason": t.LVList[t.uint8_t, t.uint8_t],
            },
            manufacturer_code=0x1217,
        )

        powering_on_notification: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "power_notification_reason": WwahPowerNotificationReason,
                "manufacturer_id": t.uint16_t,
                "manufacturer_reason": t.LVList[t.uint8_t, t.uint8_t],
            },
            manufacturer_code=0x1217,
        )

        short_address_change: Final = ZCLCommandDef(
            id=0x03,
            schema={"device_eui64": t.EUI64, "device_short": t.uint16_t},
            manufacturer_code=0x1217,
        )

        aps_ack_enablement_query_response: Final = ZCLCommandDef(
            id=0x04,
            schema={"cluster_id": t.LVList[t.ClusterId, t.uint8_t]},
            manufacturer_code=0x1217,
        )

        power_descriptor_change: Final = ZCLCommandDef(
            id=0x05,
            schema={
                "current_power_mode": t.uint32_t,
                "available_power_sources": t.uint32_t,
                "current_power_source": t.uint32_t,
                "current_power_source_level": t.uint32_t,
            },
            manufacturer_code=0x1217,
        )

        new_debug_report_notification: Final = ZCLCommandDef(
            id=0x06,
            schema={"debug_report_id": t.uint8_t, "debug_report_size": t.uint32_t},
            manufacturer_code=0x1217,
        )

        debug_report_query_response: Final = ZCLCommandDef(
            id=0x07,
            schema={
                "debug_report_id": t.uint8_t,
                "debug_report_data": t.LVList[t.uint8_t, t.uint8_t],
            },
            manufacturer_code=0x1217,
        )

        trust_center_for_cluster_server_query_response: Final = ZCLCommandDef(
            id=0x08,
            schema={"cluster_id": t.LVList[t.ClusterId, t.uint8_t]},
            manufacturer_code=0x1217,
        )

        survey_beacons_response: Final = ZCLCommandDef(
            id=0x09,
            schema={"beacon": t.LVList[WwahBeaconSurvey, t.uint8_t]},
            manufacturer_code=0x1217,
        )

        # Whether this command exists on real devices or not is uncertain, the Silicon
        # Labs SDK XML made it sound like it was either not yet added or is being
        # removed
        use_trust_center_for_cluster_server_response: Final = ZCLCommandDef(
            id=0x9E,
            schema={
                "status": Status,
                "cluster_status": t.LVList[WwahClusterStatusToUseTC, t.uint8_t],
            },
            manufacturer_code=0x1217,
        )
