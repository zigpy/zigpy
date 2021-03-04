"""Measurement & Sensing Functional Domain"""

import zigpy.types as t
from zigpy.zcl import Cluster


class IlluminanceMeasurement(Cluster):
    cluster_id = 0x0400
    name = "Illuminance Measurement"
    ep_attribute = "illuminance"
    attributes = {
        # Illuminance Measurement Information
        0x0000: ("measured_value", t.uint16_t),
        0x0001: ("min_measured_value", t.uint16_t),
        0x0002: ("max_measured_value", t.uint16_t),
        0x0003: ("tolerance", t.uint16_t),
        0x0004: ("light_sensor_type", t.enum8),
    }
    server_commands = {}
    client_commands = {}


class IlluminanceLevelSensing(Cluster):
    cluster_id = 0x0401
    name = "Illuminance Level Sensing"
    ep_attribute = "illuminance_level"
    attributes = {
        # Illuminance Level Sensing Information
        0x0000: ("level_status", t.enum8),
        0x0001: ("light_sensor_type", t.enum8),
        # Illuminance Level Sensing Settings
        0x0010: ("illuminance_target_level", t.uint16_t),
    }
    server_commands = {}
    client_commands = {}


class TemperatureMeasurement(Cluster):
    cluster_id = 0x0402
    name = "Temperature Measurement"
    ep_attribute = "temperature"
    attributes = {
        # Temperature Measurement Information
        0x0000: ("measured_value", t.int16s),
        0x0001: ("min_measured_value", t.int16s),
        0x0002: ("max_measured_value", t.int16s),
        0x0003: ("tolerance", t.uint16_t),
        # 0x0010: ('min_percent_change', UNKNOWN),
        # 0x0011: ('min_absolute_change', UNKNOWN),
    }
    server_commands = {}
    client_commands = {}


class PressureMeasurement(Cluster):
    cluster_id = 0x0403
    name = "Pressure Measurement"
    ep_attribute = "pressure"
    attributes = {
        # Pressure Measurement Information
        0x0000: ("measured_value", t.int16s),
        0x0001: ("min_measured_value", t.int16s),
        0x0002: ("max_measured_value", t.int16s),
        0x0003: ("tolerance", t.uint16_t),
    }
    server_commands = {}
    client_commands = {}


class FlowMeasurement(Cluster):
    cluster_id = 0x0404
    name = "Flow Measurement"
    ep_attribute = "flow"
    attributes = {
        # Flow Measurement Information
        0x0000: ("measured_value", t.uint16_t),
        0x0001: ("min_measured_value", t.uint16_t),
        0x0002: ("max_measured_value", t.uint16_t),
        0x0003: ("tolerance", t.uint16_t),
    }
    server_commands = {}
    client_commands = {}


class RelativeHumidity(Cluster):
    cluster_id = 0x0405
    name = "Relative Humidity Measurement"
    ep_attribute = "humidity"
    attributes = {
        # Relative Humidity Measurement Information
        0x0000: ("measured_value", t.uint16_t),
        0x0001: ("min_measured_value", t.uint16_t),
        0x0002: ("max_measured_value", t.uint16_t),
        0x0003: ("tolerance", t.uint16_t),
    }
    server_commands = {}
    client_commands = {}


class OccupancySensing(Cluster):
    cluster_id = 0x0406
    name = "Occupancy Sensing"
    ep_attribute = "occupancy"
    attributes = {
        # Occupancy Sensor Information
        0x0000: ("occupancy", t.bitmap8),
        0x0001: ("occupancy_sensor_type", t.enum8),
        # PIR Configuration
        0x0010: ("pir_o_to_u_delay", t.uint16_t),
        0x0011: ("pir_u_to_o_delay", t.uint16_t),
        0x0012: ("pir_u_to_o_threshold", t.uint8_t),
        # Ultrasonic Configuration
        0x0020: ("ultrasonic_o_to_u_delay", t.uint16_t),
        0x0021: ("ultrasonic_u_to_o_delay", t.uint16_t),
        0x0022: ("ultrasonic_u_to_o_threshold", t.uint8_t),
    }
    server_commands = {}
    client_commands = {}


# TODO: 0x0407: Leaf Wetness
# TODO: 0x0408: Soil Moisture
# TODO: 0x0409: pH Measurement
# TODO: 0x040A: Electrical Conductivity
# TODO: 0x040B: Wind Speed Measurement


class _ConcentrationMixin:
    """Mixin for the common attributes of the concentration measurement clusters"""

    attributes = {
        0x0000: ("measured_value", t.Single),  # fraction of 1 (one)
        0x0001: ("min_measured_value", t.Single),
        0x0002: ("max_measured_value", t.Single),
        0x0003: ("tolerance", t.Single),
    }

    server_commands = {}
    client_commands = {}


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
