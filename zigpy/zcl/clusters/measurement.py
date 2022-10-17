"""Measurement & Sensing Functional Domain"""

from __future__ import annotations

import zigpy.types as t
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import ZCLAttributeDef, ZCLCommandDef


class LightSensorType(t.enum8):
    Photodiode = 0x00
    CMOS = 0x01
    Unknown = 0xFF


class IlluminanceMeasurement(Cluster):
    cluster_id = 0x0400
    name = "Illuminance Measurement"
    ep_attribute = "illuminance"

    LightSensorType = LightSensorType

    attributes: dict[int, ZCLAttributeDef] = {
        # Illuminance Measurement Information
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.uint16_t, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.uint16_t, access="r"),
        0x0004: ZCLAttributeDef("light_sensor_type", type=LightSensorType, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class IlluminanceLevelSensing(Cluster):
    cluster_id = 0x0401
    name = "Illuminance Level Sensing"
    ep_attribute = "illuminance_level"

    class LevelStatus(t.enum8):
        Illuminance_On_Target = 0x00
        Illuminance_Below_Target = 0x01
        Illuminance_Above_Target = 0x02

    LightSensorType = LightSensorType

    attributes: dict[int, ZCLAttributeDef] = {
        # Illuminance Level Sensing Information
        0x0000: ZCLAttributeDef(
            "level_status", type=LevelStatus, access="r", mandatory=True
        ),
        0x0001: ZCLAttributeDef("light_sensor_type", type=LightSensorType, access="r"),
        # Illuminance Level Sensing Settings
        0x0010: ZCLAttributeDef(
            "illuminance_target_level", type=t.uint16_t, access="rw", mandatory=True
        ),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class TemperatureMeasurement(Cluster):
    cluster_id = 0x0402
    name = "Temperature Measurement"
    ep_attribute = "temperature"
    attributes: dict[int, ZCLAttributeDef] = {
        # Temperature Measurement Information
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.int16s, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.int16s, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.int16s, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.uint16_t, access="r"),
        # 0x0010: ('min_percent_change', UNKNOWN),
        # 0x0011: ('min_absolute_change', UNKNOWN),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class PressureMeasurement(Cluster):
    cluster_id = 0x0403
    name = "Pressure Measurement"
    ep_attribute = "pressure"
    attributes: dict[int, ZCLAttributeDef] = {
        # Pressure Measurement Information
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.int16s, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.int16s, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.int16s, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.uint16_t, access="r"),
        # Extended attribute set
        0x0010: ZCLAttributeDef("scaled_value", type=t.int16s, access="r"),
        0x0011: ZCLAttributeDef("min_scaled_value", type=t.int16s, access="r"),
        0x0012: ZCLAttributeDef("max_scaled_value", type=t.int16s, access="r"),
        0x0013: ZCLAttributeDef("scaled_tolerance", type=t.uint16_t, access="r"),
        0x0014: ZCLAttributeDef("scale", type=t.int8s, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class FlowMeasurement(Cluster):
    cluster_id = 0x0404
    name = "Flow Measurement"
    ep_attribute = "flow"
    attributes: dict[int, ZCLAttributeDef] = {
        # Flow Measurement Information
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.uint16_t, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.uint16_t, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class RelativeHumidity(Cluster):
    cluster_id = 0x0405
    name = "Relative Humidity Measurement"
    ep_attribute = "humidity"
    attributes: dict[int, ZCLAttributeDef] = {
        # Relative Humidity Measurement Information
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.uint16_t, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.uint16_t, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class OccupancySensing(Cluster):
    cluster_id = 0x0406
    name = "Occupancy Sensing"
    ep_attribute = "occupancy"

    class Occupancy(t.bitmap8):
        Unoccupied = 0b00000000
        Occupied = 0b00000001

    class OccupancySensorType(t.enum8):
        PIR = 0x00
        Ultrasonic = 0x01
        PIR_and_Ultrasonic = 0x02
        Physical_Contact = 0x03

    class OccupancySensorTypeBitmap(t.bitmap8):
        PIR = 0b00000001
        Ultrasonic = 0b00000010
        Physical_Contact = 0b00000100

    attributes: dict[int, ZCLAttributeDef] = {
        # Occupancy Sensor Information
        0x0000: ZCLAttributeDef(
            "occupancy", type=Occupancy, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "occupancy_sensor_type_bitmap", type=t.bitmap8, access="r", mandatory=True
        ),
        # PIR Configuration
        0x0010: ZCLAttributeDef("pir_o_to_u_delay", type=t.uint16_t, access="rw"),
        0x0011: ZCLAttributeDef("pir_u_to_o_delay", type=t.uint16_t, access="rw"),
        0x0012: ZCLAttributeDef("pir_u_to_o_threshold", type=t.uint8_t, access="rw"),
        # Ultrasonic Configuration
        0x0020: ZCLAttributeDef(
            "ultrasonic_o_to_u_delay", type=t.uint16_t, access="rw"
        ),
        0x0021: ZCLAttributeDef(
            "ultrasonic_u_to_o_delay", type=t.uint16_t, access="rw"
        ),
        0x0022: ZCLAttributeDef(
            "ultrasonic_u_to_o_threshold", type=t.uint8_t, access="rw"
        ),
        # Physical Contact Configuration
        0x0030: ZCLAttributeDef(
            "physical_contact_o_to_u_delay", type=t.uint16_t, access="rw"
        ),
        0x0031: ZCLAttributeDef(
            "physical_contact_u_to_o_delay", type=t.uint16_t, access="rw"
        ),
        0x0032: ZCLAttributeDef(
            "physical_contact_u_to_o_threshold", type=t.uint8_t, access="rw"
        ),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class LeafWetness(Cluster):
    cluster_id = 0x0407
    name = "Leaf Wetness Measurement"
    ep_attribute = "leaf_wetness"
    attributes: dict[int, ZCLAttributeDef] = {
        # Leaf Wetness Measurement Information
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.uint16_t, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.uint16_t, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class SoilMoisture(Cluster):
    cluster_id = 0x0408
    name = "Soil Moisture Measurement"
    ep_attribute = "soil_moisture"
    attributes: dict[int, ZCLAttributeDef] = {
        # Soil Moisture Measurement Information
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.uint16_t, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.uint16_t, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class PH(Cluster):
    cluster_id = 0x0409
    name = "pH Measurement"
    ep_attribute = "ph"
    attributes: dict[int, ZCLAttributeDef] = {
        # pH Measurement Information
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.uint16_t, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.uint16_t, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class ElectricalConductivity(Cluster):
    cluster_id = 0x040A
    name = "Electrical Conductivity"
    ep_attribute = "electrical_conductivity"
    attributes: dict[int, ZCLAttributeDef] = {
        # Electrical Conductivity Information
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.uint16_t, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.uint16_t, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class WindSpeed(Cluster):
    cluster_id = 0x040B
    name = "Wind Speed Measurement"
    ep_attribute = "wind_speed"
    attributes: dict[int, ZCLAttributeDef] = {
        # Wind Speed Measurement Information
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.uint16_t, access="rp", mandatory=True
        ),
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.uint16_t, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.uint16_t, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }
    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class _ConcentrationMixin:
    """Mixin for the common attributes of the concentration measurement clusters"""

    attributes: dict[int, ZCLAttributeDef] = {
        0x0000: ZCLAttributeDef(
            "measured_value", type=t.Single, access="rp", mandatory=True
        ),  # fraction of 1 (one)
        0x0001: ZCLAttributeDef(
            "min_measured_value", type=t.Single, access="r", mandatory=True
        ),
        0x0002: ZCLAttributeDef(
            "max_measured_value", type=t.Single, access="r", mandatory=True
        ),
        0x0003: ZCLAttributeDef("tolerance", type=t.Single, access="r"),
        0xFFFD: foundation.ZCL_CLUSTER_REVISION_ATTR,
        0xFFFE: foundation.ZCL_REPORTING_STATUS_ATTR,
    }

    server_commands: dict[int, ZCLCommandDef] = {}
    client_commands: dict[int, ZCLCommandDef] = {}


class CarbonMonoxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x040C
    name = "Carbon Monoxide (CO) Concentration"
    ep_attribute = "carbon_monoxide_concentration"


class CarbonDioxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x040D
    name = "Carbon Dioxide (CO₂) Concentration"
    ep_attribute = "carbon_dioxide_concentration"


class EthyleneConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x040E
    name = "Ethylene (CH₂) Concentration"
    ep_attribute = "ethylene_concentration"


class EthyleneOxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x040F
    name = "Ethylene Oxide (C₂H₄O) Concentration"
    ep_attribute = "ethylene_oxide_concentration"


class HydrogenConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0410
    name = "Hydrogen (H) Concentration"
    ep_attribute = "hydrogen_concentration"


class HydrogenSulfideConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0411
    name = "Hydrogen Sulfide (H₂S) Concentration"
    ep_attribute = "hydrogen_sulfide_concentration"


class NitricOxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0412
    name = "Nitric Oxide (NO) Concentration"
    ep_attribute = "nitric_oxide_concentration"


class NitrogenDioxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0413
    name = "Nitrogen Dioxide (NO₂) Concentration"
    ep_attribute = "nitrogen_dioxide_concentration"


class OxygenConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0414
    name = "Oxygen (O₂) Concentration"
    ep_attribute = "oxygen_concentration"


class OzoneConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0415
    name = "Ozone (O₃) Concentration"
    ep_attribute = "ozone_concentration"


class SulfurDioxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0416
    name = "Sulfur Dioxide (SO₂) Concentration"
    ep_attribute = "sulfur_dioxide_concentration"


class DissolvedOxygenConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0417
    name = "Dissolved Oxygen (DO) Concentration"
    ep_attribute = "dissolved_oxygen_concentration"


class BromateConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0418
    name = "Bromate Concentration"
    ep_attribute = "bromate_concentration"


class ChloraminesConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0419
    name = "Chloramines Concentration"
    ep_attribute = "chloramines_concentration"


class ChlorineConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x041A
    name = "Chlorine Concentration"
    ep_attribute = "chlorine_concentration"


class FecalColiformAndEColiFraction(_ConcentrationMixin, Cluster):
    """
    Percent of positive samples
    """

    cluster_id = 0x041B
    name = "Fecal coliform & E. Coli Fraction"
    ep_attribute = "fecal_coliform_and_e_coli_fraction"


class FluorideConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x041C  # XXX: spec repeats 0x041B but this seems like a mistake
    name = "Fluoride Concentration"
    ep_attribute = "fluoride_concentration"


class HaloaceticAcidsConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x041D
    name = "Haloacetic Acids Concentration"
    ep_attribute = "haloacetic_acids_concentration"


class TotalTrihalomethanesConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x041E
    name = "Total Trihalomethanes Concentration"
    ep_attribute = "total_trihalomethanes_concentration"


class TotalColiformBacteriaFraction(_ConcentrationMixin, Cluster):
    cluster_id = 0x041F
    name = "Total Coliform Bacteria Fraction"
    ep_attribute = "total_coliform_bacteria_fraction"


# XXX: is this a concentration? What are the units?
class Turbidity(_ConcentrationMixin, Cluster):
    """
    Cloudiness of particles in water where an average person would notice a 5 or higher
    """

    cluster_id = 0x0420
    name = "Turbidity"
    ep_attribute = "turbidity"


class CopperConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0421
    name = "Copper Concentration"
    ep_attribute = "copper_concentration"


class LeadConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0422
    name = "Lead Concentration"
    ep_attribute = "lead_concentration"


class ManganeseConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0423
    name = "Manganese Concentration"
    ep_attribute = "manganese_concentration"


class SulfateConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0424
    name = "Sulfate Concentration"
    ep_attribute = "sulfate_concentration"


class BromodichloromethaneConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0425
    name = "Bromodichloromethane Concentration"
    ep_attribute = "bromodichloromethane_concentration"


class BromoformConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0426
    name = "Bromoform Concentration"
    ep_attribute = "bromoform_concentration"


class ChlorodibromomethaneConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0427
    name = "Chlorodibromomethane Concentration"
    ep_attribute = "chlorodibromomethane_concentration"


class ChloroformConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0428
    name = "Chloroform Concentration"
    ep_attribute = "chloroform_concentration"


class SodiumConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x0429
    name = "Sodium Concentration"
    ep_attribute = "sodium_concentration"


# XXX: is this a concentration? What are the units?
class PM25(_ConcentrationMixin, Cluster):
    """
    Particulate Matter 2.5 microns or less
    """

    cluster_id = 0x042A
    name = "PM2.5"
    ep_attribute = "pm25"


class FormaldehydeConcentration(_ConcentrationMixin, Cluster):
    cluster_id = 0x042B
    name = "Formaldehyde Concentration"
    ep_attribute = "formaldehyde_concentration"
