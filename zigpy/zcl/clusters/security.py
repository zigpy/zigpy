"""Security and Safety Functional Domain"""

from __future__ import annotations

from typing import Any, Final

import zigpy.types as t
from zigpy.typing import AddressingMode
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import (
    BaseAttributeDefs,
    BaseCommandDefs,
    Direction,
    ZCLAttributeDef,
    ZCLCommandDef,
)


class ZoneState(t.enum8):
    Not_enrolled = 0x00
    Enrolled = 0x01


class ZoneType(t.enum_factory(t.uint16_t, "manufacturer_specific")):
    """Zone type enum."""

    Standard_CIE = 0x0000
    Motion_Sensor = 0x000D
    Contact_Switch = 0x0015
    Fire_Sensor = 0x0028
    Water_Sensor = 0x002A
    Carbon_Monoxide_Sensor = 0x002B
    Personal_Emergency_Device = 0x002C
    Vibration_Movement_Sensor = 0x002D
    Remote_Control = 0x010F
    Key_Fob = 0x0115
    Key_Pad = 0x021D
    Standard_Warning_Device = 0x0225
    Glass_Break_Sensor = 0x0226
    Security_Repeater = 0x0229
    Invalid_Zone_Type = 0xFFFF


class ZoneStatus(t.bitmap16):
    """ZoneStatus attribute."""

    Alarm_1 = 0x0001
    Alarm_2 = 0x0002
    Tamper = 0x0004
    Battery = 0x0008
    Supervision_reports = 0x0010
    Restore_reports = 0x0020
    Trouble = 0x0040
    AC_mains = 0x0080
    Test = 0x0100
    Battery_Defect = 0x0200


class EnrollResponse(t.enum8):
    """Enroll response code."""

    Success = 0x00
    Not_supported = 0x01
    No_enroll_permit = 0x02
    Too_many_zones = 0x03


class IasZone(Cluster):
    """The IAS Zone cluster defines an interface to the functionality of an IAS
    security zone device. IAS Zone supports up to two alarm types per zone, low battery
    reports and supervision of the IAS network.
    """

    ZoneState: Final = ZoneState
    ZoneType: Final = ZoneType
    ZoneStatus: Final = ZoneStatus
    EnrollResponse: Final = EnrollResponse

    cluster_id: Final[t.uint16_t] = 0x0500
    name: Final = "IAS Zone"
    ep_attribute: Final = "ias_zone"

    class AttributeDefs(BaseAttributeDefs):
        # Zone Information
        zone_state: Final = ZCLAttributeDef(
            id=0x0000, type=ZoneState, access="r", mandatory=True
        )
        zone_type: Final = ZCLAttributeDef(
            id=0x0001, type=ZoneType, access="r", mandatory=True
        )
        zone_status: Final = ZCLAttributeDef(
            id=0x0002, type=ZoneStatus, access="r", mandatory=True
        )
        # Zone Settings
        cie_addr: Final = ZCLAttributeDef(
            id=0x0010, type=t.EUI64, access="rw", mandatory=True
        )
        zone_id: Final = ZCLAttributeDef(
            id=0x0011, type=t.uint8_t, access="r", mandatory=True
        )
        # Both attributes will be supported/unsupported
        num_zone_sensitivity_levels_supported: Final = ZCLAttributeDef(
            id=0x0012, type=t.uint8_t, access="r"
        )
        current_zone_sensitivity_level: Final = ZCLAttributeDef(
            id=0x0013, type=t.uint8_t, access="rw"
        )

    class ServerCommandDefs(BaseCommandDefs):
        enroll_response: Final = ZCLCommandDef(
            id=0x00,
            schema={"enroll_response_code": EnrollResponse, "zone_id": t.uint8_t},
            direction=Direction.Server_to_Client,
        )
        init_normal_op_mode: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )
        init_test_mode: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "test_mode_duration": t.uint8_t,
                "current_zone_sensitivity_level": t.uint8_t,
            },
            direction=Direction.Client_to_Server,
        )

    class ClientCommandDefs(BaseCommandDefs):
        status_change_notification: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "zone_status": ZoneStatus,
                "extended_status": t.bitmap8,
                "zone_id": t.uint8_t,
                "delay": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )
        enroll: Final = ZCLCommandDef(
            id=0x01,
            schema={"zone_type": ZoneType, "manufacturer_code": t.uint16_t},
            direction=Direction.Client_to_Server,
        )

    def handle_cluster_request(
        self,
        hdr: foundation.ZCLHeader,
        args: list[Any],
        *,
        dst_addressing: AddressingMode | None = None,
    ):
        if (
            hdr.command_id == self.commands_by_name["enroll_response"].id
            and self.is_server
            and not hdr.frame_control.disable_default_response
        ):
            hdr.frame_control.is_reply = False  # this is a client -> server cmd
            self.send_default_rsp(hdr, foundation.Status.SUCCESS)


