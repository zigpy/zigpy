"""General Functional Domain"""

from __future__ import annotations

from datetime import datetime, timezone
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

ZIGBEE_EPOCH = datetime(2000, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)


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
    def deserialize(cls, data: bytes) -> tuple[bytes, bytes]:
        val, data = t.uint8_t.deserialize(data)
        r = cls(val & 0x7F)
        r.battery_backup = bool(val & 0x80)
        return r, data


class PhysicalEnvironment(t.enum8):
    Unspecified_environment = 0x00
    # Mirror Capacity Available: for 0x0109 Profile Id only; use 0x71 moving forward
    # Atrium: defined for legacy devices with non-0x0109 Profile Id; use 0x70 moving
    #         forward

    # Note: This value is deprecated for Profile Id 0x0104. The value 0x01 is
    #       maintained for historical purposes and SHOULD only be used for backwards
    #       compatibility with devices developed before this specification. The 0x01
    #       value MUST be interpreted using the Profile Id of the endpoint upon
    #       which it is implemented. For endpoints with the Smart Energy Profile Id
    #       (0x0109) the value 0x01 has a meaning of Mirror. For endpoints with any
    #       other profile identifier, the value 0x01 has a meaning of Atrium.
    Mirror_or_atrium_legacy = 0x01
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
    Atrium = 0x70
    Mirror = 0x71
    Unknown_environment = 0xFF


class AlarmMask(t.bitmap8):
    General_hardware_fault = 0x01
    General_software_fault = 0x02


class DisableLocalConfig(t.bitmap8):
    Reset = 0x01
    Device_Configuration = 0x02


class GenericDeviceClass(t.enum8):
    Lighting = 0x00


class GenericLightingDeviceType(t.enum8):
    Incandescent = 0x00
    Spotlight_Halogen = 0x01
    Halogen_bulb = 0x02
    CFL = 0x03
    Linear_Fluorescent = 0x04
    LED_bulb = 0x05
    Spotlight_LED = 0x06
    LED_strip = 0x07
    LED_tube = 0x08
    Generic_indoor_luminaire = 0x09
    Generic_outdoor_luminaire = 0x0A
    Pendant_luminaire = 0x0B
    Floor_standing_luminaire = 0x0C
    Generic_Controller = 0xE0
    Wall_Switch = 0xE1
    Portable_remote_controller = 0xE2
    Motion_sensor = 0xE3
    # 0xe4 to 0xef Reserved
    Generic_actuator = 0xF0
    Wall_socket = 0xF1
    Gateway_Bridge = 0xF2
    Plug_in_unit = 0xF3
    Retrofit_actuator = 0xF4
    Unspecified = 0xFF


