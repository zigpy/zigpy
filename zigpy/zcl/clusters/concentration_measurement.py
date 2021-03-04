"""Concentration measurement"""

import zigpy.types as t
from zigpy.zcl import Cluster


class ConcentrationMeasurement:
    attributes = {
        0x0000: ("measured_value", t.single),
        0x0001: ("min_measured_value", t.single),
        0x0002: ("max_measured_value", t.single),
    }

    server_commands = {}
    client_commands = {}


class ConcentrationMeasurementCarbonMonoxide(ConcentrationMeasurement, Cluster):
    cluster_id = 0x040C
    name = "Carbon Monoxide (CO)"
    ep_attribute = "carbon_monoxide"


class ConcentrationMeasurementCarbonDioxide(ConcentrationMeasurement, Cluster):
    cluster_id = 0x040D
    name = "Carbon Dioxide (CO₂)"
    ep_attribute = "carbon_dioxide"


class ConcentrationMeasurementEthylene(ConcentrationMeasurement, Cluster):
    cluster_id = 0x040E
    name = "Ethylene (CH₂)"
    ep_attribute = "ethylene"


class ConcentrationMeasurementEthyleneOxide(ConcentrationMeasurement, Cluster):
    cluster_id = 0x040F
    name = "Ethylene Oxide (C₂H₄O)"
    ep_attribute = "ethylene_oxide"


class ConcentrationMeasurementHydrogen(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0410
    name = "Hydrogen (H)"
    ep_attribute = "hydrogen"


class ConcentrationMeasurementHydrogenSulfide(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0411
    name = "Hydrogen Sulfide (H₂S)"
    ep_attribute = "hydrogen_sulfide"


class ConcentrationMeasurementNitricOxide(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0412
    name = "Nitric Oxide (NO)"
    ep_attribute = "nitric_oxide"


class ConcentrationMeasurementNitrogenDioxide(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0413
    name = "Nitrogen Dioxide (NO₂)"
    ep_attribute = "nitrogen_dioxide"


class ConcentrationMeasurementOxygen(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0414
    name = "Oxygen (O₂)"
    ep_attribute = "oxygen"


class ConcentrationMeasurementOzone(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0415
    name = "Ozone (O₃)"
    ep_attribute = "ozone"


class ConcentrationMeasurementSulfurDioxide(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0416
    name = "Sulfur Dioxide (SO₂)"
    ep_attribute = "sulfur_dioxide"


class ConcentrationMeasurementDissolvedOxygen(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0417
    name = "Dissolved Oxygen (DO)"
    ep_attribute = "dissolved_oxygen"


class ConcentrationMeasurementBromate(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0418
    name = "Bromate"
    ep_attribute = "bromate"


class ConcentrationMeasurementChloramines(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0419
    name = "Chloramines"
    ep_attribute = "chloramines"


class ConcentrationMeasurementChlorine(ConcentrationMeasurement, Cluster):
    cluster_id = 0x041A
    name = "Chlorine"
    ep_attribute = "chlorine"


class ConcentrationMeasurementFecalColiformAndEColi(ConcentrationMeasurement, Cluster):
    """
    Percent of positive samples
    """

    cluster_id = 0x041B
    name = "Fecal coliform & E. Coli"
    ep_attribute = "fecal_coliform_and_e_coli"


class ConcentrationMeasurementFluoride(ConcentrationMeasurement, Cluster):
    cluster_id = 0x041C  # XXX: spec repeats 0x041B but this seems like a mistake
    name = "Fluoride"
    ep_attribute = "fluoride"


class ConcentrationMeasurementHaloaceticAcids(ConcentrationMeasurement, Cluster):
    cluster_id = 0x041D
    name = "Haloacetic Acids"
    ep_attribute = "haloacetic_acids"


class ConcentrationMeasurementTotalTrihalomethanes(ConcentrationMeasurement, Cluster):
    cluster_id = 0x041E
    name = "Total Trihalomethanes"
    ep_attribute = "total_trihalomethanes"


class ConcentrationMeasurementTotalColiformBacteria(ConcentrationMeasurement, Cluster):
    cluster_id = 0x041F
    name = "Total Coliform Bacteria"
    ep_attribute = "total_coliform_bacteria"


class ConcentrationMeasurementTurbidity(ConcentrationMeasurement, Cluster):
    """
    Cloudiness of particles in water where an average person would notice a 5 or higher
    """

    cluster_id = 0x0420
    name = "Turbidity"
    ep_attribute = "turbidity"


class ConcentrationMeasurementCopper(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0421
    name = "Copper"
    ep_attribute = "copper"


class ConcentrationMeasurementLead(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0422
    name = "Lead"
    ep_attribute = "lead"


class ConcentrationMeasurementManganese(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0423
    name = "Manganese"
    ep_attribute = "manganese"


class ConcentrationMeasurementSulfate(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0424
    name = "Sulfate"
    ep_attribute = "sulfate"


class ConcentrationMeasurementBromodichloromethane(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0425
    name = "Bromodichloromethane"
    ep_attribute = "bromodichloromethane"


class ConcentrationMeasurementBromoform(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0426
    name = "Bromoform"
    ep_attribute = "bromoform"


class ConcentrationMeasurementChlorodibromomethane(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0427
    name = "Chlorodibromomethane"
    ep_attribute = "chlorodibromomethane"


class ConcentrationMeasurementChloroform(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0428
    name = "Chloroform"
    ep_attribute = "chloroform"


class ConcentrationMeasurementSodium(ConcentrationMeasurement, Cluster):
    cluster_id = 0x0429
    name = "Sodium"
    ep_attribute = "sodium"


class ConcentrationMeasurementPM25(ConcentrationMeasurement, Cluster):
    """
    Particulate Matter 2.5 microns or less
    """

    cluster_id = 0x042A
    name = "PM2.5"
    ep_attribute = "pm25"


class ConcentrationMeasurementFormaldehyde(ConcentrationMeasurement, Cluster):
    cluster_id = 0x042B
    name = "Formaldehyde"
    ep_attribute = "formaldehyde"
