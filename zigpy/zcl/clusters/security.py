"""Security and Safety Functional Domain"""
import collections
import enum

import zigpy.types as t
from zigpy.zcl import Cluster


class IasZone(Cluster):
    class ZoneStatus(t.Struct):
        _fields = [("zone_id", t.uint8_t), ("zone_status", t.bitmap16)]

    class ZoneType(t.enum16, enum.Enum):
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

        @classmethod
        def deserialize(cls, data):
            try:
                return super().deserialize(data)
            except ValueError:
                fake = collections.namedtuple(cls.__name__, "name, value")
                val, data = t.uint16_t.deserialize(data)
                return fake("manufacturer_specific_0x{:04x}".format(val), val), data

    cluster_id = 0x0500
    name = "IAS Zone"
    ep_attribute = "ias_zone"
    attributes = {
        # Zone Information
        0x0000: ("zone_state", t.enum8),
        0x0001: ("zone_type", t.enum16),
        0x0002: ("zone_status", t.bitmap16),
        # Zone Settings
        0x0010: ("cie_addr", t.EUI64),
        0x0011: ("zone_id", t.uint8_t),
        0x0012: ("num_zone_sensitivity_levels_supported", t.uint8_t),
        0x0013: ("current_zone_sensitivity_level", t.uint8_t),
    }
    server_commands = {
        0x0000: ("enroll_response", (t.enum8, t.uint8_t), True),
        0x0001: ("init_normal_op_mode", (), False),
        0x0002: ("init_test_mode", (t.uint8_t, t.uint8_t), False),
    }
    client_commands = {
        0x0000: (
            "status_change_notification",
            (t.bitmap16, t.bitmap8, t.uint8_t, t.uint16_t),
            False,
        ),
        0x0001: ("enroll", (ZoneType, t.uint16_t), False),
    }


class IasAce(Cluster):
    class ArmMode(t.enum8, enum.Enum):
        """IAS ACE arm mode enum."""

        Disarm = 0x00
        Arm_Day_Home_Only = 0x01
        Arm_Night_Sleep_Only = 0x02
        Arm_All_Zones = 0x03

    class ArmNotification(t.enum8, enum.Enum):
        """IAS ACE arm notification enum."""

        All_Zones_Disarmed = 0x00
        Only_Day_Home_Zones_Armed = 0x01
        Only_Night_Sleep_Zones_Armed = 0x02
        All_Zones_Armed = 0x03
        Invalid_Arm_Disarm_Code = 0x04
        Not_Ready_To_Arm = 0x05
        Already_Disarmed = 0x06

    class AudibleNotification(t.enum8, enum.Enum):
        """IAS ACE audible notification enum."""

        Mute = 0x00
        Default_Sound = 0x01

        @classmethod
        def deserialize(cls, data):
            """Deserialize the audible notification enum."""
            try:
                return super().deserialize(data)
            except ValueError:
                fake = collections.namedtuple(cls.__name__, "name, value")
                val, data = t.uint8_t.deserialize(data)
                return fake("manufacturer_specific_0x{:02x}".format(val), val), data

    class PanelStatus(t.enum8, enum.Enum):
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

    class AlarmStatus(t.enum8, enum.Enum):
        """IAS ACE alarm status enum."""

        No_Alarm = 0x00
        Burglar = 0x01
        Fire = 0x02
        Emergency = 0x03
        Police_Panic = 0x04
        Fire_Panic = 0x05
        Emergency_Panic = 0x06

    cluster_id = 0x0501
    name = "IAS Ancillary Control Equipment"
    ep_attribute = "ias_ace"
    attributes = {}
    server_commands = {
        0x0000: ("arm", (ArmMode, t.CharacterString, t.uint8_t), False),
        0x0001: ("bypass", (t.LVList(t.uint8_t), t.CharacterString), False),
        0x0002: ("emergency", (), False),
        0x0003: ("fire", (), False),
        0x0004: ("panic", (), False),
        0x0005: ("get_zone_id_map", (), False),
        0x0006: ("get_zone_info", (t.uint8_t,), False),
        0x0007: ("get_panel_status", (), False),
        0x0008: ("get_bypassed_zone_list", (), False),
        0x0009: ("get_zone_status", (t.uint8_t, t.uint8_t, t.Bool, t.bitmap16), False),
    }
    client_commands = {
        0x0000: ("arm_response", (ArmNotification,), True),
        0x0001: ("get_zone_id_map_response", (t.List(t.bitmap16),), True),
        0x0002: (
            "get_zone_info_response",
            (t.uint8_t, IasZone.ZoneType, t.EUI64, t.CharacterString),
            True,
        ),
        0x0003: (
            "zone_status_changed",
            (t.uint8_t, IasZone.ZoneStatus, AudibleNotification, t.CharacterString),
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
        0x0006: ("set_bypassed_zone_list", (t.LVList(t.uint8_t),), False),
        0x0007: ("bypass_response", (t.LVList(t.uint8_t),), True),
        0x0008: (
            "get_zone_status_response",
            (t.Bool, t.LVList(IasZone.ZoneStatus)),
            True,
        ),
    }


class IasWd(Cluster):
    cluster_id = 0x0502
    name = "IAS Warning Device"
    ep_attribute = "ias_wd"
    attributes = {0x0000: ("max_duration", t.uint16_t)}
    server_commands = {
        0x0000: ("start_warning", (t.bitmap8, t.uint16_t, t.uint8_t, t.enum8), False),
        0x0001: ("squawk", (t.bitmap8,), False),
    }
    client_commands = {}
