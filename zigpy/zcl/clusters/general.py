"""General Functional Domain"""

from __future__ import annotations

import collections
from datetime import datetime
from typing import Any, List, Optional, Tuple, Union

import zigpy.types as t
from zigpy.zcl import Cluster, foundation


class Basic(Cluster):
    """Attributes for determining basic information about a
    device, setting user device information such as location,
    and enabling a device.
    """

    class PowerSource(t.enum8):
        """Power source enum."""

        Unknown = 0x00
        Mains_single_phase = 0x01
        Mains_three_phase = 0x02
        Battery = 0x03
        DC_Source = 0x04
        Emergency_Mains_Always_On = 0x05
        Emergency_Mains_Transfer_Switch = 0x06

        def __init__(self, *args, **kwargs):
            self.battery_backup = False

        @classmethod
        def deserialize(cls, data: bytes) -> Tuple[bytes, bytes]:
            val, data = t.uint8_t.deserialize(data)
            r = cls(val & 0x7F)
            r.battery_backup = bool(val & 0x80)
            return r, data

    class PhysicalEnvironment(t.enum8):
        Unspecified_environment = 0x00
        Mirror = 0x01
        Atrium = 0x01
        Bar = 0x02
        Courtyard = 0x03
        Bathroom = 0x04
        Bedroom = 0x05
        Billiard_Room = 0x06
        Utility_Room = 0x07
        Cellar = 0x08
        Storage_Closet = 0x09
        Theater = 0x0A
        Office = 0x0B
        Deck = 0x0C
        Den = 0x0D
        Dining_Room = 0x0E
        Electrical_Room = 0x0F
        Elevator = 0x10
        Entry = 0x11
        Family_Room = 0x12
        Main_Floor = 0x13
        Upstairs = 0x14
        Downstairs = 0x15
        Basement = 0x16
        Gallery = 0x17
        Game_Room = 0x18
        Garage = 0x19
        Gym = 0x1A
        Hallway = 0x1B
        House = 0x1C
        Kitchen = 0x1D
        Laundry_Room = 0x1E
        Library = 0x1F
        Master_Bedroom = 0x20
        Mud_Room_small_room_for_coats_and_boots = 0x21
        Nursery = 0x22
        Pantry = 0x23
        Office_2 = 0x24
        Outside = 0x25
        Pool = 0x26
        Porch = 0x27
        Sewing_Room = 0x28
        Sitting_Room = 0x29
        Stairway = 0x2A
        Yard = 0x2B
        Attic = 0x2C
        Hot_Tub = 0x2D
        Living_Room = 0x2E
        Sauna = 0x2F
        Workshop = 0x30
        Guest_Bedroom = 0x31
        Guest_Bath = 0x32
        Back_Yard = 0x34
        Front_Yard = 0x35
        Patio = 0x36
        Driveway = 0x37
        Sun_Room = 0x38
        Grand_Room = 0x39
        Spa = 0x3A
        Whirlpool = 0x3B
        Shed = 0x3C
        Equipment_Storage = 0x3D
        Craft_Room = 0x3E
        Fountain = 0x3F
        Pond = 0x40
        Reception_Room = 0x41
        Breakfast_Room = 0x42
        Nook = 0x43
        Garden = 0x44
        Balcony = 0x45
        Panic_Room = 0x46
        Terrace = 0x47
        Roof = 0x48
        Toilet = 0x49
        Toilet_Main = 0x4A
        Outside_Toilet = 0x4B
        Shower_room = 0x4C
        Study = 0x4D
        Front_Garden = 0x4E
        Back_Garden = 0x4F
        Kettle = 0x50
        Television = 0x51
        Stove = 0x52
        Microwave = 0x53
        Toaster = 0x54
        Vacuum = 0x55
        Appliance = 0x56
        Front_Door = 0x57
        Back_Door = 0x58
        Fridge_Door = 0x59
        Medication_Cabinet_Door = 0x60
        Wardrobe_Door = 0x61
        Front_Cupboard_Door = 0x62
        Other_Door = 0x63
        Waiting_Room = 0x64
        Triage_Room = 0x65
        Doctors_Office = 0x66
        Patients_Private_Room = 0x67
        Consultation_Room = 0x68
        Nurse_Station = 0x69
        Ward = 0x6A
        Corridor = 0x6B
        Operating_Theatre = 0x6C
        Dental_Surgery_Room = 0x6D
        Medical_Imaging_Room = 0x6E
        Decontamination_Room = 0x6F
        Unknown_environment = 0xFF

    class AlarmMask(t.bitmap8):
        General_hardware_fault = 0x01
        General_software_fault = 0x02

    class DisableLocalConfig(t.bitmap8):
        Reset = 0x01
        Device_Configuration = 0x02

    cluster_id = 0x0000
    ep_attribute = "basic"
    attributes = {
        # Basic Device Information
        0x0000: ("zcl_version", t.uint8_t),
        0x0001: ("app_version", t.uint8_t),
        0x0002: ("stack_version", t.uint8_t),
        0x0003: ("hw_version", t.uint8_t),
        0x0004: ("manufacturer", t.CharacterString),
        0x0005: ("model", t.CharacterString),
        0x0006: ("date_code", t.CharacterString),
        0x0007: ("power_source", PowerSource),
        0x0008: ("app_profile_version", t.enum8),
        # Basic Device Settings
        0x0010: ("location_desc", t.LimitedCharString(16)),
        0x0011: ("physical_env", PhysicalEnvironment),
        0x0012: ("device_enabled", t.Bool),
        0x0013: ("alarm_mask", AlarmMask),
        0x0014: ("disable_local_config", DisableLocalConfig),
        0x4000: ("sw_build_id", t.CharacterString),
    }
    server_commands = {0x0000: ("reset_fact_default", (), False)}
    client_commands = {}


