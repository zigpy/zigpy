"""Security and Safety Functional Domain"""

from __future__ import annotations

from typing import Any, Tuple

import zigpy.types as t
from zigpy.zcl import Cluster
import zigpy.zcl.foundation


class IasZone(Cluster):
    """The IAS Zone cluster defines an interface to the functionality of an IAS
    security zone device. IAS Zone supports up to two alarm types per zone, low battery
    reports and supervision of the IAS network."""

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

    cluster_id = 0x0500
    name = "IAS Zone"
    ep_attribute = "ias_zone"
    attributes = {
        # Zone Information
        0x0000: ("zone_state", ZoneState),
        0x0001: ("zone_type", ZoneType),
        0x0002: ("zone_status", ZoneStatus),
        # Zone Settings
        0x0010: ("cie_addr", t.EUI64),
        0x0011: ("zone_id", t.uint8_t),
        0x0012: ("num_zone_sensitivity_levels_supported", t.uint8_t),
        0x0013: ("current_zone_sensitivity_level", t.uint8_t),
    }
    server_commands = {
        0x0000: ("enroll_response", (EnrollResponse, t.uint8_t), True),
        0x0001: ("init_normal_op_mode", (), False),
        0x0002: ("init_test_mode", (t.uint8_t, t.uint8_t), False),
    }
    client_commands = {
        0x0000: (
            "status_change_notification",
            (ZoneStatus, t.bitmap8, t.uint8_t, t.uint16_t),
            False,
        ),
        0x0001: ("enroll", (ZoneType, t.uint16_t), False),
    }

    def handle_cluster_request(
        self,
        hdr: zigpy.zcl.foundation.ZCLHeader,
        args: list[Any],
        *,
        dst_addressing: t.Addressing.Group
        | t.Addressing.IEEE
        | t.Addressing.NWK
        | None = None,
    ):
        if (
            hdr.command_id == 0
            and self.is_server
            and not hdr.frame_control.disable_default_response
        ):
            hdr.frame_control.is_reply = False  # this is a client -> server cmd
            self.send_default_rsp(hdr, zigpy.zcl.foundation.Status.SUCCESS)


class IasAce(Cluster):
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

    ZoneType = IasZone.ZoneType
    ZoneStatus = IasZone.ZoneStatus

    class ZoneStatusRsp(t.Struct):
        """Zone status response."""

        zone_id: t.uint8_t
        zone_status: IasZone.ZoneStatus

    cluster_id = 0x0501
    name = "IAS Ancillary Control Equipment"
    ep_attribute = "ias_ace"
    attributes = {}
    server_commands = {
        0x0000: ("arm", (ArmMode, t.CharacterString, t.uint8_t), False),
        0x0001: ("bypass", (t.LVList[t.uint8_t], t.CharacterString), False),
        0x0002: ("emergency", (), False),
        0x0003: ("fire", (), False),
        0x0004: ("panic", (), False),
        0x0005: ("get_zone_id_map", (), False),
        0x0006: ("get_zone_info", (t.uint8_t,), False),
        0x0007: ("get_panel_status", (), False),
        0x0008: ("get_bypassed_zone_list", (), False),
        0x0009: ("get_zone_status", (t.uint8_t, t.uint8_t, t.Bool, ZoneStatus), False),
    }
    client_commands = {
        0x0000: ("arm_response", (ArmNotification,), True),
        0x0001: ("get_zone_id_map_response", (t.List[t.bitmap16],), True),
        0x0002: (
            "get_zone_info_response",
            (t.uint8_t, ZoneType, t.EUI64, t.CharacterString),
            True,
        ),
        0x0003: (
            "zone_status_changed",
            (t.uint8_t, ZoneStatus, AudibleNotification, t.CharacterString),
            False,
        ),
        0x0004: (
            "panel_status_changed",
            (PanelStatus, t.uint8_t, AudibleNotification, AlarmStatus),
            False,
        ),
        0x0005: (
            "panel_status_response",
            (PanelStatus, t.uint8_t, AudibleNotification, AlarmStatus),
            True,
        ),
        0x0006: ("set_bypassed_zone_list", (t.LVList[t.uint8_t],), False),
        0x0007: ("bypass_response", (t.LVList[BypassResponse],), True),
        0x0008: ("get_zone_status_response", (t.Bool, t.LVList[ZoneStatusRsp]), True),
    }


class Strobe(t.enum8):
    No_strobe = 0x00
    Strobe = 0x01


class _SquawkOrWarningCommand:
    def __init__(self, value: int = 0) -> None:
        self.value = t.uint8_t(value)

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple["_SquawkOrWarningCommand", bytes]:
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


class IasWd(Cluster):
    """The IAS WD cluster provides an interface to the functionality of any Warning
    Device equipment of the IAS system. Using this cluster, a ZigBee enabled CIE device
    can access a ZigBee enabled IAS WD device and issue alarm warning indications
    (siren, strobe lighting, etc.) when a system alarm condition is detected
    """

    class StrobeLevel(t.enum8):
        Low_level_strobe = 0x00
        Medium_level_strobe = 0x01
        High_level_strobe = 0x02
        Very_high_level_strobe = 0x03

    class Warning(_SquawkOrWarningCommand):
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
        def mode(self) -> "WarningMode":
            return self.WarningMode((self.value >> 4) & 0x0F)

        @mode.setter
        def mode(self, mode: WarningMode) -> None:
            self.value = (self.value & 0xF) | (mode << 4)

        @property
        def strobe(self) -> "Strobe":
            return self.Strobe((self.value >> 2) & 0x01)

        @strobe.setter
        def strobe(self, strobe: "Strobe") -> None:
            self.value = (self.value & 0xF7) | ((strobe & 0x01) << 2)

        @property
        def level(self) -> "SirenLevel":
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
        def mode(self) -> "SquawkMode":
            return self.SquawkMode((self.value >> 4) & 0x0F)

        @mode.setter
        def mode(self, mode: SquawkMode) -> None:
            self.value = (self.value & 0xF) | ((mode & 0x0F) << 4)

        @property
        def strobe(self) -> "Strobe":
            return self.Strobe((self.value >> 3) & 0x01)

        @strobe.setter
        def strobe(self, strobe: Strobe) -> None:
            self.value = (self.value & 0xF7) | (strobe << 3)

        @property
        def level(self) -> "SquawkLevel":
            return self.SquawkLevel(self.value & 0x03)

        @level.setter
        def level(self, level: SquawkLevel) -> None:
            self.value = (self.value & 0xFC) | (level & 0x03)

    cluster_id = 0x0502
    name = "IAS Warning Device"
    ep_attribute = "ias_wd"
    attributes = {0x0000: ("max_duration", t.uint16_t)}
    server_commands = {
        0x0000: ("start_warning", (Warning, t.uint16_t, t.uint8_t, StrobeLevel), False),
        0x0001: ("squawk", (Squawk,), False),
    }
    client_commands = {}