class AlarmStatus(t.enum8):
    """IAS ACE alarm status enum."""

    No_Alarm = 0x00
    Burglar = 0x01
    Fire = 0x02
    Emergency = 0x03
    Police_Panic = 0x04
    Fire_Panic = 0x05
    Emergency_Panic = 0x06


class ArmMode(t.enum8):
    """IAS ACE arm mode enum."""

    Disarm = 0x00
    Arm_Day_Home_Only = 0x01
    Arm_Night_Sleep_Only = 0x02
    Arm_All_Zones = 0x03


class ArmNotification(t.enum8):
    """IAS ACE arm notification enum."""

    All_Zones_Disarmed = 0x00
    Only_Day_Home_Zones_Armed = 0x01
    Only_Night_Sleep_Zones_Armed = 0x02
    All_Zones_Armed = 0x03
    Invalid_Arm_Disarm_Code = 0x04
    Not_Ready_To_Arm = 0x05
    Already_Disarmed = 0x06


class AudibleNotification(t.enum_factory(t.uint8_t, "manufacturer_specific")):
    """IAS ACE audible notification enum."""

    Mute = 0x00
    Default_Sound = 0x01


class BypassResponse(t.enum8):
    """Bypass result."""

    Zone_bypassed = 0x00
    Zone_not_bypassed = 0x01
    Not_allowed = 0x02
    Invalid_Zone_ID = 0x03
    Unknown_Zone_ID = 0x04
    Invalid_Code = 0x05


class PanelStatus(t.enum8):
    """IAS ACE panel status enum."""

    Panel_Disarmed = 0x00
    Armed_Stay = 0x01
    Armed_Night = 0x02
    Armed_Away = 0x03
    Exit_Delay = 0x04
    Entry_Delay = 0x05
    Not_Ready_To_Arm = 0x06
    In_Alarm = 0x07
    Arming_Stay = 0x08
    Arming_Night = 0x09
    Arming_Away = 0x0A


class ZoneStatusRsp(t.Struct):
    """Zone status response."""

    zone_id: t.uint8_t
    zone_status: IasZone.ZoneStatus