class PowerConfiguration(Cluster):
    """Attributes for determining more detailed information
    about a device’s power source(s), and for configuring
    under/over voltage alarms."""

    cluster_id = 0x0001
    name = "Power Configuration"
    ep_attribute = "power"
    attributes = {
        # Mains Information
        0x0000: ("mains_voltage", t.uint16_t),
        0x0001: ("mains_frequency", t.uint8_t),
        # Mains Settings
        0x0010: ("mains_alarm_mask", t.bitmap8),
        0x0011: ("mains_volt_min_thres", t.uint16_t),
        0x0012: ("mains_volt_max_thres", t.uint16_t),
        0x0013: ("mains_voltage_dwell_trip_point", t.uint16_t),
        # Battery Information
        0x0020: ("battery_voltage", t.uint8_t),
        0x0021: ("battery_percentage_remaining", t.uint8_t),
        # Battery Settings
        0x0030: ("battery_manufacturer", t.CharacterString),
        0x0031: ("battery_size", t.enum8),
        0x0032: ("battery_a_hr_rating", t.uint16_t),
        0x0033: ("battery_quantity", t.uint8_t),
        0x0034: ("battery_rated_voltage", t.uint8_t),
        0x0035: ("battery_alarm_mask", t.bitmap8),
        0x0036: ("battery_volt_min_thres", t.uint8_t),
        0x0037: ("battery_volt_thres1", t.uint16_t),
        0x0038: ("battery_volt_thres2", t.uint16_t),
        0x0039: ("battery_volt_thres3", t.uint16_t),
        0x003A: ("battery_percent_min_thres", t.uint8_t),
        0x003B: ("battery_percent_thres1", t.uint8_t),
        0x003C: ("battery_percent_thres2", t.uint8_t),
        0x003D: ("battery_percent_thres3", t.uint8_t),
        0x003E: ("battery_alarm_state", t.bitmap32),
        # Battery 2 Information
        0x0040: ("battery_2_voltage", t.uint8_t),
        0x0041: ("battery_2_percentage_remaining", t.uint8_t),
        # Battery 2 Settings
        0x0050: ("battery_2_manufacturer", t.CharacterString),
        0x0051: ("battery_2_size", t.enum8),
        0x0052: ("battery_2_a_hr_rating", t.uint16_t),
        0x0053: ("battery_2_quantity", t.uint8_t),
        0x0054: ("battery_2_rated_voltage", t.uint8_t),
        0x0055: ("battery_2_alarm_mask", t.bitmap8),
        0x0056: ("battery_2_volt_min_thres", t.uint8_t),
        0x0057: ("battery_2_volt_thres1", t.uint16_t),
        0x0058: ("battery_2_volt_thres2", t.uint16_t),
        0x0059: ("battery_2_volt_thres3", t.uint16_t),
        0x005A: ("battery_2_percent_min_thres", t.uint8_t),
        0x005B: ("battery_2_percent_thres1", t.uint8_t),
        0x005C: ("battery_2_percent_thres2", t.uint8_t),
        0x005D: ("battery_2_percent_thres3", t.uint8_t),
        0x005E: ("battery_2_alarm_state", t.bitmap32),
        # Battery 3 Information
        0x0060: ("battery_3_voltage", t.uint8_t),
        0x0061: ("battery_3_percentage_remaining", t.uint8_t),
        # Battery 3 Settings
        0x0070: ("battery_3_manufacturer", t.CharacterString),
        0x0071: ("battery_3_size", t.enum8),
        0x0072: ("battery_3_a_hr_rating", t.uint16_t),
        0x0073: ("battery_3_quantity", t.uint8_t),
        0x0074: ("battery_3_rated_voltage", t.uint8_t),
        0x0075: ("battery_3_alarm_mask", t.bitmap8),
        0x0076: ("battery_3_volt_min_thres", t.uint8_t),
        0x0077: ("battery_3_volt_thres1", t.uint16_t),
        0x0078: ("battery_3_volt_thres2", t.uint16_t),
        0x0079: ("battery_3_volt_thres3", t.uint16_t),
        0x007A: ("battery_3_percent_min_thres", t.uint8_t),
        0x007B: ("battery_3_percent_thres1", t.uint8_t),
        0x007C: ("battery_3_percent_thres2", t.uint8_t),
        0x007D: ("battery_3_percent_thres3", t.uint8_t),
        0x007E: ("battery_3_alarm_state", t.bitmap32),
    }
    server_commands = {}
    client_commands = {}


class DeviceTemperature(Cluster):
    """Attributes for determining information about a device’s
    internal temperature, and for configuring under/over
    temperature alarms."""

    cluster_id = 0x0002
    name = "Device Temperature"
    ep_attribute = "device_temperature"
    attributes = {
        # Device Temperature Information
        0x0000: ("current_temperature", t.int16s),
        0x0001: ("min_temp_experienced", t.int16s),
        0x0002: ("max_temp_experienced", t.int16s),
        0x0003: ("over_temp_total_dwell", t.uint16_t),
        # Device Temperature Settings
        0x0010: ("dev_temp_alarm_mask", t.bitmap8),
        0x0011: ("low_temp_thres", t.int16s),
        0x0012: ("high_temp_thres", t.int16s),
        0x0013: ("low_temp_dwell_trip_point", t.uint24_t),
        0x0014: ("high_temp_dwell_trip_point", t.uint24_t),
    }
    server_commands = {}
    client_commands = {}


class Identify(Cluster):
    """Attributes and commands for putting a device into
    Identification mode (e.g. flashing a light)"""

    cluster_id = 0x0003
    ep_attribute = "identify"
    attributes = {
        0x0000: ("identify_time", t.uint16_t),
        0x0001: ("identify_commission_state", t.bitmap8),
    }
    server_commands = {
        0x0000: ("identify", (t.uint16_t,), False),
        0x0001: ("identify_query", (), False),
        0x0002: ("ezmode_invoke", (t.bitmap8,), False),
        0x0003: ("update_commission_state", (t.bitmap8,), False),
        0x0040: ("trigger_effect", (t.uint8_t, t.uint8_t), False),
    }
    client_commands = {0x0000: ("identify_query_response", (t.uint16_t,), True)}


