"""Measurement & Sensing Functional Domain"""

from __future__ import annotations

from typing import Final

import zigpy.types as t
from zigpy.zcl import Cluster, foundation
from zigpy.zcl.foundation import BaseAttributeDefs, ZCLAttributeDef


class LightSensorType(t.enum8):
    Photodiode = 0x00
    CMOS = 0x01
    Unknown = 0xFF


class IlluminanceMeasurement(Cluster):
    LightSensorType: Final = LightSensorType

    cluster_id: Final[t.uint16_t] = 0x0400
    name: Final = "Illuminance Measurement"
    ep_attribute: Final = "illuminance"

    class AttributeDefs(BaseAttributeDefs):
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rp", mandatory=True
        )
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="r")
        light_sensor_type: Final = ZCLAttributeDef(
            id=0x0004, type=LightSensorType, access="r"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class LevelStatus(t.enum8):
    Illuminance_On_Target = 0x00
    Illuminance_Below_Target = 0x01
    Illuminance_Above_Target = 0x02


class IlluminanceLevelSensing(Cluster):
    LevelStatus: Final = LevelStatus
    LightSensorType: Final = LightSensorType

    cluster_id: Final[t.uint16_t] = 0x0401
    name: Final = "Illuminance Level Sensing"
    ep_attribute: Final = "illuminance_level"

    class AttributeDefs(BaseAttributeDefs):
        level_status: Final = ZCLAttributeDef(
            id=0x0000, type=LevelStatus, access="r", mandatory=True
        )
        light_sensor_type: Final = ZCLAttributeDef(
            id=0x0001, type=LightSensorType, access="r"
        )
        # Illuminance Level Sensing Settings
        illuminance_target_level: Final = ZCLAttributeDef(
            id=0x0010, type=t.uint16_t, access="rw", mandatory=True
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class TemperatureMeasurement(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0402
    name: Final = "Temperature Measurement"
    ep_attribute: Final = "temperature"

    class AttributeDefs(BaseAttributeDefs):
        # Temperature Measurement Information
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.int16s, access="rp", mandatory=True
        )
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.int16s, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.int16s, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="r")
        # 0x0010: ('min_percent_change', UNKNOWN),
        # 0x0011: ('min_absolute_change', UNKNOWN),
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class PressureMeasurement(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0403
    name: Final = "Pressure Measurement"
    ep_attribute: Final = "pressure"

    class AttributeDefs(BaseAttributeDefs):
        # Pressure Measurement Information
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.int16s, access="rp", mandatory=True
        )
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.int16s, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.int16s, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="r")
        # Extended attribute set
        scaled_value: Final = ZCLAttributeDef(id=0x0010, type=t.int16s, access="r")
        min_scaled_value: Final = ZCLAttributeDef(id=0x0011, type=t.int16s, access="r")
        max_scaled_value: Final = ZCLAttributeDef(id=0x0012, type=t.int16s, access="r")
        scaled_tolerance: Final = ZCLAttributeDef(
            id=0x0013, type=t.uint16_t, access="r"
        )
        scale: Final = ZCLAttributeDef(id=0x0014, type=t.int8s, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class FlowMeasurement(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0404
    name: Final = "Flow Measurement"
    ep_attribute: Final = "flow"

    class AttributeDefs(BaseAttributeDefs):
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rp", mandatory=True
        )
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class RelativeHumidity(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0405
    name: Final = "Relative Humidity Measurement"
    ep_attribute: Final = "humidity"

    class AttributeDefs(BaseAttributeDefs):
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rp", mandatory=True
        )
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


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


class OccupancySensing(Cluster):
    Occupancy: Final = Occupancy
    OccupancySensorType: Final = OccupancySensorType
    OccupancySensorTypeBitmap: Final = OccupancySensorTypeBitmap

    cluster_id: Final[t.uint16_t] = 0x0406
    name: Final = "Occupancy Sensing"
    ep_attribute: Final = "occupancy"

    class AttributeDefs(BaseAttributeDefs):
        # Occupancy Sensor Information
        occupancy: Final = ZCLAttributeDef(
            id=0x0000, type=Occupancy, access="rp", mandatory=True
        )
        occupancy_sensor_type_bitmap: Final = ZCLAttributeDef(
            id=0x0001, type=t.bitmap8, access="r", mandatory=True
        )
        # PIR Configuration
        pir_o_to_u_delay: Final = ZCLAttributeDef(
            id=0x0010, type=t.uint16_t, access="rw"
        )
        pir_u_to_o_delay: Final = ZCLAttributeDef(
            id=0x0011, type=t.uint16_t, access="rw"
        )
        pir_u_to_o_threshold: Final = ZCLAttributeDef(
            id=0x0012, type=t.uint8_t, access="rw"
        )
        # Ultrasonic Configuration
        ultrasonic_o_to_u_delay: Final = ZCLAttributeDef(
            id=0x0020, type=t.uint16_t, access="rw"
        )
        ultrasonic_u_to_o_delay: Final = ZCLAttributeDef(
            id=0x0021, type=t.uint16_t, access="rw"
        )
        ultrasonic_u_to_o_threshold: Final = ZCLAttributeDef(
            id=0x0022, type=t.uint8_t, access="rw"
        )
        # Physical Contact Configuration
        physical_contact_o_to_u_delay: Final = ZCLAttributeDef(
            id=0x0030, type=t.uint16_t, access="rw"
        )
        physical_contact_u_to_o_delay: Final = ZCLAttributeDef(
            id=0x0031, type=t.uint16_t, access="rw"
        )
        physical_contact_u_to_o_threshold: Final = ZCLAttributeDef(
            id=0x0032, type=t.uint8_t, access="rw"
        )
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class LeafWetness(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0407
    name: Final = "Leaf Wetness Measurement"
    ep_attribute: Final = "leaf_wetness"

    class AttributeDefs(BaseAttributeDefs):
        # Leaf Wetness Measurement Information
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rp", mandatory=True
        )
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class SoilMoisture(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0408
    name: Final = "Soil Moisture Measurement"
    ep_attribute: Final = "soil_moisture"

    class AttributeDefs(BaseAttributeDefs):
        # Soil Moisture Measurement Information
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rp", mandatory=True
        )
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class PH(Cluster):
    cluster_id: Final[t.uint16_t] = 0x0409
    name: Final = "pH Measurement"
    ep_attribute: Final = "ph"

    class AttributeDefs(BaseAttributeDefs):
        # pH Measurement Information
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rp", mandatory=True
        )
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class ElectricalConductivity(Cluster):
    cluster_id: Final[t.uint16_t] = 0x040A
    name: Final = "Electrical Conductivity"
    ep_attribute: Final = "electrical_conductivity"

    class AttributeDefs(BaseAttributeDefs):
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rp", mandatory=True
        )
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class WindSpeed(Cluster):
    cluster_id: Final[t.uint16_t] = 0x040B
    name: Final = "Wind Speed Measurement"
    ep_attribute: Final = "wind_speed"

    class AttributeDefs(BaseAttributeDefs):
        # Wind Speed Measurement Information
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, access="rp", mandatory=True
        )
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.uint16_t, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class _ConcentrationMixin:
    """Mixin for the common attributes of the concentration measurement clusters"""

    class AttributeDefs(BaseAttributeDefs):
        measured_value: Final = ZCLAttributeDef(
            id=0x0000, type=t.Single, access="rp", mandatory=True
        )  # fraction of 1 (one)
        min_measured_value: Final = ZCLAttributeDef(
            id=0x0001, type=t.Single, access="r", mandatory=True
        )
        max_measured_value: Final = ZCLAttributeDef(
            id=0x0002, type=t.Single, access="r", mandatory=True
        )
        tolerance: Final = ZCLAttributeDef(id=0x0003, type=t.Single, access="r")
        cluster_revision: Final = foundation.ZCL_CLUSTER_REVISION_ATTR
        reporting_status: Final = foundation.ZCL_REPORTING_STATUS_ATTR


class CarbonMonoxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x040C
    name: Final = "Carbon Monoxide (CO) Concentration"
    ep_attribute: Final = "carbon_monoxide_concentration"


class CarbonDioxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x040D
    name: Final = "Carbon Dioxide (CO₂) Concentration"
    ep_attribute: Final = "carbon_dioxide_concentration"


class EthyleneConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x040E
    name: Final = "Ethylene (CH₂) Concentration"
    ep_attribute: Final = "ethylene_concentration"


class EthyleneOxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x040F
    name: Final = "Ethylene Oxide (C₂H₄O) Concentration"
    ep_attribute: Final = "ethylene_oxide_concentration"


class HydrogenConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0410
    name: Final = "Hydrogen (H) Concentration"
    ep_attribute: Final = "hydrogen_concentration"


class HydrogenSulfideConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0411
    name: Final = "Hydrogen Sulfide (H₂S) Concentration"
    ep_attribute: Final = "hydrogen_sulfide_concentration"


class NitricOxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0412
    name: Final = "Nitric Oxide (NO) Concentration"
    ep_attribute: Final = "nitric_oxide_concentration"


class NitrogenDioxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0413
    name: Final = "Nitrogen Dioxide (NO₂) Concentration"
    ep_attribute: Final = "nitrogen_dioxide_concentration"


class OxygenConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0414
    name: Final = "Oxygen (O₂) Concentration"
    ep_attribute: Final = "oxygen_concentration"


class OzoneConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0415
    name: Final = "Ozone (O₃) Concentration"
    ep_attribute: Final = "ozone_concentration"


class SulfurDioxideConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0416
    name: Final = "Sulfur Dioxide (SO₂) Concentration"
    ep_attribute: Final = "sulfur_dioxide_concentration"


class DissolvedOxygenConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0417
    name: Final = "Dissolved Oxygen (DO) Concentration"
    ep_attribute: Final = "dissolved_oxygen_concentration"


class BromateConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0418
    name: Final = "Bromate Concentration"
    ep_attribute: Final = "bromate_concentration"


class ChloraminesConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0419
    name: Final = "Chloramines Concentration"
    ep_attribute: Final = "chloramines_concentration"


class ChlorineConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x041A
    name: Final = "Chlorine Concentration"
    ep_attribute: Final = "chlorine_concentration"


class FecalColiformAndEColiFraction(_ConcentrationMixin, Cluster):
    """Percent of positive samples"""

    cluster_id: Final[t.uint16_t] = 0x041B
    name: Final = "Fecal coliform & E. Coli Fraction"
    ep_attribute: Final = "fecal_coliform_and_e_coli_fraction"


class FluorideConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = (
        0x041C  # XXX: spec repeats 0x041B but this seems like a mistake
    )
    name: Final = "Fluoride Concentration"
    ep_attribute: Final = "fluoride_concentration"


class HaloaceticAcidsConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x041D
    name: Final = "Haloacetic Acids Concentration"
    ep_attribute: Final = "haloacetic_acids_concentration"


class TotalTrihalomethanesConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x041E
    name: Final = "Total Trihalomethanes Concentration"
    ep_attribute: Final = "total_trihalomethanes_concentration"


class TotalColiformBacteriaFraction(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x041F
    name: Final = "Total Coliform Bacteria Fraction"
    ep_attribute: Final = "total_coliform_bacteria_fraction"


# XXX: is this a concentration? What are the units?
class Turbidity(_ConcentrationMixin, Cluster):
    """Cloudiness of particles in water where an average person would notice a 5 or higher"""

    cluster_id: Final[t.uint16_t] = 0x0420
    name: Final = "Turbidity"
    ep_attribute: Final = "turbidity"


class CopperConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0421
    name: Final = "Copper Concentration"
    ep_attribute: Final = "copper_concentration"


class LeadConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0422
    name: Final = "Lead Concentration"
    ep_attribute: Final = "lead_concentration"


class ManganeseConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0423
    name: Final = "Manganese Concentration"
    ep_attribute: Final = "manganese_concentration"


class SulfateConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0424
    name: Final = "Sulfate Concentration"
    ep_attribute: Final = "sulfate_concentration"


class BromodichloromethaneConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0425
    name: Final = "Bromodichloromethane Concentration"
    ep_attribute: Final = "bromodichloromethane_concentration"


class BromoformConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0426
    name: Final = "Bromoform Concentration"
    ep_attribute: Final = "bromoform_concentration"


class ChlorodibromomethaneConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0427
    name: Final = "Chlorodibromomethane Concentration"
    ep_attribute: Final = "chlorodibromomethane_concentration"


class ChloroformConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0428
    name: Final = "Chloroform Concentration"
    ep_attribute: Final = "chloroform_concentration"


class SodiumConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x0429
    name: Final = "Sodium Concentration"
    ep_attribute: Final = "sodium_concentration"


# XXX: is this a concentration? What are the units?
class PM25(_ConcentrationMixin, Cluster):
    """Particulate Matter 2.5 microns or less"""

    cluster_id: Final[t.uint16_t] = 0x042A
    name: Final = "PM2.5"
    ep_attribute: Final = "pm25"


class FormaldehydeConcentration(_ConcentrationMixin, Cluster):
    cluster_id: Final[t.uint16_t] = 0x042B
    name: Final = "Formaldehyde Concentration"
    ep_attribute: Final = "formaldehyde_concentration"