class IasAce(Cluster):
    """IAS Ancillary Control Equipment cluster."""

    AlarmStatus: Final = AlarmStatus
    ArmMode: Final = ArmMode
    ArmNotification: Final = ArmNotification
    AudibleNotification: Final = AudibleNotification
    BypassResponse: Final = BypassResponse
    PanelStatus: Final = PanelStatus
    ZoneType: Final = IasZone.ZoneType
    ZoneStatus: Final = IasZone.ZoneStatus
    ZoneStatusRsp: Final = ZoneStatusRsp

    cluster_id: Final[t.uint16_t] = 0x0501
    name: Final = "IAS Ancillary Control Equipment"
    ep_attribute: Final = "ias_ace"

    class AttributeDefs(BaseAttributeDefs):
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        arm: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "arm_mode": ArmMode,
                "arm_disarm_code": t.CharacterString,
                "zone_id": t.uint8_t,
            },
            direction=Direction.Client_to_Server,
        )
        bypass: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "zones_ids": t.LVList[t.uint8_t],
                "arm_disarm_code": t.CharacterString,
            },
            direction=Direction.Client_to_Server,
        )
        emergency: Final = ZCLCommandDef(
            id=0x02, schema={}, direction=Direction.Client_to_Server
        )
        fire: Final = ZCLCommandDef(
            id=0x03, schema={}, direction=Direction.Client_to_Server
        )
        panic: Final = ZCLCommandDef(
            id=0x04, schema={}, direction=Direction.Client_to_Server
        )
        get_zone_id_map: Final = ZCLCommandDef(
            id=0x05, schema={}, direction=Direction.Client_to_Server
        )
        get_zone_info: Final = ZCLCommandDef(
            id=0x06, schema={"zone_id": t.uint8_t}, direction=Direction.Client_to_Server
        )
        get_panel_status: Final = ZCLCommandDef(
            id=0x07, schema={}, direction=Direction.Client_to_Server
        )
        get_bypassed_zone_list: Final = ZCLCommandDef(
            id=0x08, schema={}, direction=Direction.Client_to_Server
        )
        get_zone_status: Final = ZCLCommandDef(
            id=0x09,
            schema={
                "starting_zone_id": t.uint8_t,
                "max_num_zone_ids": t.uint8_t,
                "zone_status_mask_flag": t.Bool,
                "zone_status_mask": ZoneStatus,
            },
            direction=Direction.Client_to_Server,
        )

    class ClientCommandDefs(BaseCommandDefs):
        arm_response: Final = ZCLCommandDef(
            id=0x00,
            schema={"arm_notification": ArmNotification},
            direction=Direction.Server_to_Client,
        )
        get_zone_id_map_response: Final = ZCLCommandDef(
            id=0x01,
            schema={"zone_id_map_sections": t.List[t.bitmap16]},
            direction=Direction.Server_to_Client,
        )
        get_zone_info_response: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "zone_id": t.uint8_t,
                "zone_type": ZoneType,
                "ieee": t.EUI64,
                "zone_label": t.CharacterString,
            },
            direction=Direction.Server_to_Client,
        )
        zone_status_changed: Final = ZCLCommandDef(
            id=0x03,
            schema={
                "zone_id": t.uint8_t,
                "zone_status": ZoneStatus,
                "audible_notification": AudibleNotification,
                "zone_label": t.CharacterString,
            },
            direction=Direction.Client_to_Server,
        )
        panel_status_changed: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "panel_status": PanelStatus,
                "seconds_remaining": t.uint8_t,
                "audible_notification": AudibleNotification,
                "alarm_status": AlarmStatus,
            },
            direction=Direction.Client_to_Server,
        )
        panel_status_response: Final = ZCLCommandDef(
            id=0x05,
            schema={
                "panel_status": PanelStatus,
                "seconds_remaining": t.uint8_t,
                "audible_notification": AudibleNotification,
                "alarm_status": AlarmStatus,
            },
            direction=Direction.Server_to_Client,
        )
        set_bypassed_zone_list: Final = ZCLCommandDef(
            id=0x06,
            schema={"zone_ids": t.LVList[t.uint8_t]},
            direction=Direction.Client_to_Server,
        )
        bypass_response: Final = ZCLCommandDef(
            id=0x07,
            schema={"bypass_results": t.LVList[BypassResponse]},
            direction=Direction.Server_to_Client,
        )
        get_zone_status_response: Final = ZCLCommandDef(
            id=0x08,
            schema={
                "zone_status_complete": t.Bool,
                "zone_statuses": t.LVList[ZoneStatusRsp],
            },
            direction=Direction.Server_to_Client,
        )


class Strobe(t.enum8):
    No_strobe = 0x00
    Strobe = 0x01


class _SquawkOrWarningCommand:
    def __init__(self, value: int = 0) -> None:
        self.value = t.uint8_t(value)

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[_SquawkOrWarningCommand, bytes]:
        val, data = t.uint8_t.deserialize(data)
        return cls(val), data

    def serialize(self) -> bytes:
        return t.uint8_t(self.value).serialize()

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}.mode={self.mode.name} "
            f"strobe={self.strobe.name} level={self.level.name}: "
            f"{self.value}>"
        )

    def __eq__(self, other):
        """Compare to int."""
        return self.value == other