class Groups(Cluster):
    """Attributes and commands for group configuration and
    manipulation."""

    cluster_id = 0x0004
    ep_attribute = "groups"
    attributes = {0x0000: ("name_support", t.bitmap8)}
    server_commands = {
        0x0000: ("add", (t.Group, t.CharacterString), False),
        0x0001: ("view", (t.Group,), False),
        0x0002: ("get_membership", (t.LVList[t.Group],), False),
        0x0003: ("remove", (t.Group,), False),
        0x0004: ("remove_all", (), False),
        0x0005: ("add_if_identifying", (t.Group, t.CharacterString), False),
    }
    client_commands = {
        0x0000: ("add_response", (foundation.Status, t.Group), True),
        0x0001: (
            "view_response",
            (foundation.Status, t.Group, t.CharacterString),
            True,
        ),
        0x0002: ("get_membership_response", (t.uint8_t, t.LVList[t.Group]), True),
        0x0003: ("remove_response", (foundation.Status, t.Group), True),
    }


class Scenes(Cluster):
    """Attributes and commands for scene configuration and
    manipulation."""

    cluster_id = 0x0005
    ep_attribute = "scenes"
    attributes = {
        # Scene Management Information
        0x0000: ("count", t.uint8_t),
        0x0001: ("current_scene", t.uint8_t),
        0x0002: ("current_group", t.uint16_t),
        0x0003: ("scene_valid", t.Bool),
        0x0004: ("name_support", t.bitmap8),
        0x0005: ("last_configured_by", t.EUI64),
    }
    server_commands = {
        0x0000: (
            "add",
            (t.uint16_t, t.uint8_t, t.uint16_t, t.CharacterString),
            False,
        ),  # + extension field sets
        0x0001: ("view", (t.uint16_t, t.uint8_t), False),
        0x0002: ("remove", (t.uint16_t, t.uint8_t), False),
        0x0003: ("remove_all", (t.uint16_t,), False),
        0x0004: ("store", (t.uint16_t, t.uint8_t), False),
        0x0005: ("recall", (t.uint16_t, t.uint8_t), False),
        0x0006: ("get_scene_membership", (t.uint16_t,), False),
        0x0040: ("enhanced_add", (), False),
        0x0041: ("enhanced_view", (), False),
        0x0042: ("copy", (), False),
    }
    client_commands = {
        0x0000: ("add_response", (t.uint8_t, t.uint16_t, t.uint8_t), True),
        0x0001: (
            "view_response",
            (t.uint8_t, t.uint16_t, t.uint8_t),
            True,
        ),  # + 3 more optionals
        0x0002: ("remove_response", (t.uint8_t, t.uint16_t, t.uint8_t), True),
        0x0003: ("remove_all_response", (t.uint8_t, t.uint16_t), True),
        0x0004: ("store_response", (t.uint8_t, t.uint16_t, t.uint8_t), True),
        0x0006: (
            "get_scene_membership_response",
            (t.uint8_t, t.uint8_t, t.uint16_t, t.Optional(t.LVList[t.uint8_t])),
            True,
        ),
        0x0040: ("enhanced_add_response", (), True),
        0x0041: ("enhanced_view_response", (), True),
        0x0042: ("copy_response", (), True),
    }


class OnOff(Cluster):
    """Attributes and commands for switching devices between
    ‘On’ and ‘Off’ states."""

    class StartUpOnOff(t.enum8):
        Off = 0x00
        On = 0x01
        Toggle = 0x02
        PreviousValue = 0xFF

    cluster_id = 0x0006
    name = "On/Off"
    ep_attribute = "on_off"
    attributes = {
        0x0000: ("on_off", t.Bool),
        0x4000: ("global_scene_control", t.Bool),
        0x4001: ("on_time", t.uint16_t),
        0x4002: ("off_wait_time", t.uint16_t),
        0x4003: ("start_up_on_off", StartUpOnOff),
    }
    server_commands = {
        0x0000: ("off", (), False),
        0x0001: ("on", (), False),
        0x0002: ("toggle", (), False),
        0x0040: ("off_with_effect", (t.uint8_t, t.uint8_t), False),
        0x0041: ("on_with_recall_global_scene", (), False),
        0x0042: ("on_with_timed_off", (t.uint8_t, t.uint16_t, t.uint16_t), False),
    }
    client_commands = {}


class OnOffConfiguration(Cluster):
    """Attributes and commands for configuring On/Off
    switching devices"""

    cluster_id = 0x0007
    name = "On/Off Switch Configuration"
    ep_attribute = "on_off_config"
    attributes = {
        # Switch Information
        0x0000: ("switch_type", t.enum8),
        # Switch Settings
        0x0010: ("switch_actions", t.enum8),
    }
    server_commands = {}
    client_commands = {}