class Basic(Cluster):
    """Attributes for determining basic information about a
    device, setting user device information such as location,
    and enabling a device.
    """

    PowerSource: Final = PowerSource
    PhysicalEnvironment: Final = PhysicalEnvironment
    AlarmMask: Final = AlarmMask
    DisableLocalConfig: Final = DisableLocalConfig
    GenericDeviceClass: Final = GenericDeviceClass
    GenericLightingDeviceType: Final = GenericLightingDeviceType

    cluster_id: Final[t.uint16_t] = 0x0000
    ep_attribute: Final = "basic"

    class AttributeDefs(BaseAttributeDefs):
        # Basic Device Information
        zcl_version: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint8_t, access="r", mandatory=True
        )
        app_version: Final = ZCLAttributeDef(id=0x0001, type=t.uint8_t, access="r")
        stack_version: Final = ZCLAttributeDef(id=0x0002, type=t.uint8_t, access="r")
        hw_version: Final = ZCLAttributeDef(id=0x0003, type=t.uint8_t, access="r")
        manufacturer: Final = ZCLAttributeDef(
            id=0x0004, type=t.LimitedCharString(32), access="r"
        )
        model: Final = ZCLAttributeDef(
            id=0x0005, type=t.LimitedCharString(32), access="r"
        )
        date_code: Final = ZCLAttributeDef(
            id=0x0006, type=t.LimitedCharString(16), access="r"
        )
        power_source: Final = ZCLAttributeDef(
            id=0x0007, type=PowerSource, access="r", mandatory=True
        )
        generic_device_class: Final = ZCLAttributeDef(
            id=0x0008, type=GenericDeviceClass, access="r"
        )
        # Lighting is the only non-reserved device type
        generic_device_type: Final = ZCLAttributeDef(
            id=0x0009, type=GenericLightingDeviceType, access="r"
        )
        product_code: Final = ZCLAttributeDef(id=0x000A, type=t.LVBytes, access="r")
        product_url: Final = ZCLAttributeDef(
            id=0x000B, type=t.CharacterString, access="r"
        )
        manufacturer_version_details: Final = ZCLAttributeDef(
            id=0x000C, type=t.CharacterString, access="r"
        )
        serial_number: Final = ZCLAttributeDef(
            id=0x000D, type=t.CharacterString, access="r"
        )
        product_label: Final = ZCLAttributeDef(
            id=0x000E, type=t.CharacterString, access="r"
        )
        # Basic Device Settings
        location_desc: Final = ZCLAttributeDef(
            id=0x0010, type=t.LimitedCharString(16), access="rw"
        )
        physical_env: Final = ZCLAttributeDef(
            id=0x0011, type=PhysicalEnvironment, access="rw"
        )
        device_enabled: Final = ZCLAttributeDef(id=0x0012, type=t.Bool, access="rw")
        alarm_mask: Final = ZCLAttributeDef(id=0x0013, type=AlarmMask, access="rw")
        disable_local_config: Final = ZCLAttributeDef(
            id=0x0014, type=DisableLocalConfig, access="rw"
        )
        sw_build_id: Final = ZCLAttributeDef(
            id=0x4000, type=t.CharacterString, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        reset_fact_default: Final = ZCLCommandDef(
            id=0x00, schema={}, direction=Direction.Client_to_Server
        )

    def handle_read_attribute_zcl_version(self) -> t.uint8_t:
        return t.uint8_t(8)

    def handle_read_attribute_power_source(self) -> PowerSource:
        return PowerSource.DC_Source


class MainsAlarmMask(t.bitmap8):
    Voltage_Too_Low = 0b00000001
    Voltage_Too_High = 0b00000010
    Power_Supply_Unavailable = 0b00000100


class BatterySize(t.enum8):
    No_battery = 0x00
    Built_in = 0x01
    Other = 0x02
    AA = 0x03
    AAA = 0x04
    C = 0x05
    D = 0x06
    CR2 = 0x07
    CR123A = 0x08
    Unknown = 0xFF


class PowerConfiguration(Cluster):
    """Attributes for determining more detailed information
    about a device’s power source(s), and for configuring
    under/over voltage alarms.
    """

    MainsAlarmMask: Final = MainsAlarmMask
    BatterySize: Final = BatterySize

    cluster_id: Final[t.uint16_t] = 0x0001
    name: Final = "Power Configuration"
    ep_attribute: Final = "power"

    class AttributeDefs(BaseAttributeDefs):
        # Mains Information
        mains_voltage: Final = ZCLAttributeDef(id=0x0000, type=t.uint16_t, access="r")
        mains_frequency: Final = ZCLAttributeDef(id=0x0001, type=t.uint8_t, access="r")
        # Mains Settings
        mains_alarm_mask: Final = ZCLAttributeDef(
            id=0x0010, type=MainsAlarmMask, access="rw"
        )
        mains_volt_min_thres: Final = ZCLAttributeDef(
            id=0x0011, type=t.uint16_t, access="rw"
        )
        mains_volt_max_thres: Final = ZCLAttributeDef(
            id=0x0012, type=t.uint16_t, access="rw"
        )
        mains_voltage_dwell_trip_point: Final = ZCLAttributeDef(
            id=0x0013, type=t.uint16_t, access="rw"
        )
        # Battery Information
        battery_voltage: Final = ZCLAttributeDef(id=0x0020, type=t.uint8_t, access="r")
        battery_percentage_remaining: Final = ZCLAttributeDef(
            id=0x0021, type=t.uint8_t, access="rp"
        )
        # Battery Settings
        battery_manufacturer: Final = ZCLAttributeDef(
            id=0x0030, type=t.LimitedCharString(16), access="rw"
        )
        battery_size: Final = ZCLAttributeDef(id=0x0031, type=BatterySize, access="rw")
        battery_a_hr_rating: Final = ZCLAttributeDef(
            id=0x0032, type=t.uint16_t, access="rw"
        )
        # measured in units of 10mAHr
        battery_quantity: Final = ZCLAttributeDef(
            id=0x0033, type=t.uint8_t, access="rw"
        )
        battery_rated_voltage: Final = ZCLAttributeDef(
            id=0x0034, type=t.uint8_t, access="rw"
        )
        # measured in units of 100mV
        battery_alarm_mask: Final = ZCLAttributeDef(
            id=0x0035, type=t.bitmap8, access="rw"
        )
        battery_volt_min_thres: Final = ZCLAttributeDef(
            id=0x0036, type=t.uint8_t, access="rw"
        )
        battery_volt_thres1: Final = ZCLAttributeDef(
            id=0x0037, type=t.uint16_t, access="r*w"
        )
        battery_volt_thres2: Final = ZCLAttributeDef(
            id=0x0038, type=t.uint16_t, access="r*w"
        )
        battery_volt_thres3: Final = ZCLAttributeDef(
            id=0x0039, type=t.uint16_t, access="r*w"
        )
        battery_percent_min_thres: Final = ZCLAttributeDef(
            id=0x003A, type=t.uint8_t, access="r*w"
        )
        battery_percent_thres1: Final = ZCLAttributeDef(
            id=0x003B, type=t.uint8_t, access="r*w"
        )
        battery_percent_thres2: Final = ZCLAttributeDef(
            id=0x003C, type=t.uint8_t, access="r*w"
        )
        battery_percent_thres3: Final = ZCLAttributeDef(
            id=0x003D, type=t.uint8_t, access="r*w"
        )
        battery_alarm_state: Final = ZCLAttributeDef(
            id=0x003E, type=t.bitmap32, access="rp"
        )
        # Battery 2 Information
        battery_2_voltage: Final = ZCLAttributeDef(
            id=0x0040, type=t.uint8_t, access="r"
        )
        battery_2_percentage_remaining: Final = ZCLAttributeDef(
            id=0x0041, type=t.uint8_t, access="rp"
        )
        # Battery 2 Settings
        battery_2_manufacturer: Final = ZCLAttributeDef(
            id=0x0050, type=t.CharacterString, access="rw"
        )
        battery_2_size: Final = ZCLAttributeDef(
            id=0x0051, type=BatterySize, access="rw"
        )
        battery_2_a_hr_rating: Final = ZCLAttributeDef(
            id=0x0052, type=t.uint16_t, access="rw"
        )
        battery_2_quantity: Final = ZCLAttributeDef(
            id=0x0053, type=t.uint8_t, access="rw"
        )
        battery_2_rated_voltage: Final = ZCLAttributeDef(
            id=0x0054, type=t.uint8_t, access="rw"
        )
        battery_2_alarm_mask: Final = ZCLAttributeDef(
            id=0x0055, type=t.bitmap8, access="rw"
        )
        battery_2_volt_min_thres: Final = ZCLAttributeDef(
            id=0x0056, type=t.uint8_t, access="rw"
        )
        battery_2_volt_thres1: Final = ZCLAttributeDef(
            id=0x0057, type=t.uint16_t, access="r*w"
        )
        battery_2_volt_thres2: Final = ZCLAttributeDef(
            id=0x0058, type=t.uint16_t, access="r*w"
        )
        battery_2_volt_thres3: Final = ZCLAttributeDef(
            id=0x0059, type=t.uint16_t, access="r*w"
        )
        battery_2_percent_min_thres: Final = ZCLAttributeDef(
            id=0x005A, type=t.uint8_t, access="r*w"
        )
        battery_2_percent_thres1: Final = ZCLAttributeDef(
            id=0x005B, type=t.uint8_t, access="r*w"
        )
        battery_2_percent_thres2: Final = ZCLAttributeDef(
            id=0x005C, type=t.uint8_t, access="r*w"
        )
        battery_2_percent_thres3: Final = ZCLAttributeDef(
            id=0x005D, type=t.uint8_t, access="r*w"
        )
        battery_2_alarm_state: Final = ZCLAttributeDef(
            id=0x005E, type=t.bitmap32, access="rp"
        )
        # Battery 3 Information
        battery_3_voltage: Final = ZCLAttributeDef(
            id=0x0060, type=t.uint8_t, access="r"
        )
        battery_3_percentage_remaining: Final = ZCLAttributeDef(
            id=0x0061, type=t.uint8_t, access="rp"
        )
        # Battery 3 Settings
        battery_3_manufacturer: Final = ZCLAttributeDef(
            id=0x0070, type=t.CharacterString, access="rw"
        )
        battery_3_size: Final = ZCLAttributeDef(
            id=0x0071, type=BatterySize, access="rw"
        )
        battery_3_a_hr_rating: Final = ZCLAttributeDef(
            id=0x0072, type=t.uint16_t, access="rw"
        )
        battery_3_quantity: Final = ZCLAttributeDef(
            id=0x0073, type=t.uint8_t, access="rw"
        )
        battery_3_rated_voltage: Final = ZCLAttributeDef(
            id=0x0074, type=t.uint8_t, access="rw"
        )
        battery_3_alarm_mask: Final = ZCLAttributeDef(
            id=0x0075, type=t.bitmap8, access="rw"
        )
        battery_3_volt_min_thres: Final = ZCLAttributeDef(
            id=0x0076, type=t.uint8_t, access="rw"
        )
        battery_3_volt_thres1: Final = ZCLAttributeDef(
            id=0x0077, type=t.uint16_t, access="r*w"
        )
        battery_3_volt_thres2: Final = ZCLAttributeDef(
            id=0x0078, type=t.uint16_t, access="r*w"
        )
        battery_3_volt_thres3: Final = ZCLAttributeDef(
            id=0x0079, type=t.uint16_t, access="r*w"
        )
        battery_3_percent_min_thres: Final = ZCLAttributeDef(
            id=0x007A, type=t.uint8_t, access="r*w"
        )
        battery_3_percent_thres1: Final = ZCLAttributeDef(
            id=0x007B, type=t.uint8_t, access="r*w"
        )
        battery_3_percent_thres2: Final = ZCLAttributeDef(
            id=0x007C, type=t.uint8_t, access="r*w"
        )
        battery_3_percent_thres3: Final = ZCLAttributeDef(
            id=0x007D, type=t.uint8_t, access="r*w"
        )
        battery_3_alarm_state: Final = ZCLAttributeDef(
            id=0x007E, type=t.bitmap32, access="rp"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class DeviceTempAlarmMask(t.bitmap8):
    Temp_too_low = 0b00000001
    Temp_too_high = 0b00000010


class DeviceTemperature(Cluster):
    """Attributes for determining information about a device’s
    internal temperature, and for configuring under/over
    temperature alarms.
    """

    DeviceTempAlarmMask: Final = DeviceTempAlarmMask

    cluster_id: Final[t.uint16_t] = 0x0002
    name: Final = "Device Temperature"
    ep_attribute: Final = "device_temperature"

    class AttributeDefs(BaseAttributeDefs):
        # Device Temperature Information
        current_temperature: Final = ZCLAttributeDef(
            id=0x0000, type=t.int16s, access="r", mandatory=True
        )
        min_temp_experienced: Final = ZCLAttributeDef(
            id=0x0001, type=t.int16s, access="r"
        )
        max_temp_experienced: Final = ZCLAttributeDef(
            id=0x0002, type=t.int16s, access="r"
        )
        over_temp_total_dwell: Final = ZCLAttributeDef(
            id=0x0003, type=t.uint16_t, access="r"
        )
        # Device Temperature Settings
        dev_temp_alarm_mask: Final = ZCLAttributeDef(
            id=0x0010, type=DeviceTempAlarmMask, access="rw"
        )
        low_temp_thres: Final = ZCLAttributeDef(id=0x0011, type=t.int16s, access="rw")
        high_temp_thres: Final = ZCLAttributeDef(id=0x0012, type=t.int16s, access="rw")
        low_temp_dwell_trip_point: Final = ZCLAttributeDef(
            id=0x0013, type=t.uint24_t, access="rw"
        )
        high_temp_dwell_trip_point: Final = ZCLAttributeDef(
            id=0x0014, type=t.uint24_t, access="rw"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class EffectIdentifier(t.enum8):
    Blink = 0x00
    Breathe = 0x01
    Okay = 0x02
    Channel_change = 0x03
    Finish_effect = 0xFE
    Stop_effect = 0xFF


class EffectVariant(t.enum8):
    Default = 0x00


class Identify(Cluster):
    """Attributes and commands for putting a device into
    Identification mode (e.g. flashing a light)
    """

    EffectIdentifier: Final = EffectIdentifier
    EffectVariant: Final = EffectVariant

    cluster_id: Final[t.uint16_t] = 0x0003
    ep_attribute: Final = "identify"

    class AttributeDefs(BaseAttributeDefs):
        identify_time: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rw", mandatory=True
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        identify: Final = ZCLCommandDef(
            id=0x00,
            schema={"identify_time": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        identify_query: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )
        # 0x02: ("ezmode_invoke", (t.bitmap8,), False),
        # 0x03: ("update_commission_state", (t.bitmap8,), False),
        trigger_effect: Final = ZCLCommandDef(
            id=0x40,
            schema={"effect_id": EffectIdentifier, "effect_variant": EffectVariant},
            direction=Direction.Client_to_Server,
        )

    class ClientCommandDefs(BaseCommandDefs):
        identify_query_response: Final = ZCLCommandDef(
            id=0x00,
            schema={"timeout": t.uint16_t},
            direction=Direction.Server_to_Client,
        )


class NameSupport(t.bitmap8):
    Supported = 0b10000000


class Groups(Cluster):
    """Attributes and commands for group configuration and
    manipulation.
    """

    NameSupport: Final = NameSupport

    cluster_id: Final[t.uint16_t] = 0x0004
    ep_attribute: Final = "groups"

    class AttributeDefs(BaseAttributeDefs):
        name_support: Final = ZCLAttributeDef(
            id=0x0000, type=NameSupport, access="r", mandatory=True
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        add: Final = ZCLCommandDef(
            id=0x00,
            schema={"group_id": t.Group, "group_name": t.LimitedCharString(16)},
            direction=Direction.Client_to_Server,
        )
        view: Final = ZCLCommandDef(
            id=0x01, schema={"group_id": t.Group}, direction=Direction.Client_to_Server
        )
        get_membership: Final = ZCLCommandDef(
            id=0x02,
            schema={"groups": t.LVList[t.Group]},
            direction=Direction.Client_to_Server,
        )
        remove: Final = ZCLCommandDef(
            id=0x03, schema={"group_id": t.Group}, direction=Direction.Client_to_Server
        )
        remove_all: Final = ZCLCommandDef(
            id=0x04, schema={}, direction=Direction.Client_to_Server
        )
        add_if_identifying: Final = ZCLCommandDef(
            id=0x05,
            schema={"group_id": t.Group, "group_name": t.LimitedCharString(16)},
            direction=Direction.Client_to_Server,
        )

    class ClientCommandDefs(BaseCommandDefs):
        add_response: Final = ZCLCommandDef(
            id=0x00,
            schema={"status": foundation.Status, "group_id": t.Group},
            direction=Direction.Server_to_Client,
        )
        view_response: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "status": foundation.Status,
                "group_id": t.Group,
                "group_name": t.LimitedCharString(16),
            },
            direction=Direction.Server_to_Client,
        )
        get_membership_response: Final = ZCLCommandDef(
            id=0x02,
            schema={"capacity": t.uint8_t, "groups": t.LVList[t.Group]},
            direction=Direction.Server_to_Client,
        )
        remove_response: Final = ZCLCommandDef(
            id=0x03,
            schema={"status": foundation.Status, "group_id": t.Group},
            direction=Direction.Server_to_Client,
        )


class Scenes(Cluster):
    """Attributes and commands for scene configuration and
    manipulation.
    """

    NameSupport: Final = NameSupport

    cluster_id: Final[t.uint16_t] = 0x0005
    ep_attribute: Final = "scenes"

    class AttributeDefs(BaseAttributeDefs):
        # Scene Management Information
        count: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint8_t, access="r", mandatory=True
        )
        current_scene: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint8_t, access="r", mandatory=True
        )
        current_group: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        scene_valid: Final = ZCLAttributeDef(
            id=0x0003, type=t.Bool, access="r", mandatory=True
        )
        name_support: Final = ZCLAttributeDef(
            id=0x0004, type=NameSupport, access="r", mandatory=True
        )
        last_configured_by: Final = ZCLAttributeDef(id=0x0005, type=t.EUI64, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        add: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "group_id": t.Group,
                "scene_id": t.uint8_t,
                "transition_time": t.uint16_t,
                "scene_name": t.LimitedCharString(16),
            },
            direction=Direction.Client_to_Server,
        )
        # TODO: + extension field sets
        view: Final = ZCLCommandDef(
            id=0x01,
            schema={"group_id": t.Group, "scene_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        remove: Final = ZCLCommandDef(
            id=0x02,
            schema={"group_id": t.Group, "scene_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        remove_all: Final = ZCLCommandDef(
            id=0x03, schema={"group_id": t.Group}, direction=Direction.Client_to_Server
        )
        store: Final = ZCLCommandDef(
            id=0x04,
            schema={"group_id": t.Group, "scene_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        recall: Final = ZCLCommandDef(
            id=0x05,
            schema={
                "group_id": t.Group,
                "scene_id": t.uint8_t,
                "transition_time?": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )
        get_scene_membership: Final = ZCLCommandDef(
            id=0x06, schema={"group_id": t.Group}, direction=Direction.Client_to_Server
        )
        enhanced_add: Final = ZCLCommandDef(
            id=0x40,
            schema={
                "group_id": t.Group,
                "scene_id": t.uint8_t,
                "transition_time": t.uint16_t,
                "scene_name": t.LimitedCharString(16),
            },
            direction=Direction.Client_to_Server,
        )
        enhanced_view: Final = ZCLCommandDef(
            id=0x41,
            schema={"group_id": t.Group, "scene_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        copy: Final = ZCLCommandDef(
            id=0x42,
            schema={
                "mode": t.uint8_t,
                "group_id_from": t.uint16_t,
                "scene_id_from": t.uint8_t,
                "group_id_to": t.uint16_t,
                "scene_id_to": t.uint8_t,
            },
            direction=Direction.Client_to_Server,
        )

    class ClientCommandDefs(BaseCommandDefs):
        add_scene_response: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "status": foundation.Status,
                "group_id": t.Group,
                "scene_id": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        view_response: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "status": foundation.Status,
                "group_id": t.Group,
                "scene_id": t.uint8_t,
                "transition_time?": t.uint16_t,
                "scene_name?": t.LimitedCharString(16),
            },
            direction=Direction.Server_to_Client,
        )
        # TODO: + extension field sets
        remove_scene_response: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "status": foundation.Status,
                "group_id": t.Group,
                "scene_id": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        remove_all_scenes_response: Final = ZCLCommandDef(
            id=0x03,
            schema={"status": foundation.Status, "group_id": t.Group},
            direction=Direction.Server_to_Client,
        )
        store_scene_response: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "status": foundation.Status,
                "group_id": t.Group,
                "scene_id": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        get_scene_membership_response: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "status": foundation.Status,
                "capacity": t.uint8_t,
                "group_id": t.Group,
                "scenes?": t.LVList[t.uint8_t],
            },
            direction=Direction.Server_to_Client,
        )
        enhanced_add_response: Final = ZCLCommandDef(
            id=0x40,
            schema={
                "status": foundation.Status,
                "group_id": t.Group,
                "scene_id": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        enhanced_view_response: Final = ZCLCommandDef(
            id=0x41,
            schema={
                "status": foundation.Status,
                "group_id": t.Group,
                "scene_id": t.uint8_t,
                "transition_time?": t.uint16_t,
                "scene_name?": t.LimitedCharString(16),
            },
            direction=Direction.Server_to_Client,
        )
        # TODO: + extension field sets
        copy_response: Final = ZCLCommandDef(
            id=0x42,
            schema={
                "status": foundation.Status,
                "group_id": t.Group,
                "scene_id": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )


class StartUpOnOff(t.enum8):
    Off = 0x00
    On = 0x01
    Toggle = 0x02
    PreviousValue = 0xFF


class OffEffectIdentifier(t.enum8):
    Delayed_All_Off = 0x00
    Dying_Light = 0x01


class OnOffControl(t.bitmap8):
    Accept_Only_When_On = 0b00000001


class OnOff(Cluster):
    """Attributes and commands for switching devices between
    ‘On’ and ‘Off’ states.
    """

    StartUpOnOff: Final = StartUpOnOff
    OffEffectIdentifier: Final = OffEffectIdentifier
    OnOffControl: Final = OnOffControl

    DELAYED_ALL_OFF_FADE_TO_OFF = 0x00
    DELAYED_ALL_OFF_NO_FADE = 0x01
    DELAYED_ALL_OFF_DIM_THEN_FADE_TO_OFF = 0x02

    DYING_LIGHT_DIM_UP_THEN_FADE_TO_OFF = 0x00

    cluster_id: Final[t.uint16_t] = 0x0006
    name: Final = "On/Off"
    ep_attribute: Final = "on_off"

    class AttributeDefs(BaseAttributeDefs):
        on_off: Final = ZCLAttributeDef(
            id=0x0000, type=t.Bool, access="rps", mandatory=True
        )
        global_scene_control: Final = ZCLAttributeDef(
            id=0x4000, type=t.Bool, access="r"
        )
        on_time: Final = ZCLAttributeDef(id=0x4001, type=t.uint16_t, access="rw")
        off_wait_time: Final = ZCLAttributeDef(id=0x4002, type=t.uint16_t, access="rw")
        start_up_on_off: Final = ZCLAttributeDef(
            id=0x4003, type=StartUpOnOff, access="rw"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        off: Final = ZCLCommandDef(
            id=0x00, schema={}, direction=Direction.Client_to_Server
        )
        on: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )
        toggle: Final = ZCLCommandDef(
            id=0x02, schema={}, direction=Direction.Client_to_Server
        )
        off_with_effect: Final = ZCLCommandDef(
            id=0x40,
            schema={"effect_id": OffEffectIdentifier, "effect_variant": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        on_with_recall_global_scene: Final = ZCLCommandDef(
            id=0x41, schema={}, direction=Direction.Client_to_Server
        )
        on_with_timed_off: Final = ZCLCommandDef(
            id=0x42,
            schema={
                "on_off_control": OnOffControl,
                "on_time": t.uint16_t,
                "off_wait_time": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )


class SwitchType(t.enum8):
    Toggle = 0x00
    Momentary = 0x01
    Multifunction = 0x02


class SwitchActions(t.enum8):
    OnOff = 0x00
    OffOn = 0x01
    ToggleToggle = 0x02


class OnOffConfiguration(Cluster):
    """Attributes and commands for configuring On/Off switching devices"""

    SwitchType: Final = SwitchType
    SwitchActions: Final = SwitchActions

    cluster_id: Final[t.uint16_t] = 0x0007
    name: Final = "On/Off Switch Configuration"
    ep_attribute: Final = "on_off_config"

    class AttributeDefs(BaseAttributeDefs):
        switch_type: Final = ZCLAttributeDef(
            id=0x0000, type=SwitchType, access="r", mandatory=True
        )
        switch_actions: Final = ZCLAttributeDef(
            id=0x0010, type=SwitchActions, access="rw", mandatory=True
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class MoveMode(t.enum8):
    Up = 0x00
    Down = 0x01


class StepMode(t.enum8):
    Up = 0x00
    Down = 0x01


class OptionsMask(t.bitmap8):
    Execute_if_off_present = 0b00000001
    Couple_color_temp_to_level_present = 0b00000010


class Options(t.bitmap8):
    Execute_if_off = 0b00000001
    Couple_color_temp_to_level = 0b00000010


class LevelControl(Cluster):
    """Attributes and commands for controlling devices that
    can be set to a level between fully ‘On’ and fully ‘Off’.
    """

    MoveMode: Final = MoveMode
    StepMode: Final = StepMode
    Options: Final = Options
    OptionsMask: Final = OptionsMask

    cluster_id: Final[t.uint16_t] = 0x0008
    name: Final = "Level control"
    ep_attribute: Final = "level"

    class AttributeDefs(BaseAttributeDefs):
        current_level: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint8_t, access="rps", mandatory=True
        )
        remaining_time: Final = ZCLAttributeDef(id=0x0001, type=t.uint16_t, access="r")
        min_level: Final = ZCLAttributeDef(id=0x0002, type=t.uint8_t, access="r")
        max_level: Final = ZCLAttributeDef(id=0x0003, type=t.uint8_t, access="r")
        current_frequency: Final = ZCLAttributeDef(
            id=0x0004, type=t.uint16_t, access="rps"
        )
        min_frequency: Final = ZCLAttributeDef(id=0x0005, type=t.uint16_t, access="r")
        max_frequency: Final = ZCLAttributeDef(id=0x0006, type=t.uint16_t, access="r")
        options: Final = ZCLAttributeDef(id=0x000F, type=t.bitmap8, access="rw")
        on_off_transition_time: Final = ZCLAttributeDef(
            id=0x0010, type=t.uint16_t, access="rw"
        )
        on_level: Final = ZCLAttributeDef(id=0x0011, type=t.uint8_t, access="rw")
        on_transition_time: Final = ZCLAttributeDef(
            id=0x0012, type=t.uint16_t, access="rw"
        )
        off_transition_time: Final = ZCLAttributeDef(
            id=0x0013, type=t.uint16_t, access="rw"
        )
        default_move_rate: Final = ZCLAttributeDef(
            id=0x0014, type=t.uint8_t, access="rw"
        )
        start_up_current_level: Final = ZCLAttributeDef(
            id=0x4000, type=t.uint8_t, access="rw"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        move_to_level: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "level": t.uint8_t,
                "transition_time": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=Direction.Client_to_Server,
        )
        move: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "move_mode": MoveMode,
                "rate": t.uint8_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=Direction.Client_to_Server,
        )
        step: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "step_mode": StepMode,
                "step_size": t.uint8_t,
                "transition_time": t.uint16_t,
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=Direction.Client_to_Server,
        )
        stop: Final = ZCLCommandDef(
            id=0x03,
            schema={
                "options_mask?": OptionsMask,
                "options_override?": Options,
            },
            direction=Direction.Client_to_Server,
        )
        move_to_level_with_on_off: Final = ZCLCommandDef(
            id=0x04,
            schema={"level": t.uint8_t, "transition_time": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        move_with_on_off: Final = ZCLCommandDef(
            id=0x05,
            schema={"move_mode": MoveMode, "rate": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        step_with_on_off: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "step_mode": StepMode,
                "step_size": t.uint8_t,
                "transition_time": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )
        stop_with_on_off: Final = ZCLCommandDef(
            id=0x07, schema={}, direction=Direction.Client_to_Server
        )
        move_to_closest_frequency: Final = ZCLCommandDef(
            id=0x08,
            schema={"frequency": t.uint16_t},
            direction=Direction.Client_to_Server,
        )


class Alarms(Cluster):
    """Attributes and commands for sending notifications and
    configuring alarm functionality.
    """

    cluster_id: Final[t.uint16_t] = 0x0009
    ep_attribute: Final = "alarms"

    class AttributeDefs(BaseAttributeDefs):
        alarm_count: Final = ZCLAttributeDef(id=0x0000, type=t.uint16_t, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        reset_alarm: Final = ZCLCommandDef(
            id=0x00,
            schema={"alarm_code": t.uint8_t, "cluster_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        reset_all_alarms: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )
        get_alarm: Final = ZCLCommandDef(
            id=0x02, schema={}, direction=Direction.Client_to_Server
        )
        reset_alarm_log: Final = ZCLCommandDef(
            id=0x03, schema={}, direction=Direction.Client_to_Server
        )
        # 0x04: ("publish_event_log", {}, False),

    class ClientCommandDefs(BaseCommandDefs):
        alarm: Final = ZCLCommandDef(
            id=0x00,
            schema={"alarm_code": t.uint8_t, "cluster_id": t.uint16_t},
            direction=Direction.Client_to_Server,
        )
        get_alarm_response: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "status": foundation.Status,
                "alarm_code?": t.uint8_t,
                "cluster_id?": t.uint16_t,
                "timestamp?": t.uint32_t,
            },
            direction=Direction.Server_to_Client,
        )
        # 0x02: ("get_event_log", {}, False),


class TimeStatus(t.bitmap8):
    Master = 0b00000001
    Synchronized = 0b00000010
    Master_for_Zone_and_DST = 0b00000100
    Superseding = 0b00001000


class Time(Cluster):
    """Attributes and commands that provide a basic interface
    to a real-time clock.
    """

    TimeStatus: Final = TimeStatus

    cluster_id: Final[t.uint16_t] = 0x000A
    ep_attribute: Final = "time"

    class AttributeDefs(BaseAttributeDefs):
        time: Final = ZCLAttributeDef(
            id=0x0000, type=t.UTCTime, access="r*w", mandatory=True
        )
        time_status: Final = ZCLAttributeDef(
            id=0x0001, type=TimeStatus, access="r*w", mandatory=True
        )
        time_zone: Final = ZCLAttributeDef(id=0x0002, type=t.int32s, access="rw")
        dst_start: Final = ZCLAttributeDef(id=0x0003, type=t.uint32_t, access="rw")
        dst_end: Final = ZCLAttributeDef(id=0x0004, type=t.uint32_t, access="rw")
        dst_shift: Final = ZCLAttributeDef(id=0x0005, type=t.int32s, access="rw")
        standard_time: Final = ZCLAttributeDef(
            id=0x0006, type=t.StandardTime, access="r"
        )
        local_time: Final = ZCLAttributeDef(id=0x0007, type=t.LocalTime, access="r")
        last_set_time: Final = ZCLAttributeDef(id=0x0008, type=t.UTCTime, access="r")
        valid_until_time: Final = ZCLAttributeDef(
            id=0x0009, type=t.UTCTime, access="rw"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    def handle_read_attribute_time(self) -> t.UTCTime:
        now = datetime.now(timezone.utc)
        return t.UTCTime((now - ZIGBEE_EPOCH).total_seconds())

    def handle_read_attribute_time_status(self) -> TimeStatus:
        return (
            TimeStatus.Master
            | TimeStatus.Synchronized
            | TimeStatus.Master_for_Zone_and_DST
        )

    def handle_read_attribute_time_zone(self) -> t.int32s:
        tz_offset = datetime.now().astimezone().utcoffset()
        assert tz_offset is not None

        return t.int32s(tz_offset.total_seconds())

    def handle_read_attribute_local_time(self) -> t.LocalTime:
        now = datetime.now(timezone.utc)
        tz_offset = datetime.now().astimezone().utcoffset()
        assert tz_offset is not None

        return t.LocalTime((now + tz_offset - ZIGBEE_EPOCH).total_seconds())


class LocationMethod(t.enum8):
    Lateration = 0x00
    Signposting = 0x01
    RF_fingerprinting = 0x02
    Out_of_band = 0x03
    Centralized = 0x04


class NeighborInfo(t.Struct):
    neighbor: t.EUI64
    x: t.int16s
    y: t.int16s
    z: t.int16s
    rssi: t.int8s
    num_measurements: t.uint8_t


class RSSILocation(Cluster):
    """Attributes and commands that provide a means for
    exchanging location information and channel parameters
    among devices.
    """

    LocationMethod: Final = LocationMethod
    NeighborInfo: Final = NeighborInfo

    cluster_id: Final[t.uint16_t] = 0x000B
    ep_attribute: Final = "rssi_location"

    class AttributeDefs(BaseAttributeDefs):
        # Location Information
        type: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint8_t, access="rw", mandatory=True
        )
        method: Final = ZCLAttributeDef(
            id=0x0001, type=LocationMethod, access="rw", mandatory=True
        )
        age: Final = ZCLAttributeDef(id=0x0002, type=t.uint16_t, access="r")
        quality_measure: Final = ZCLAttributeDef(id=0x0003, type=t.uint8_t, access="r")
        num_of_devices: Final = ZCLAttributeDef(id=0x0004, type=t.uint8_t, access="r")
        # Location Settings
        coordinate1: Final = ZCLAttributeDef(
            id=0x0010, type=t.int16s, access="rw", mandatory=True
        )
        coordinate2: Final = ZCLAttributeDef(
            id=0x0011, type=t.int16s, access="rw", mandatory=True
        )
        coordinate3: Final = ZCLAttributeDef(id=0x0012, type=t.int16s, access="rw")
        power: Final = ZCLAttributeDef(
            id=0x0013, type=t.int16s, access="rw", mandatory=True
        )
        path_loss_exponent: Final = ZCLAttributeDef(
            id=0x0014, type=t.uint16_t, access="rw", mandatory=True
        )
        reporting_period: Final = ZCLAttributeDef(
            id=0x0015, type=t.uint16_t, access="rw"
        )
        calculation_period: Final = ZCLAttributeDef(
            id=0x0016, type=t.uint16_t, access="rw"
        )
        number_rssi_measurements: Final = ZCLAttributeDef(
            id=0x0017, type=t.uint8_t, access="rw", mandatory=True
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        set_absolute_location: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "coordinate1": t.int16s,
                "coordinate2": t.int16s,
                "coordinate3": t.int16s,
                "power": t.int16s,
                "path_loss_exponent": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )
        set_dev_config: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "power": t.int16s,
                "path_loss_exponent": t.uint16_t,
                "calculation_period": t.uint16_t,
                "num_rssi_measurements": t.uint8_t,
                "reporting_period": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )
        get_dev_config: Final = ZCLCommandDef(
            id=0x02,
            schema={"target_addr": t.EUI64},
            direction=Direction.Client_to_Server,
        )
        get_location_data: Final = ZCLCommandDef(
            id=0x03,
            schema={
                "packed": t.bitmap8,
                "num_responses": t.uint8_t,
                "target_addr": t.EUI64,
            },
            direction=Direction.Client_to_Server,
        )
        rssi_response: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "replying_device": t.EUI64,
                "x": t.int16s,
                "y": t.int16s,
                "z": t.int16s,
                "rssi": t.int8s,
                "num_rssi_measurements": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        send_pings: Final = ZCLCommandDef(
            id=0x05,
            schema={
                "target_addr": t.EUI64,
                "num_rssi_measurements": t.uint8_t,
                "calculation_period": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )
        anchor_node_announce: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "anchor_node_ieee_addr": t.EUI64,
                "x": t.int16s,
                "y": t.int16s,
                "z": t.int16s,
            },
            direction=Direction.Client_to_Server,
        )

    class ClientCommandDefs(BaseCommandDefs):
        dev_config_response: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "status": foundation.Status,
                "power?": t.int16s,
                "path_loss_exponent?": t.uint16_t,
                "calculation_period?": t.uint16_t,
                "num_rssi_measurements?": t.uint8_t,
                "reporting_period?": t.uint16_t,
            },
            direction=Direction.Server_to_Client,
        )
        location_data_response: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "status": foundation.Status,
                "location_type?": t.uint8_t,
                "coordinate1?": t.int16s,
                "coordinate2?": t.int16s,
                "coordinate3?": t.int16s,
                "power?": t.uint16_t,
                "path_loss_exponent?": t.uint8_t,
                "location_method?": t.uint8_t,
                "quality_measure?": t.uint8_t,
                "location_age?": t.uint16_t,
            },
            direction=Direction.Server_to_Client,
        )
        location_data_notification: Final = ZCLCommandDef(
            id=0x02, schema={}, direction=Direction.Client_to_Server
        )
        compact_location_data_notification: Final = ZCLCommandDef(
            id=0x03, schema={}, direction=Direction.Client_to_Server
        )
        rssi_ping: Final = ZCLCommandDef(
            id=0x04,
            schema={"location_type": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        rssi_req: Final = ZCLCommandDef(
            id=0x05, schema={}, direction=Direction.Client_to_Server
        )
        report_rssi_measurements: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "measuring_device": t.EUI64,
                "neighbors": t.LVList[NeighborInfo],
            },
            direction=Direction.Client_to_Server,
        )
        request_own_location: Final = ZCLCommandDef(
            id=0x07,
            schema={"ieee_of_blind_node": t.EUI64},
            direction=Direction.Client_to_Server,
        )


class Reliability(t.enum8):
    No_fault_detected = 0
    No_sensor = 1
    Over_range = 2
    Under_range = 3
    Open_loop = 4
    Shorted_loop = 5
    No_output = 6
    Unreliable_other = 7
    Process_error = 8
    Multi_state_fault = 9
    Configuration_error = 10


class AnalogInput(Cluster):
    Reliability: Final = Reliability

    cluster_id: Final[t.uint16_t] = 0x000C
    ep_attribute: Final = "analog_input"

    class AttributeDefs(BaseAttributeDefs):
        description: Final = ZCLAttributeDef(
            id=0x001C, type=t.CharacterString, access="r*w"
        )
        max_present_value: Final = ZCLAttributeDef(
            id=0x0041, type=t.Single, access="r*w"
        )
        min_present_value: Final = ZCLAttributeDef(
            id=0x0045, type=t.Single, access="r*w"
        )
        out_of_service: Final = ZCLAttributeDef(
            id=0x0051, type=t.Bool, access="r*w", mandatory=True
        )
        present_value: Final = ZCLAttributeDef(
            id=0x0055, type=t.Single, access="rwp", mandatory=True
        )
        reliability: Final = ZCLAttributeDef(id=0x0067, type=Reliability, access="r*w")
        resolution: Final = ZCLAttributeDef(id=0x006A, type=t.Single, access="r*w")
        status_flags: Final = ZCLAttributeDef(
            id=0x006F, type=t.bitmap8, access="rp", mandatory=True
        )
        engineering_units: Final = ZCLAttributeDef(
            id=0x0075, type=t.enum16, access="r*w"
        )
        application_type: Final = ZCLAttributeDef(
            id=0x0100, type=t.uint32_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class AnalogOutput(Cluster):
    cluster_id: Final[t.uint16_t] = 0x000D
    ep_attribute: Final = "analog_output"

    class AttributeDefs(BaseAttributeDefs):
        description: Final = ZCLAttributeDef(
            id=0x001C, type=t.CharacterString, access="r*w"
        )
        max_present_value: Final = ZCLAttributeDef(
            id=0x0041, type=t.Single, access="r*w"
        )
        min_present_value: Final = ZCLAttributeDef(
            id=0x0045, type=t.Single, access="r*w"
        )
        out_of_service: Final = ZCLAttributeDef(
            id=0x0051, type=t.Bool, access="r*w", mandatory=True
        )
        present_value: Final = ZCLAttributeDef(
            id=0x0055, type=t.Single, access="rwp", mandatory=True
        )
        # 0x0057: ZCLAttributeDef('priority_array', type=TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        reliability: Final = ZCLAttributeDef(id=0x0067, type=t.enum8, access="r*w")
        relinquish_default: Final = ZCLAttributeDef(
            id=0x0068, type=t.Single, access="r*w"
        )
        resolution: Final = ZCLAttributeDef(id=0x006A, type=t.Single, access="r*w")
        status_flags: Final = ZCLAttributeDef(
            id=0x006F, type=t.bitmap8, access="rp", mandatory=True
        )
        engineering_units: Final = ZCLAttributeDef(
            id=0x0075, type=t.enum16, access="r*w"
        )
        application_type: Final = ZCLAttributeDef(
            id=0x0100, type=t.uint32_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class AnalogValue(Cluster):
    cluster_id: Final[t.uint16_t] = 0x000E
    ep_attribute: Final = "analog_value"

    class AttributeDefs(BaseAttributeDefs):
        description: Final = ZCLAttributeDef(
            id=0x001C, type=t.CharacterString, access="r*w"
        )
        out_of_service: Final = ZCLAttributeDef(
            id=0x0051, type=t.Bool, access="r*w", mandatory=True
        )
        present_value: Final = ZCLAttributeDef(
            id=0x0055, type=t.Single, access="rw", mandatory=True
        )
        # 0x0057: ('priority_array', TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        reliability: Final = ZCLAttributeDef(id=0x0067, type=t.enum8, access="r*w")
        relinquish_default: Final = ZCLAttributeDef(
            id=0x0068, type=t.Single, access="r*w"
        )
        status_flags: Final = ZCLAttributeDef(
            id=0x006F, type=t.bitmap8, access="r", mandatory=True
        )
        engineering_units: Final = ZCLAttributeDef(
            id=0x0075, type=t.enum16, access="r*w"
        )
        application_type: Final = ZCLAttributeDef(
            id=0x0100, type=t.uint32_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class BinaryInput(Cluster):
    cluster_id: Final[t.uint16_t] = 0x000F
    name: Final = "Binary Input (Basic)"
    ep_attribute: Final = "binary_input"

    class AttributeDefs(BaseAttributeDefs):
        active_text: Final = ZCLAttributeDef(
            id=0x0004, type=t.CharacterString, access="r*w"
        )
        description: Final = ZCLAttributeDef(
            id=0x001C, type=t.CharacterString, access="r*w"
        )
        inactive_text: Final = ZCLAttributeDef(
            id=0x002E, type=t.CharacterString, access="r*w"
        )
        out_of_service: Final = ZCLAttributeDef(
            id=0x0051, type=t.Bool, access="r*w", mandatory=True
        )
        polarity: Final = ZCLAttributeDef(id=0x0054, type=t.enum8, access="r")
        present_value: Final = ZCLAttributeDef(
            id=0x0055, type=t.Bool, access="r*w", mandatory=True
        )
        reliability: Final = ZCLAttributeDef(id=0x0067, type=t.enum8, access="r*w")
        status_flags: Final = ZCLAttributeDef(
            id=0x006F, type=t.bitmap8, access="r", mandatory=True
        )
        application_type: Final = ZCLAttributeDef(
            id=0x0100, type=t.uint32_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class BinaryOutput(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0010
    ep_attribute: Final = "binary_output"

    class AttributeDefs(BaseAttributeDefs):
        active_text: Final = ZCLAttributeDef(
            id=0x0004, type=t.CharacterString, access="r*w"
        )
        description: Final = ZCLAttributeDef(
            id=0x001C, type=t.CharacterString, access="r*w"
        )
        inactive_text: Final = ZCLAttributeDef(
            id=0x002E, type=t.CharacterString, access="r*w"
        )
        minimum_off_time: Final = ZCLAttributeDef(
            id=0x0042, type=t.uint32_t, access="r*w"
        )
        minimum_on_time: Final = ZCLAttributeDef(
            id=0x0043, type=t.uint32_t, access="r*w"
        )
        out_of_service: Final = ZCLAttributeDef(
            id=0x0051, type=t.Bool, access="r*w", mandatory=True
        )
        polarity: Final = ZCLAttributeDef(id=0x0054, type=t.enum8, access="r")
        present_value: Final = ZCLAttributeDef(
            id=0x0055, type=t.Bool, access="r*w", mandatory=True
        )
        # 0x0057: ('priority_array', TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        reliability: Final = ZCLAttributeDef(id=0x0067, type=t.enum8, access="r*w")
        relinquish_default: Final = ZCLAttributeDef(
            id=0x0068, type=t.Bool, access="r*w"
        )
        resolution: Final = ZCLAttributeDef(
            id=0x006A, type=t.Single, access="r"
        )  # Does not seem to be in binary_output
        status_flags: Final = ZCLAttributeDef(
            id=0x006F, type=t.bitmap8, access="r", mandatory=True
        )
        engineering_units: Final = ZCLAttributeDef(
            id=0x0075, type=t.enum16, access="r"
        )  # Does not seem to be in binary_output
        application_type: Final = ZCLAttributeDef(
            id=0x0100, type=t.uint32_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class BinaryValue(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0011
    ep_attribute: Final = "binary_value"

    class AttributeDefs(BaseAttributeDefs):
        active_text: Final = ZCLAttributeDef(
            id=0x0004, type=t.CharacterString, access="r*w"
        )
        description: Final = ZCLAttributeDef(
            id=0x001C, type=t.CharacterString, access="r*w"
        )
        inactive_text: Final = ZCLAttributeDef(
            id=0x002E, type=t.CharacterString, access="r*w"
        )
        minimum_off_time: Final = ZCLAttributeDef(
            id=0x0042, type=t.uint32_t, access="r*w"
        )
        minimum_on_time: Final = ZCLAttributeDef(
            id=0x0043, type=t.uint32_t, access="r*w"
        )
        out_of_service: Final = ZCLAttributeDef(
            id=0x0051, type=t.Bool, access="r*w", mandatory=True
        )
        present_value: Final = ZCLAttributeDef(
            id=0x0055, type=t.Single, access="r*w", mandatory=True
        )
        # 0x0057: ZCLAttributeDef('priority_array', type=TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        reliability: Final = ZCLAttributeDef(id=0x0067, type=t.enum8, access="r*w")
        relinquish_default: Final = ZCLAttributeDef(
            id=0x0068, type=t.Single, access="r*w"
        )
        status_flags: Final = ZCLAttributeDef(
            id=0x006F, type=t.bitmap8, access="r", mandatory=True
        )
        application_type: Final = ZCLAttributeDef(
            id=0x0100, type=t.uint32_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class MultistateInput(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0012
    ep_attribute: Final = "multistate_input"

    class AttributeDefs(BaseAttributeDefs):
        state_text: Final = ZCLAttributeDef(
            id=0x000E, type=t.LVList[t.CharacterString, t.uint16_t], access="r*w"
        )
        description: Final = ZCLAttributeDef(
            id=0x001C, type=t.CharacterString, access="r*w"
        )
        number_of_states: Final = ZCLAttributeDef(
            id=0x004A, type=t.uint16_t, access="r*w"
        )
        out_of_service: Final = ZCLAttributeDef(
            id=0x0051, type=t.Bool, access="r*w", mandatory=True
        )
        present_value: Final = ZCLAttributeDef(
            id=0x0055, type=t.Single, access="r*w", mandatory=True
        )
        # 0x0057: ('priority_array', TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        reliability: Final = ZCLAttributeDef(id=0x0067, type=t.enum8, access="r*w")
        status_flags: Final = ZCLAttributeDef(
            id=0x006F, type=t.bitmap8, access="r", mandatory=True
        )
        application_type: Final = ZCLAttributeDef(
            id=0x0100, type=t.uint32_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class MultistateOutput(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0013
    ep_attribute: Final = "multistate_output"

    class AttributeDefs(BaseAttributeDefs):
        state_text: Final = ZCLAttributeDef(
            id=0x000E, type=t.LVList[t.CharacterString, t.uint16_t], access="r*w"
        )
        description: Final = ZCLAttributeDef(
            id=0x001C, type=t.CharacterString, access="r*w"
        )
        number_of_states: Final = ZCLAttributeDef(
            id=0x004A, type=t.uint16_t, access="r*w", mandatory=True
        )
        out_of_service: Final = ZCLAttributeDef(
            id=0x0051, type=t.Bool, access="r*w", mandatory=True
        )
        present_value: Final = ZCLAttributeDef(
            id=0x0055, type=t.Single, access="r*w", mandatory=True
        )
        # 0x0057: ZCLAttributeDef('priority_array', type=TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        reliability: Final = ZCLAttributeDef(id=0x0067, type=t.enum8, access="r*w")
        relinquish_default: Final = ZCLAttributeDef(
            id=0x0068, type=t.Single, access="r*w"
        )
        status_flags: Final = ZCLAttributeDef(
            id=0x006F, type=t.bitmap8, access="r", mandatory=True
        )
        application_type: Final = ZCLAttributeDef(
            id=0x0100, type=t.uint32_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class MultistateValue(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0014
    ep_attribute: Final = "multistate_value"

    class AttributeDefs(BaseAttributeDefs):
        state_text: Final = ZCLAttributeDef(
            id=0x000E, type=t.LVList[t.CharacterString, t.uint16_t], access="r*w"
        )
        description: Final = ZCLAttributeDef(
            id=0x001C, type=t.CharacterString, access="r*w"
        )
        number_of_states: Final = ZCLAttributeDef(
            id=0x004A, type=t.uint16_t, access="r*w", mandatory=True
        )
        out_of_service: Final = ZCLAttributeDef(
            id=0x0051, type=t.Bool, access="r*w", mandatory=True
        )
        present_value: Final = ZCLAttributeDef(
            id=0x0055, type=t.Single, access="r*w", mandatory=True
        )
        # 0x0057: ZCLAttributeDef('priority_array', type=TODO.array),  # Array of 16 structures of (boolean,
        # single precision)
        reliability: Final = ZCLAttributeDef(id=0x0067, type=t.enum8, access="r*w")
        relinquish_default: Final = ZCLAttributeDef(
            id=0x0068, type=t.Single, access="r*w"
        )
        status_flags: Final = ZCLAttributeDef(
            id=0x006F, type=t.bitmap8, access="r", mandatory=True
        )
        application_type: Final = ZCLAttributeDef(
            id=0x0100, type=t.uint32_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class StartupControl(t.enum8):
    Part_of_network = 0x00
    Form_network = 0x01
    Rejoin_network = 0x02
    Start_from_scratch = 0x03


class NetworkKeyType(t.enum8):
    Standard = 0x01


class Commissioning(Cluster):
    """Attributes and commands for commissioning and
    managing a ZigBee device.
    """

    StartupControl: Final = StartupControl
    NetworkKeyType: Final = NetworkKeyType

    cluster_id: Final[t.uint16_t] = 0x0015
    ep_attribute: Final = "commissioning"

    class AttributeDefs(BaseAttributeDefs):
        # Startup Parameters
        short_address: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rw", mandatory=True
        )
        extended_pan_id: Final = ZCLAttributeDef(
            id=0x0001, type=t.EUI64, access="rw", mandatory=True
        )
        pan_id: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="rw", mandatory=True
        )
        channel_mask: Final = ZCLAttributeDef(
            id=0x0003, type=t.Channels, access="rw", mandatory=True
        )
        protocol_version: Final = ZCLAttributeDef(
            id=0x0004, type=t.uint8_t, access="rw", mandatory=True
        )
        stack_profile: Final = ZCLAttributeDef(
            id=0x0005, type=t.uint8_t, access="rw", mandatory=True
        )
        startup_control: Final = ZCLAttributeDef(
            id=0x0006, type=StartupControl, access="rw", mandatory=True
        )
        trust_center_address: Final = ZCLAttributeDef(
            id=0x0010, type=t.EUI64, access="rw", mandatory=True
        )
        trust_center_master_key: Final = ZCLAttributeDef(
            id=0x0011, type=t.KeyData, access="rw"
        )
        network_key: Final = ZCLAttributeDef(
            id=0x0012, type=t.KeyData, access="rw", mandatory=True
        )
        use_insecure_join: Final = ZCLAttributeDef(
            id=0x0013, type=t.Bool, access="rw", mandatory=True
        )
        preconfigured_link_key: Final = ZCLAttributeDef(
            id=0x0014, type=t.KeyData, access="rw", mandatory=True
        )
        network_key_seq_num: Final = ZCLAttributeDef(
            id=0x0015, type=t.uint8_t, access="rw", mandatory=True
        )
        network_key_type: Final = ZCLAttributeDef(
            id=0x0016, type=NetworkKeyType, access="rw", mandatory=True
        )
        network_manager_address: Final = ZCLAttributeDef(
            id=0x0017, type=t.uint16_t, access="rw", mandatory=True
        )
        # Join Parameters
        scan_attempts: Final = ZCLAttributeDef(id=0x0020, type=t.uint8_t, access="rw")
        time_between_scans: Final = ZCLAttributeDef(
            id=0x0021, type=t.uint16_t, access="rw"
        )
        rejoin_interval: Final = ZCLAttributeDef(
            id=0x0022, type=t.uint16_t, access="rw"
        )
        max_rejoin_interval: Final = ZCLAttributeDef(
            id=0x0023, type=t.uint16_t, access="rw"
        )
        # End Device Parameters
        indirect_poll_rate: Final = ZCLAttributeDef(
            id=0x0030, type=t.uint16_t, access="rw"
        )
        parent_retry_threshold: Final = ZCLAttributeDef(
            id=0x0031, type=t.uint8_t, access="r"
        )
        # Concentrator Parameters
        concentrator_flag: Final = ZCLAttributeDef(id=0x0040, type=t.Bool, access="rw")
        concentrator_radius: Final = ZCLAttributeDef(
            id=0x0041, type=t.uint8_t, access="rw"
        )
        concentrator_discovery_time: Final = ZCLAttributeDef(
            id=0x0042, type=t.uint8_t, access="rw"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        restart_device: Final = ZCLCommandDef(
            id=0x00,
            schema={"options": t.bitmap8, "delay": t.uint8_t, "jitter": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        save_startup_parameters: Final = ZCLCommandDef(
            id=0x01,
            schema={"options": t.bitmap8, "index": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        restore_startup_parameters: Final = ZCLCommandDef(
            id=0x02,
            schema={"options": t.bitmap8, "index": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        reset_startup_parameters: Final = ZCLCommandDef(
            id=0x03,
            schema={"options": t.bitmap8, "index": t.uint8_t},
            direction=Direction.Client_to_Server,
        )

    class ClientCommandDefs(BaseCommandDefs):
        restart_device_response: Final = ZCLCommandDef(
            id=0x00,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        save_startup_params_response: Final = ZCLCommandDef(
            id=0x01,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        restore_startup_params_response: Final = ZCLCommandDef(
            id=0x02,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )
        reset_startup_params_response: Final = ZCLCommandDef(
            id=0x03,
            schema={"status": foundation.Status},
            direction=Direction.Server_to_Client,
        )


class Partition(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0016
    ep_attribute: Final = "partition"

    class AttributeDefs(BaseAttributeDefs):
        maximum_incoming_transfer_size: Final = ZCLAttributeDef(
            id=0x0000,
            type=t.uint16_t,
            access="r",
            mandatory=True,
        )
        maximum_outgoing_transfer_size: Final = ZCLAttributeDef(
            id=0x0001,
            type=t.uint16_t,
            access="r",
            mandatory=True,
        )
        partitioned_frame_size: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint8_t, access="rw", mandatory=True
        )
        large_frame_size: Final = ZCLAttributeDef(
            id=0x0003, type=t.uint16_t, access="rw", mandatory=True
        )
        number_of_ack_frame: Final = ZCLAttributeDef(
            id=0x0004, type=t.uint8_t, access="rw", mandatory=True
        )
        nack_timeout: Final = ZCLAttributeDef(
            id=0x0005, type=t.uint16_t, access="r", mandatory=True
        )
        interframe_delay: Final = ZCLAttributeDef(
            id=0x0006, type=t.uint8_t, access="rw", mandatory=True
        )
        number_of_send_retries: Final = ZCLAttributeDef(
            id=0x0007, type=t.uint8_t, access="r", mandatory=True
        )
        sender_timeout: Final = ZCLAttributeDef(
            id=0x0008, type=t.uint16_t, access="r", mandatory=True
        )
        receiver_timeout: Final = ZCLAttributeDef(
            id=0x0009, type=t.uint16_t, access="r", mandatory=True
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class ImageUpgradeStatus(t.enum8):
    Normal = 0x00
    Download_in_progress = 0x01
    Download_complete = 0x02
    Waiting_to_upgrade = 0x03
    Count_down = 0x04
    Wait_for_more = 0x05
    Waiting_to_Upgrade_via_External_Event = 0x06


class UpgradeActivationPolicy(t.enum8):
    OTA_server_allowed = 0x00
    Out_of_band_allowed = 0x01


class UpgradeTimeoutPolicy(t.enum8):
    Apply_after_timeout = 0x00
    Do_not_apply_after_timeout = 0x01


class ImageNotifyCommand(foundation.CommandSchema):
    class PayloadType(t.enum8):
        QueryJitter = 0x00
        QueryJitter_ManufacturerCode = 0x01
        QueryJitter_ManufacturerCode_ImageType = 0x02
        QueryJitter_ManufacturerCode_ImageType_NewFileVersion = 0x03

    payload_type: None = t.StructField(type=PayloadType)
    query_jitter: t.uint8_t
    manufacturer_code: t.uint16_t = t.StructField(
        requires=(
            lambda s: s.payload_type >= s.PayloadType.QueryJitter_ManufacturerCode
        )
    )
    image_type: t.uint16_t = t.StructField(
        requires=(
            lambda s: s.payload_type
            >= s.PayloadType.QueryJitter_ManufacturerCode_ImageType
        )
    )
    new_file_version: t.uint32_t = t.StructField(
        requires=(
            lambda s: s.payload_type
            >= s.PayloadType.QueryJitter_ManufacturerCode_ImageType_NewFileVersion
        )
    )


class QueryNextImageCommand(foundation.CommandSchema):
    class FieldControl(t.bitmap8):
        HardwareVersion = 0b00000001

    field_control: None = t.StructField(type=FieldControl)
    manufacturer_code: t.uint16_t
    image_type: t.uint16_t
    current_file_version: t.uint32_t
    hardware_version: t.uint16_t = t.StructField(
        requires=(lambda s: s.field_control & s.FieldControl.HardwareVersion)
    )


class ImageBlockCommand(foundation.CommandSchema):
    class FieldControl(t.bitmap8):
        RequestNodeAddr = 0b00000001
        MinimumBlockPeriod = 0b00000010

    field_control: None = t.StructField(type=FieldControl)
    manufacturer_code: t.uint16_t
    image_type: t.uint16_t
    file_version: t.uint32_t
    file_offset: t.uint32_t
    maximum_data_size: t.uint8_t
    request_node_addr: t.EUI64 = t.StructField(
        requires=(lambda s: s.field_control & s.FieldControl.RequestNodeAddr)
    )
    minimum_block_period: t.uint16_t = t.StructField(
        requires=(lambda s: s.field_control & s.FieldControl.MinimumBlockPeriod)
    )


class ImagePageCommand(foundation.CommandSchema):
    class FieldControl(t.bitmap8):
        RequestNodeAddr = 0b00000001

    field_control: None = t.StructField(type=FieldControl)
    manufacturer_code: t.uint16_t
    image_type: t.uint16_t
    file_version: t.uint32_t
    file_offset: t.uint32_t
    maximum_data_size: t.uint8_t
    page_size: t.uint16_t
    response_spacing: t.uint16_t
    request_node_addr: t.EUI64 = t.StructField(
        requires=lambda s: s.field_control & s.FieldControl.RequestNodeAddr
    )


class ImageBlockResponseCommand(foundation.CommandSchema):
    # All responses contain at least a status
    status: foundation.Status

    # Payload with `SUCCESS` status
    manufacturer_code: t.uint16_t = t.StructField(
        requires=lambda s: s.status == foundation.Status.SUCCESS
    )
    image_type: t.uint16_t = t.StructField(
        requires=lambda s: s.status == foundation.Status.SUCCESS
    )
    file_version: t.uint32_t = t.StructField(
        requires=lambda s: s.status == foundation.Status.SUCCESS
    )
    file_offset: t.uint32_t = t.StructField(
        requires=lambda s: s.status == foundation.Status.SUCCESS
    )
    image_data: t.LVBytes = t.StructField(
        requires=lambda s: s.status == foundation.Status.SUCCESS
    )

    # Payload with `WAIT_FOR_DATA` status
    current_time: t.UTCTime = t.StructField(
        requires=lambda s: s.status == foundation.Status.WAIT_FOR_DATA
    )
    request_time: t.UTCTime = t.StructField(
        requires=lambda s: s.status == foundation.Status.WAIT_FOR_DATA
    )
    minimum_block_period: t.uint16_t = t.StructField(
        requires=lambda s: s.status == foundation.Status.WAIT_FOR_DATA
    )


class Ota(Cluster):
    ImageUpgradeStatus: Final = ImageUpgradeStatus
    UpgradeActivationPolicy: Final = UpgradeActivationPolicy
    UpgradeTimeoutPolicy: Final = UpgradeTimeoutPolicy
    ImageNotifyCommand: Final = ImageNotifyCommand
    QueryNextImageCommand: Final = QueryNextImageCommand
    ImageBlockCommand: Final = ImageBlockCommand
    ImagePageCommand: Final = ImagePageCommand
    ImageBlockResponseCommand: Final = ImageBlockResponseCommand

    cluster_id: Final[t.uint16_t] = 0x0019
    ep_attribute: Final = "ota"

    class AttributeDefs(BaseAttributeDefs):
        upgrade_server_id: Final = ZCLAttributeDef(
            id=0x0000, type=t.EUI64, access="r", mandatory=True
        )
        file_offset: Final = ZCLAttributeDef(id=0x0001, type=t.uint32_t, access="r")
        current_file_version: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint32_t, access="r"
        )
        current_zigbee_stack_version: Final = ZCLAttributeDef(
            id=0x0003, type=t.uint16_t, access="r"
        )
        downloaded_file_version: Final = ZCLAttributeDef(
            id=0x0004, type=t.uint32_t, access="r"
        )
        downloaded_zigbee_stack_version: Final = ZCLAttributeDef(
            id=0x0005, type=t.uint16_t, access="r"
        )
        image_upgrade_status: Final = ZCLAttributeDef(
            id=0x0006, type=ImageUpgradeStatus, access="r", mandatory=True
        )
        manufacturer_id: Final = ZCLAttributeDef(id=0x0007, type=t.uint16_t, access="r")
        image_type_id: Final = ZCLAttributeDef(id=0x0008, type=t.uint16_t, access="r")
        minimum_block_req_delay: Final = ZCLAttributeDef(
            id=0x0009, type=t.uint16_t, access="r"
        )
        image_stamp: Final = ZCLAttributeDef(id=0x000A, type=t.uint32_t, access="r")
        upgrade_activation_policy: Final = ZCLAttributeDef(
            id=0x000B, type=UpgradeActivationPolicy, access="r"
        )
        upgrade_timeout_policy: Final = ZCLAttributeDef(
            id=0x000C, type=UpgradeTimeoutPolicy, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        query_next_image: Final = ZCLCommandDef(
            id=0x01, schema=QueryNextImageCommand, direction=Direction.Client_to_Server
        )
        image_block: Final = ZCLCommandDef(
            id=0x03, schema=ImageBlockCommand, direction=Direction.Client_to_Server
        )
        image_page: Final = ZCLCommandDef(
            id=0x04, schema=ImagePageCommand, direction=Direction.Client_to_Server
        )
        upgrade_end: Final = ZCLCommandDef(
            id=0x06,
            schema={
                "status": foundation.Status,
                "manufacturer_code": t.uint16_t,
                "image_type": t.uint16_t,
                "file_version": t.uint32_t,
            },
            direction=Direction.Client_to_Server,
        )
        query_specific_file: Final = ZCLCommandDef(
            id=0x08,
            schema={
                "request_node_addr": t.EUI64,
                "manufacturer_code": t.uint16_t,
                "image_type": t.uint16_t,
                "file_version": t.uint32_t,
                "current_zigbee_stack_version": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )

    class ClientCommandDefs(BaseCommandDefs):
        image_notify: Final = ZCLCommandDef(
            id=0x00, schema=ImageNotifyCommand, direction=Direction.Client_to_Server
        )
        query_next_image_response: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "status": foundation.Status,
                "manufacturer_code?": t.uint16_t,
                "image_type?": t.uint16_t,
                "file_version?": t.uint32_t,
                "image_size?": t.uint32_t,
            },
            direction=Direction.Server_to_Client,
        )
        image_block_response: Final = ZCLCommandDef(
            id=0x05,
            schema=ImageBlockResponseCommand,
            direction=Direction.Server_to_Client,
        )
        upgrade_end_response: Final = ZCLCommandDef(
            id=0x07,
            schema={
                "manufacturer_code": t.uint16_t,
                "image_type": t.uint16_t,
                "file_version": t.uint32_t,
                "current_time": t.UTCTime,
                "upgrade_time": t.UTCTime,
            },
            direction=Direction.Server_to_Client,
        )
        query_specific_file_response: Final = ZCLCommandDef(
            id=0x09,
            schema={
                "status": foundation.Status,
                "manufacturer_code?": t.uint16_t,
                "image_type?": t.uint16_t,
                "file_version?": t.uint32_t,
                "image_size?": t.uint32_t,
            },
            direction=Direction.Server_to_Client,
        )

    def handle_cluster_request(
        self,
        hdr: foundation.ZCLHeader,
        args: list[Any],
        *,
        dst_addressing: AddressingMode | None = None,
    ):
        # We don't want the cluster to do anything here because it would interfere with
        # the OTA manager
        device = self.endpoint.device
        if device.ota_in_progress:
            return

        if (
            hdr.direction == foundation.Direction.Client_to_Server
            and hdr.command_id == self.ServerCommandDefs.query_next_image.id
        ):
            self.create_catching_task(
                self._handle_query_next_image(hdr, args),
            )
        elif (
            hdr.direction == foundation.Direction.Client_to_Server
            and hdr.command_id == self.ServerCommandDefs.image_block.id
        ):
            self.create_catching_task(
                self._handle_image_block_req(hdr, args),
            )

    async def _handle_query_next_image(self, hdr, cmd):
        # Always send no image available response so that the device stops asking
        await self.query_next_image_response(
            foundation.Status.NO_IMAGE_AVAILABLE, tsn=hdr.tsn
        )

        device = self.endpoint.device
        images_result = await device.application.ota.get_ota_images(device, cmd)

        device.listener_event(
            "device_ota_image_query_result",
            images_result,
            cmd,
        )

    async def _handle_image_block_req(self, hdr, cmd):
        # Abort any running firmware update (i.e. the integration is reloaded midway)
        await self.image_block_response(foundation.Status.ABORT, tsn=hdr.tsn)


class ScheduleRecord(t.Struct):
    phase_id: t.uint8_t
    scheduled_time: t.uint16_t


class PowerProfilePhase(t.Struct):
    energy_phase_id: t.uint8_t
    macro_phase_id: t.uint8_t
    expected_duration: t.uint16_t
    peak_power: t.uint16_t
    energy: t.uint16_t


class PowerProfileType(t.Struct):
    power_profile_id: t.uint8_t
    energy_phase_id: t.uint8_t
    power_profile_remote_control: t.Bool
    power_profile_state: t.uint8_t


class PowerProfile(Cluster):
    ScheduleRecord: Final = ScheduleRecord
    PowerProfilePhase: Final = PowerProfilePhase
    PowerProfile: Final = PowerProfileType

    cluster_id: Final[t.uint16_t] = 0x001A
    ep_attribute: Final = "power_profile"

    class AttributeDefs(BaseAttributeDefs):
        total_profile_num: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint8_t, access="r", mandatory=True
        )
        multiple_scheduling: Final = ZCLAttributeDef(
            id=0x0001, type=t.Bool, access="r", mandatory=True
        )
        energy_formatting: Final = ZCLAttributeDef(
            id=0x0002, type=t.bitmap8, access="r", mandatory=True
        )
        energy_remote: Final = ZCLAttributeDef(
            id=0x0003, type=t.Bool, access="r", mandatory=True
        )
        schedule_mode: Final = ZCLAttributeDef(
            id=0x0004, type=t.bitmap8, access="rwp", mandatory=True
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        power_profile_request: Final = ZCLCommandDef(
            id=0x00,
            schema={"power_profile_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        power_profile_state_request: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )
        get_power_profile_price_response: Final = ZCLCommandDef(
            id=0x02,
            schema={
                "power_profile_id": t.uint8_t,
                "currency": t.uint16_t,
                "price": t.uint32_t,
                "price_trailing_digit": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        get_overall_schedule_price_response: Final = ZCLCommandDef(
            id=0x03,
            schema={
                "currency": t.uint16_t,
                "price": t.uint32_t,
                "price_trailing_digit": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        energy_phases_schedule_notification: Final = ZCLCommandDef(
            id=0x04,
            schema={
                "power_profile_id": t.uint8_t,
                "scheduled_phases": t.LVList[ScheduleRecord],
            },
            direction=Direction.Client_to_Server,
        )
        energy_phases_schedule_response: Final = ZCLCommandDef(
            id=0x05,
            schema={
                "power_profile_id": t.uint8_t,
                "scheduled_phases": t.LVList[ScheduleRecord],
            },
            direction=Direction.Server_to_Client,
        )
        power_profile_schedule_constraints_request: Final = ZCLCommandDef(
            id=0x06,
            schema={"power_profile_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        energy_phases_schedule_state_request: Final = ZCLCommandDef(
            id=0x07,
            schema={"power_profile_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        get_power_profile_price_extended_response: Final = ZCLCommandDef(
            id=0x08,
            schema={
                "power_profile_id": t.uint8_t,
                "currency": t.uint16_t,
                "price": t.uint32_t,
                "price_trailing_digit": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )

    class ClientCommandDefs(BaseCommandDefs):
        power_profile_notification: Final = ZCLCommandDef(
            id=0x00,
            schema={
                "total_profile_num": t.uint8_t,
                "power_profile_id": t.uint8_t,
                "transfer_phases": t.LVList[PowerProfilePhase],
            },
            direction=Direction.Client_to_Server,
        )
        power_profile_response: Final = ZCLCommandDef(
            id=0x01,
            schema={
                "total_profile_num": t.uint8_t,
                "power_profile_id": t.uint8_t,
                "transfer_phases": t.LVList[PowerProfilePhase],
            },
            direction=Direction.Server_to_Client,
        )
        power_profile_state_response: Final = ZCLCommandDef(
            id=0x02,
            schema={"power_profiles": t.LVList[PowerProfileType]},
            direction=Direction.Server_to_Client,
        )
        get_power_profile_price: Final = ZCLCommandDef(
            id=0x03,
            schema={"power_profile_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        power_profile_state_notification: Final = ZCLCommandDef(
            id=0x04,
            schema={"power_profiles": t.LVList[PowerProfileType]},
            direction=Direction.Client_to_Server,
        )
        get_overall_schedule_price: Final = ZCLCommandDef(
            id=0x05, schema={}, direction=Direction.Client_to_Server
        )
        energy_phases_schedule_request: Final = ZCLCommandDef(
            id=0x06,
            schema={"power_profile_id": t.uint8_t},
            direction=Direction.Client_to_Server,
        )
        energy_phases_schedule_state_response: Final = ZCLCommandDef(
            id=0x07,
            schema={
                "power_profile_id": t.uint8_t,
                "num_scheduled_energy_phases": t.uint8_t,
            },
            direction=Direction.Server_to_Client,
        )
        energy_phases_schedule_state_notification: Final = ZCLCommandDef(
            id=0x08,
            schema={
                "power_profile_id": t.uint8_t,
                "num_scheduled_energy_phases": t.uint8_t,
            },
            direction=Direction.Client_to_Server,
        )
        power_profile_schedule_constraints_notification: Final = ZCLCommandDef(
            id=0x09,
            schema={
                "power_profile_id": t.uint8_t,
                "start_after": t.uint16_t,
                "stop_before": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )
        power_profile_schedule_constraints_response: Final = ZCLCommandDef(
            id=0x0A,
            schema={
                "power_profile_id": t.uint8_t,
                "start_after": t.uint16_t,
                "stop_before": t.uint16_t,
            },
            direction=Direction.Server_to_Client,
        )
        get_power_profile_price_extended: Final = ZCLCommandDef(
            id=0x0B,
            schema={
                "options": t.bitmap8,
                "power_profile_id": t.uint8_t,
                "power_profile_start_time?": t.uint16_t,
            },
            direction=Direction.Client_to_Server,
        )


class ApplianceControl(Cluster):
    cluster_id: Final[t.uint16_t] = 0x001B
    ep_attribute: Final = "appliance_control"

    class AttributeDefs(BaseAttributeDefs):
        start_time: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rp", mandatory=True
        )
        finish_time: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="rp", mandatory=True
        )
        remaining_time: Final = ZCLAttributeDef(id=0x0002, type=t.uint16_t, access="rp")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class PollControl(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0020
    name: Final = "Poll Control"
    ep_attribute: Final = "poll_control"

    class AttributeDefs(BaseAttributeDefs):
        checkin_interval: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint32_t, access="rw", mandatory=True
        )
        long_poll_interval: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint32_t, access="r", mandatory=True
        )
        short_poll_interval: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        fast_poll_timeout: Final = ZCLAttributeDef(
            id=0x0003, type=t.uint16_t, access="rw", mandatory=True
        )
        checkin_interval_min: Final = ZCLAttributeDef(
            id=0x0004, type=t.uint32_t, access="r"
        )
        long_poll_interval_min: Final = ZCLAttributeDef(
            id=0x0005, type=t.uint32_t, access="r"
        )
        fast_poll_timeout_max: Final = ZCLAttributeDef(
            id=0x0006, type=t.uint16_t, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR

    class ServerCommandDefs(BaseCommandDefs):
        checkin_response: Final = ZCLCommandDef(
            id=0x00,
            schema={"start_fast_polling": t.Bool, "fast_poll_timeout": t.uint16_t},
            direction=Direction.Server_to_Client,
        )
        fast_poll_stop: Final = ZCLCommandDef(
            id=0x01, schema={}, direction=Direction.Client_to_Server
        )
        set_long_poll_interval: Final = ZCLCommandDef(
            id=0x02,
            schema={"new_long_poll_interval": t.uint32_t},
            direction=Direction.Client_to_Server,
        )
        set_short_poll_interval: Final = ZCLCommandDef(
            id=0x03,
            schema={"new_short_poll_interval": t.uint16_t},
            direction=Direction.Client_to_Server,
        )

    class ClientCommandDefs(BaseCommandDefs):
        checkin: Final = ZCLCommandDef(
            id=0x0000, schema={}, direction=Direction.Client_to_Server
        )


class GreenPowerProxy(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0021
    ep_attribute: Final = "green_power"


class KeepAlive(Cluster):
    """Keep Alive cluster definition."""

    cluster_id: Final[t.uint16_t] = 0x0025
    ep_attribute: Final = "keep_alive"

    class AttributeDefs(BaseAttributeDefs):
        """Keep Alive cluster attributes."""

        tc_keep_alive_base: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint8_t, access="r", mandatory=True
        )
        tc_keep_alive_jitter: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