class StrobeLevel(t.enum8):
    Low_level_strobe = 0x00
    Medium_level_strobe = 0x01
    High_level_strobe = 0x02
    Very_high_level_strobe = 0x03


class WarningType(_SquawkOrWarningCommand):
    Strobe = Strobe

    class SirenLevel(t.enum8):
        Low_level_sound = 0x00
        Medium_level_sound = 0x01
        High_level_sound = 0x02
        Very_high_level_sound = 0x03

    class WarningMode(t.enum8):
        Stop = 0x00
        Burglar = 0x01
        Fire = 0x02
        Emergency = 0x03
        Police_Panic = 0x04
        Fire_Panic = 0x05
        Emergency_Panic = 0x06

    @property
    def mode(self) -> WarningMode:
        return self.WarningMode((self.value >> 4) & 0x0F)

    @mode.setter
    def mode(self, mode: WarningMode) -> None:
        self.value = (self.value & 0xF) | (mode << 4)

    @property
    def strobe(self) -> Strobe:
        return self.Strobe((self.value >> 2) & 0x01)

    @strobe.setter
    def strobe(self, strobe: Strobe) -> None:
        self.value = (self.value & 0xF7) | (
            (strobe & 0x01) << 2  # type:ignore[operator]
        )

    @property
    def level(self) -> SirenLevel:
        return self.SirenLevel(self.value & 0x03)

    @level.setter
    def level(self, level: SirenLevel) -> None:
        self.value = (self.value & 0xFC) | (level & 0x03)


class Squawk(_SquawkOrWarningCommand):
    Strobe = Strobe

    class SquawkLevel(t.enum8):
        Low_level_sound = 0x00
        Medium_level_sound = 0x01
        High_level_sound = 0x02
        Very_high_level_sound = 0x03

    class SquawkMode(t.enum8):
        Armed = 0x00
        Disarmed = 0x01

    @property
    def mode(self) -> SquawkMode:
        return self.SquawkMode((self.value >> 4) & 0x0F)

    @mode.setter
    def mode(self, mode: SquawkMode) -> None:
        self.value = (self.value & 0xF) | ((mode & 0x0F) << 4)

    @property
    def strobe(self) -> Strobe:
        return self.Strobe((self.value >> 3) & 0x01)

    @strobe.setter
    def strobe(self, strobe: Strobe) -> None:
        self.value = (self.value & 0xF7) | (strobe << 3)  # type:ignore[operator]

    @property
    def level(self) -> SquawkLevel:
        return self.SquawkLevel(self.value & 0x03)

    @level.setter
    def level(self, level: SquawkLevel) -> None:
        self.value = (self.value & 0xFC) | (level & 0x03)


class IasWd(Cluster):
    """The IAS WD cluster provides an interface to the functionality of any Warning
    Device equipment of the IAS system. Using this cluster, a Zigbee enabled CIE device
    can access a Zigbee enabled IAS WD device and issue alarm warning indications
    (siren, strobe lighting, etc.) when a system alarm condition is detected
    """

    StrobeLevel: Final = StrobeLevel
    Warning: Final = WarningType
    Squawk: Final = Squawk

    cluster_id: Final[t.uint16_t] = 0x0502
    name: Final = "IAS Warning Device"
    ep_attribute: Final = "ias_wd"

    class AttributeDefs(BaseAttributeDefs):
        max_duration: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rw", mandatory=True
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        start_warning: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "warning": WarningType,
                "warning_duration": t.uint16_t,
                "strobe_duty_cycle": t.uint8_t,
                "stobe_level": StrobeLevel,
            },
            direction=Direction.Client_to_Server,
        )
        squawk: Final = ZCLCommandDef(
            id=0x01, schema={"squawk": Squawk}, direction=Direction.Client_to_Server
        )