class LevelControl(Cluster):
    """Attributes and commands for controlling devices that
    can be set to a level between fully ‘On’ and fully ‘Off’."""

    class StartUpCurrentLevel(t.enum8):
        Minimum = 0x00
        PreviousValue = 0xFF

    cluster_id = 0x0008
    name = "Level control"
    ep_attribute = "level"
    attributes = {
        0x0000: ("current_level", t.uint8_t),
        0x0001: ("remaining_time", t.uint16_t),
        0x0010: ("on_off_transition_time", t.uint16_t),
        0x0011: ("on_level", t.uint8_t),
        0x0012: ("on_transition_time", t.uint16_t),
        0x0013: ("off_transition_time", t.uint16_t),
        0x0014: ("default_move_rate", t.uint8_t),
        0x4000: ("start_up_current_level", StartUpCurrentLevel),
    }
    server_commands = {
        0x0000: ("move_to_level", (t.uint8_t, t.uint16_t), False),
        0x0001: ("move", (t.uint8_t, t.uint8_t), False),
        0x0002: ("step", (t.uint8_t, t.uint8_t, t.uint16_t), False),
        0x0003: ("stop", (), False),
        0x0004: ("move_to_level_with_on_off", (t.uint8_t, t.uint16_t), False),
        0x0005: ("move_with_on_off", (t.uint8_t, t.uint8_t), False),
        0x0006: ("step_with_on_off", (t.uint8_t, t.uint8_t, t.uint16_t), False),
        0x0007: ("stop", (), False),
    }
    client_commands = {}


class Alarms(Cluster):
    """Attributes and commands for sending notifications and
    configuring alarm functionality."""

    cluster_id = 0x0009
    ep_attribute = "alarms"
    attributes = {
        # Alarm Information
        0x0000: ("alarm_count", t.uint16_t)
    }
    server_commands = {
        0x0000: ("reset", (t.uint8_t, t.uint16_t), False),
        0x0001: ("reset_all", (), False),
        0x0002: ("get_alarm", (), False),
        0x0003: ("reset_log", (), False),
        0x0004: ("publish_event_log", (), False),
    }
    client_commands = {
        0x0000: ("alarm", (t.uint8_t, t.uint16_t), False),
        0x0001: (
            "get_alarm_response",
            (
                t.uint8_t,
                t.Optional(t.uint8_t),
                t.Optional(t.uint16_t),
                t.Optional(t.uint32_t),
            ),
            True,
        ),
        0x0002: ("get_event_log", (), False),
    }


class Time(Cluster):
    """Attributes and commands that provide a basic interface
    to a real-time clock."""

    cluster_id = 0x000A
    ep_attribute = "time"
    attributes = {
        0x0000: ("time", t.UTCTime),
        0x0001: ("time_status", t.bitmap8),
        0x0002: ("time_zone", t.int32s),
        0x0003: ("dst_start", t.uint32_t),
        0x0004: ("dst_end", t.uint32_t),
        0x0005: ("dst_shift", t.int32s),
        0x0006: ("standard_time", t.StandardTime),
        0x0007: ("local_time", t.LocalTime),
        0x0008: ("last_set_time", t.uint32_t),
        0x0009: ("valid_until_time", t.uint32_t),
    }
    server_commands = {}
    client_commands = {}

    def handle_cluster_general_request(
        self,
        hdr: foundation.ZCLHeader,
        *args: List[Any],
        dst_addressing: Optional[
            Union[t.Addressing.Group, t.Addressing.IEEE, t.Addressing.NWK]
        ] = None,
    ):
        if hdr.command_id == foundation.Command.Read_Attributes:
            # responses should be in the same order. Is it time to ditch py35?
            data = collections.OrderedDict()
            for attr in args[0][0]:
                if attr == 0:
                    epoch = datetime(2000, 1, 1, 0, 0, 0, 0)
                    diff = datetime.utcnow() - epoch
                    data[attr] = diff.total_seconds()
                elif attr == 1:
                    data[attr] = 7
                elif attr == 2:
                    diff = datetime.fromtimestamp(86400) - datetime.utcfromtimestamp(
                        86400
                    )
                    data[attr] = diff.total_seconds()
                elif attr == 7:
                    epoch = datetime(2000, 1, 1, 0, 0, 0, 0)
                    diff = datetime.now() - epoch
                    data[attr] = diff.total_seconds()
                else:
                    data[attr] = None
            self.create_catching_task(self.read_attributes_rsp(data, tsn=hdr.tsn))


class RSSILocation(Cluster):
    """Attributes and commands that provide a means for
    exchanging location information and channel parameters
    among devices."""

    cluster_id = 0x000B
    ep_attribute = "rssi_location"
    attributes = {
        # Location Information
        0x0000: ("type", t.uint8_t),
        0x0001: ("method", t.enum8),
        0x0002: ("age", t.uint16_t),
        0x0003: ("quality_measure", t.uint8_t),
        0x0004: ("num_of_devices", t.uint8_t),
        # Location Settings
        0x0010: ("coordinate1", t.int16s),
        0x0011: ("coordinate2", t.int16s),
        0x0012: ("coordinate3", t.int16s),
        0x0013: ("power", t.int16s),
        0x0014: ("path_loss_exponent", t.uint16_t),
        0x0015: ("reporting_period", t.uint16_t),
        0x0016: ("calc_period", t.uint16_t),
        0x0017: ("num_rssi_measurements", t.uint16_t),
    }
    server_commands = {
        0x0000: (
            "set_absolute_location",
            (t.int16s, t.int16s, t.int16s, t.int8s, t.uint16_t),
            False,
        ),
        0x0001: (
            "set_dev_config",
            (t.int16s, t.uint16_t, t.uint16_t, t.uint8_t, t.uint16_t),
            False,
        ),
        0x0002: ("get_dev_config", (t.EUI64,), False),
        0x0003: ("get_location_data", (t.bitmap8, t.uint8_t, t.EUI64), False),
        0x0004: (
            "rssi_response",
            (t.EUI64, t.int16s, t.int16s, t.int16s, t.int8s, t.uint8_t),
            True,
        ),
        0x0005: ("send_pings", (t.EUI64, t.uint8_t, t.uint16_t), False),
        0x0006: (
            "anchor_node_announce",
            (t.EUI64, t.int16s, t.int16s, t.int16s),
            False,
        ),
    }

    class NeighborInfo(t.Struct):
        neighbor: t.EUI64
        x: t.int16s
        y: t.int16s
        z: t.int16s
        rssi: t.int8s
        num_measurements: t.uint8_t

    client_commands = {
        0x0000: (
            "dev_config_response",
            (
                foundation.Status,
                t.Optional(t.int16s),
                t.Optional(t.uint16_t),
                t.Optional(t.uint16_t),
                t.Optional(t.uint8_t),
                t.Optional(t.uint16_t),
            ),
            True,
        ),
        0x0001: (
            "location_data_response",
            (
                foundation.Status,
                t.Optional(t.uint8_t),
                t.Optional(t.int16s),
                t.Optional(t.int16s),
                t.Optional(t.int16s),
                t.Optional(t.uint16_t),
                t.Optional(t.uint8_t),
                t.Optional(t.uint8_t),
                t.Optional(t.uint16_t),
            ),
            True,
        ),
        0x0002: ("location_data_notification", (), False),
        0x0003: ("compact_location_data_notification", (), False),
        0x0004: ("rssi_ping", (t.uint8_t,), False),  # data8
        0x0005: ("rssi_req", (), False),
        0x0006: ("report_rssi_measurements", (t.EUI64, t.LVList[NeighborInfo]), False),
        0x0007: ("request_own_location", (t.EUI64,), False),
    }


class AnalogInput(Cluster):
    cluster_id = 0x000C
    ep_attribute = "analog_input"
    attributes = {
        0x001C: ("description", t.CharacterString),
        0x0041: ("max_present_value", t.Single),
        0x0045: ("min_present_value", t.Single),
        0x0051: ("out_of_service", t.Bool),
        0x0055: ("present_value", t.Single),
        0x0067: ("reliability", t.enum8),
        0x006A: ("resolution", t.Single),
        0x006F: ("status_flags", t.bitmap8),
        0x0075: ("engineering_units", t.enum16),
        0x0100: ("application_type", t.uint32_t),
    }
    server_commands = {}
    client_commands = {}


class AnalogOutput(Cluster):
    cluster_id = 0x000D
    ep_attribute = "analog_output"
    attributes = {
        0x001C: ("description", t.CharacterString),
        0x0041: ("max_present_value", t.Single),
        0x0045: ("min_present_value", t.Single),
        0x0051: ("out_of_service", t.Bool),
        0x0055: ("present_value", t.Single),
        # 0x0057: ('priority_array', TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        0x0067: ("reliability", t.enum8),
        0x0068: ("relinquish_default", t.Single),
        0x006A: ("resolution", t.Single),
        0x006F: ("status_flags", t.bitmap8),
        0x0075: ("engineering_units", t.enum16),
        0x0100: ("application_type", t.uint32_t),
    }
    server_commands = {}
    client_commands = {}


class AnalogValue(Cluster):
    cluster_id = 0x000E
    ep_attribute = "analog_value"
    attributes = {
        0x001C: ("description", t.CharacterString),
        0x0051: ("out_of_service", t.Bool),
        0x0055: ("present_value", t.Single),
        # 0x0057: ('priority_array', TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        0x0067: ("reliability", t.enum8),
        0x0068: ("relinquish_default", t.Single),
        0x006F: ("status_flags", t.bitmap8),
        0x0075: ("engineering_units", t.enum16),
        0x0100: ("application_type", t.uint32_t),
    }
    server_commands = {}
    client_commands = {}


class BinaryInput(Cluster):
    cluster_id = 0x000F
    name = "Binary Input (Basic)"
    ep_attribute = "binary_input"
    attributes = {
        0x0004: ("active_text", t.CharacterString),
        0x001C: ("description", t.CharacterString),
        0x002E: ("inactive_text", t.CharacterString),
        0x0051: ("out_of_service", t.Bool),
        0x0054: ("polarity", t.enum8),
        0x0055: ("present_value", t.Bool),
        0x0067: ("reliability", t.enum8),
        0x006F: ("status_flags", t.bitmap8),
        0x0100: ("application_type", t.uint32_t),
    }
    server_commands = {}
    client_commands = {}


class BinaryOutput(Cluster):
    cluster_id = 0x0010
    ep_attribute = "binary_output"
    attributes = {
        0x0004: ("active_text", t.CharacterString),
        0x001C: ("description", t.CharacterString),
        0x002E: ("inactive_text", t.CharacterString),
        0x0042: ("minimum_off_time", t.uint32_t),
        0x0043: ("minimum_on_time", t.uint32_t),
        0x0051: ("out_of_service", t.Bool),
        0x0054: ("polarity", t.enum8),
        0x0055: ("present_value", t.Bool),
        # 0x0057: ('priority_array', TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        0x0067: ("reliability", t.enum8),
        0x0068: ("relinquish_default", t.Bool),
        0x006F: ("status_flags", t.bitmap8),
        0x0100: ("application_type", t.uint32_t),
    }
    server_commands = {}
    client_commands = {}


class BinaryValue(Cluster):
    cluster_id = 0x0011
    ep_attribute = "binary_value"
    attributes = {
        0x0004: ("active_text", t.CharacterString),
        0x001C: ("description", t.CharacterString),
        0x002E: ("inactive_text", t.CharacterString),
        0x0042: ("minimum_off_time", t.uint32_t),
        0x0043: ("minimum_on_time", t.uint32_t),
        0x0051: ("out_of_service", t.Bool),
        0x0055: ("present_value", t.Single),
        # 0x0057: ('priority_array', TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        0x0067: ("reliability", t.enum8),
        0x0068: ("relinquish_default", t.Single),
        0x006F: ("status_flags", t.bitmap8),
        0x0100: ("application_type", t.uint32_t),
    }
    server_commands = {}
    client_commands = {}


class MultistateInput(Cluster):
    cluster_id = 0x0012
    ep_attribute = "multistate_input"
    attributes = {
        0x000E: ("state_text", t.List[t.CharacterString]),
        0x001C: ("description", t.CharacterString),
        0x004A: ("number_of_states", t.uint16_t),
        0x0051: ("out_of_service", t.Bool),
        0x0055: ("present_value", t.Single),
        # 0x0057: ('priority_array', TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        0x0067: ("reliability", t.enum8),
        0x006F: ("status_flags", t.bitmap8),
        0x0100: ("application_type", t.uint32_t),
    }
    server_commands = {}
    client_commands = {}


class MultistateOutput(Cluster):
    cluster_id = 0x0013
    ep_attribute = "multistate_output"
    attributes = {
        0x000E: ("state_text", t.List[t.CharacterString]),
        0x001C: ("description", t.CharacterString),
        0x004A: ("number_of_states", t.uint16_t),
        0x0051: ("out_of_service", t.Bool),
        0x0055: ("present_value", t.Single),
        # 0x0057: ('priority_array', TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        0x0067: ("reliability", t.enum8),
        0x0068: ("relinquish_default", t.Single),
        0x006F: ("status_flags", t.bitmap8),
        0x0100: ("application_type", t.uint32_t),
    }
    server_commands = {}
    client_commands = {}


class MultistateValue(Cluster):
    cluster_id = 0x0014
    ep_attribute = "multistate_value"
    attributes = {
        0x000E: ("state_text", t.List[t.CharacterString]),
        0x001C: ("description", t.CharacterString),
        0x004A: ("number_of_states", t.uint16_t),
        0x0051: ("out_of_service", t.Bool),
        0x0055: ("present_value", t.Single),
        # 0x0057: ('priority_array', TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        0x0067: ("reliability", t.enum8),
        0x0068: ("relinquish_default", t.Single),
        0x006F: ("status_flags", t.bitmap8),
        0x0100: ("application_type", t.uint32_t),
    }
    server_commands = {}
    client_commands = {}


class Commissioning(Cluster):
    """Attributes and commands for commissioning and
    managing a ZigBee device."""

    cluster_id = 0x0015
    ep_attribute = "commissioning"
    attributes = {
        # Startup Parameters
        0x0000: ("short_address", t.uint16_t),
        0x0001: ("extended_pan_id", t.EUI64),
        0x0002: ("pan_id", t.uint16_t),
        0x0003: ("channelmask", t.bitmap32),
        0x0004: ("protocol_version", t.uint8_t),
        0x0005: ("stack_profile", t.uint8_t),
        0x0006: ("startup_control", t.enum8),
        0x0010: ("trust_center_address", t.EUI64),
        0x0011: ("trust_center_master_key", t.FixedList[16, t.uint8_t]),
        0x0012: ("network_key", t.FixedList[16, t.uint8_t]),
        0x0013: ("use_insecure_join", t.Bool),
        0x0014: ("preconfigured_link_key", t.FixedList[16, t.uint8_t]),
        0x0015: ("network_key_seq_num", t.uint8_t),
        0x0016: ("network_key_type", t.enum8),
        0x0017: ("network_manager_address", t.uint16_t),
        # Join Parameters
        0x0020: ("scan_attempts", t.uint8_t),
        0x0021: ("time_between_scans", t.uint16_t),
        0x0022: ("rejoin_interval", t.uint16_t),
        0x0023: ("max_rejoin_interval", t.uint16_t),
        # End Device Parameters
        0x0030: ("indirect_poll_rate", t.uint16_t),
        0x0031: ("parent_retry_threshold", t.uint8_t),
        # Concentrator Parameters
        0x0040: ("concentrator_flag", t.Bool),
        0x0041: ("concentrator_radius", t.uint8_t),
        0x0042: ("concentrator_discovery_time", t.uint8_t),
    }
    server_commands = {
        0x0000: ("restart_device", (t.uint8_t, t.uint8_t, t.uint8_t), False),
        0x0001: ("save_startup_parameters", (t.uint8_t, t.uint8_t), False),
        0x0002: ("restore_startup_parameters", (t.uint8_t, t.uint8_t), False),
        0x0003: ("reset_startup_parameters", (t.uint8_t, t.uint8_t), False),
    }
    client_commands = {
        0x0000: ("restart_device_response", (t.uint8_t,), True),
        0x0001: ("save_startup_params_response", (t.uint8_t,), True),
        0x0002: ("restore_startup_params_response", (t.uint8_t,), True),
        0x0003: ("reset_startup_params_response", (t.uint8_t,), True),
    }


class Partition(Cluster):
    cluster_id = 0x0016
    ep_attribute = "partition"
    attributes = {}
    server_commands = {}
    client_commands = {}


class Ota(Cluster):
    cluster_id = 0x0019
    ep_attribute = "ota"
    attributes = {
        0x0000: ("upgrade_server_id", t.EUI64),
        0x0001: ("file_offset", t.uint32_t),
        0x0002: ("current_file_version", t.uint32_t),
        0x0003: ("current_zigbee_stack_version", t.uint16_t),
        0x0004: ("downloaded_file_version", t.uint32_t),
        0x0005: ("downloaded_zigbee_stack_version", t.uint16_t),
        0x0006: ("image_upgrade_status", t.enum8),
        0x0007: ("manufacturer_id", t.uint16_t),
        0x0008: ("image_type_id", t.uint16_t),
        0x0009: ("minimum_block_req_delay", t.uint16_t),
        0x000A: ("image_stamp", t.uint32_t),
    }
    server_commands = {
        0x0001: (
            "query_next_image",
            (t.uint8_t, t.uint16_t, t.uint16_t, t.uint32_t, t.Optional(t.uint16_t)),
            False,
        ),
        0x0003: (
            "image_block",
            (
                t.uint8_t,
                t.uint16_t,
                t.uint16_t,
                t.uint32_t,
                t.uint32_t,
                t.uint8_t,
                t.Optional(t.EUI64),
                t.Optional(t.uint16_t),
            ),
            False,
        ),
        0x0004: (
            "image_page",
            (
                t.uint8_t,
                t.uint16_t,
                t.uint16_t,
                t.uint32_t,
                t.uint32_t,
                t.uint8_t,
                t.uint16_t,
                t.uint16_t,
                t.Optional(t.EUI64),
            ),
            False,
        ),
        0x0006: (
            "upgrade_end",
            (foundation.Status, t.uint16_t, t.uint16_t, t.uint32_t),
            False,
        ),
        0x0008: (
            "query_specific_file",
            (t.EUI64, t.uint16_t, t.uint16_t, t.uint32_t, t.uint16_t),
            False,
        ),
    }
    client_commands = {
        0x0000: (
            "image_notify",
            (
                t.uint8_t,
                t.uint8_t,
                t.Optional(t.uint16_t),
                t.Optional(t.uint16_t),
                t.Optional(t.uint32_t),
            ),
            False,
        ),
        0x0002: (
            "query_next_image_response",
            (
                foundation.Status,
                t.Optional(t.uint16_t),
                t.Optional(t.uint16_t),
                t.Optional(t.uint32_t),
                t.Optional(t.uint32_t),
            ),
            True,
        ),
        0x0005: (
            "image_block_response",
            (
                foundation.Status,
                t.uint16_t,
                t.uint16_t,
                t.uint32_t,
                t.uint32_t,
                t.LVBytes,
            ),
            True,
        ),
        0x0007: (
            "upgrade_end_response",
            (t.uint16_t, t.uint16_t, t.uint32_t, t.uint32_t, t.uint32_t),
            True,
        ),
        0x0009: (
            "query_specific_file_response",
            (
                foundation.Status,
                t.Optional(t.uint16_t),
                t.Optional(t.uint16_t),
                t.Optional(t.uint32_t),
                t.Optional(t.uint32_t),
            ),
            True,
        ),
    }

    def handle_cluster_request(
        self,
        hdr: foundation.ZCLHeader,
        args: List[Any],
        *,
        dst_addressing: Optional[
            Union[t.Addressing.Group, t.Addressing.IEEE, t.Addressing.NWK]
        ] = None,
    ):
        self.create_catching_task(
            self._handle_cluster_request(hdr, args, dst_addressing=dst_addressing),
        )

    async def _handle_cluster_request(
        self,
        hdr: foundation.ZCLHeader,
        args: List[Any],
        *,
        dst_addressing: Optional[
            Union[t.Addressing.Group, t.Addressing.IEEE, t.Addressing.NWK]
        ] = None,
    ):
        """Parse OTA commands."""
        tsn, command_id = hdr.tsn, hdr.command_id
        cmd_name = self.server_commands.get(command_id, [command_id])[0]

        if cmd_name == "query_next_image":
            await self._handle_query_next_image(*args, tsn=tsn)
        elif cmd_name == "image_block":
            await self._handle_image_block(*args, tsn=tsn)
        elif cmd_name == "upgrade_end":
            await self._handle_upgrade_end(*args, tsn=tsn)
        else:
            self.debug(
                "no '%s' OTA command handler for '%s %s': %s",
                cmd_name,
                self.endpoint.manufacturer,
                self.endpoint.model,
                args,
            )

    async def _handle_query_next_image(
        self,
        field_ctrl,
        manufacturer_id,
        image_type,
        current_file_version,
        hardware_version,
        *,
        tsn,
    ):
        self.debug(
            (
                "OTA query_next_image handler for '%s %s': "
                "field_control=%s, manufacture_id=%s, image_type=%s, "
                "current_file_version=%s, hardware_version=%s"
            ),
            self.endpoint.manufacturer,
            self.endpoint.model,
            field_ctrl,
            manufacturer_id,
            image_type,
            current_file_version,
            hardware_version,
        )

        img = await self.endpoint.device.application.ota.get_ota_image(
            manufacturer_id, image_type
        )

        if img is not None:
            should_update = img.should_update(
                manufacturer_id, image_type, current_file_version, hardware_version
            )
            self.debug(
                "OTA image version: %s, size: %s. Update needed: %s",
                img.version,
                img.header.image_size,
                should_update,
            )
            if should_update:
                self.info(
                    "Updating: %s %s", self.endpoint.manufacturer, self.endpoint.model
                )
                await self.query_next_image_response(
                    foundation.Status.SUCCESS,
                    img.key.manufacturer_id,
                    img.key.image_type,
                    img.version,
                    img.header.image_size,
                    tsn=tsn,
                )
                return
        else:
            self.debug("No OTA image is available")
        await self.query_next_image_response(
            foundation.Status.NO_IMAGE_AVAILABLE, tsn=tsn
        )

    async def _handle_image_block(
        self,
        field_ctr,
        manufacturer_id,
        image_type,
        file_version,
        file_offset,
        max_data_size,
        request_node_addr,
        block_request_delay,
        *,
        tsn=None,
    ):
        self.debug(
            (
                "OTA image_block handler for '%s %s': field_control=%s, "
                "manufacturer_id=%s, image_type=%s, file_version=%s, "
                "file_offset=%s, max_data_size=%s, request_node_addr=%s"
                "block_request_delay=%s"
            ),
            self.endpoint.manufacturer,
            self.endpoint.model,
            field_ctr,
            manufacturer_id,
            image_type,
            file_version,
            file_offset,
            max_data_size,
            request_node_addr,
            block_request_delay,
        )
        img = await self.endpoint.device.application.ota.get_ota_image(
            manufacturer_id, image_type
        )
        if img is None or img.version != file_version:
            self.debug("OTA image is not available")
            await self.image_block_response(foundation.Status.ABORT, tsn=tsn)
            return
        self.debug(
            "OTA upgrade progress: %0.1f", 100.0 * file_offset / img.header.image_size
        )
        try:
            await self.image_block_response(
                foundation.Status.SUCCESS,
                img.key.manufacturer_id,
                img.key.image_type,
                img.version,
                file_offset,
                img.get_image_block(file_offset, max_data_size),
                tsn=tsn,
            )
        except ValueError:
            await self.image_block_response(
                foundation.Status.MALFORMED_COMMAND, tsn=tsn
            )

    async def _handle_upgrade_end(
        self, status, manufacturer_id, image_type, file_ver, *, tsn
    ):
        self.debug(
            (
                "OTA upgrade_end handler for '%s %s': status=%s, "
                "manufacturer_id=%s, image_type=%s, file_version=%s"
            ),
            self.endpoint.manufacturer,
            self.endpoint.model,
            status,
            manufacturer_id,
            image_type,
            file_ver,
        )
        await self.upgrade_end_response(
            manufacturer_id, image_type, file_ver, 0x00000000, 0x00000000, tsn=tsn
        )


class PowerProfile(Cluster):
    cluster_id = 0x001A
    ep_attribute = "power_profile"
    attributes = {
        0x0000: ("total_profile_num", t.uint8_t),
        0x0001: ("multiple_scheduling", t.uint8_t),
        0x0002: ("energy_formatting", t.bitmap8),
        0x0003: ("energy_remote", t.Bool),
        0x0004: ("schedule_mode", t.bitmap8),
    }

    class ScheduleRecord(t.Struct):
        phase_id: t.uint8_t
        scheduled_time: t.uint16_t

    class PowerProfilePhase(t.Struct):
        energy_phase_id: t.uint8_t
        macro_phase_id: t.uint8_t
        expected_duration: t.uint16_t
        peak_power: t.uint16_t
        energy: t.uint16_t

    class PowerProfile(t.Struct):
        power_profile_id: t.uint8_t
        energy_phase_id: t.uint8_t
        power_profile_remote_control: t.Bool
        power_profile_state: t.uint8_t

    server_commands = {
        0x0000: ("power_profile_request", (t.uint8_t,), False),
        0x0001: ("power_profile_state_request", (), False),
        0x0002: (
            "get_power_profile_price_response",
            (t.uint8_t, t.uint16_t, t.uint32_t, t.uint8_t),
            True,
        ),
        0x0003: (
            "get_overall_schedule_price_response",
            (t.uint16_t, t.uint32_t, t.uint8_t),
            True,
        ),
        0x0004: (
            "energy_phases_schedule_notification",
            (t.uint8_t, t.LVList[ScheduleRecord]),
            False,
        ),
        0x0005: (
            "energy_phases_schedule_response",
            (t.uint8_t, t.LVList[ScheduleRecord]),
            True,
        ),
        0x0006: ("power_profile_schedule_constraints_request", (t.uint8_t,), False),
        0x0007: ("energy_phases_schedule_state_request", (t.uint8_t,), False),
        0x0008: (
            "get_power_profile_price_extended_response",
            (t.uint8_t, t.uint16_t, t.uint32_t, t.uint8_t),
            True,
        ),
    }
    client_commands = {
        0x0000: (
            "power_profile_notification",
            (t.uint8_t, t.uint8_t, t.LVList[PowerProfilePhase]),
            False,
        ),
        0x0001: (
            "power_profile_response",
            (t.uint8_t, t.uint8_t, t.LVList[PowerProfilePhase]),
            True,
        ),
        0x0002: (
            "power_profile_state_response",
            (t.LVList[PowerProfile],),
            True,
        ),
        0x0003: ("get_power_profile_price", (t.uint8_t,), False),
        0x0004: (
            "power_profile_state_notification",
            (t.LVList[PowerProfile],),
            False,
        ),
        0x0005: ("get_overall_schedule_price", (), False),
        0x0006: ("energy_phases_schedule_request", (), False),
        0x0007: ("energy_phases_schedule_state_response", (t.uint8_t, t.uint8_t), True),
        0x0008: (
            "energy_phases_schedule_state_notification",
            (t.uint8_t, t.uint8_t),
            False,
        ),
        0x0009: (
            "power_profile_schedule_constraints_notification",
            (t.uint8_t, t.uint16_t, t.uint16_t),
            False,
        ),
        0x000A: (
            "power_profile_schedule_constraints_response",
            (t.uint8_t, t.uint16_t, t.uint16_t),
            True,
        ),
        0x000B: (
            "get_power_profile_price_extended",
            (t.bitmap8, t.uint8_t, t.Optional(t.uint16_t)),
            False,
        ),
    }


class ApplianceControl(Cluster):
    cluster_id = 0x001B
    ep_attribute = "appliance_control"
    attributes = {}
    server_commands = {}
    client_commands = {}


class PollControl(Cluster):
    cluster_id = 0x0020
    name = "Poll Control"
    ep_attribute = "poll_control"
    attributes = {
        0x0000: ("checkin_interval", t.uint32_t),
        0x0001: ("long_poll_interval", t.uint32_t),
        0x0002: ("short_poll_interval", t.uint16_t),
        0x0003: ("fast_poll_timeout", t.uint16_t),
        0x0004: ("checkin_interval_min", t.uint32_t),
        0x0005: ("long_poll_interval_min", t.uint32_t),
        0x0006: ("fast_poll_timeout_max", t.uint16_t),
    }
    server_commands = {
        0x0000: ("checkin_response", (t.uint8_t, t.uint16_t), True),
        0x0001: ("fast_poll_stop", (), False),
        0x0002: ("set_long_poll_interval", (t.uint32_t,), False),
        0x0003: ("set_short_poll_interval", (t.uint16_t,), False),
    }
    client_commands = {0x0000: ("checkin", (), False)}


class GreenPowerProxy(Cluster):
    cluster_id = 0x0021
    ep_attribute = "green_power"
    attributes = {}
    server_commands = {}
    client_commands = {}
