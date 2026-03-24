"""Homeassistant specific quirks v2 things."""

from enum import StrEnum
from typing import Final


class EntityType(StrEnum):
    """Entity type."""

    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"
    STANDARD = "standard"


class EntityPlatform(StrEnum):
    """Entity platform."""

    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    NUMBER = "number"
    SENSOR = "sensor"
    SELECT = "select"
    SWITCH = "switch"


# #### UNITS OF MEASUREMENT ####
# Apparent power units
class UnitOfApparentPower(StrEnum):
    """Apparent power units."""

    MILLIVOLT_AMPERE = "mVA"
    VOLT_AMPERE = "VA"
    KILO_VOLT_AMPERE = "kVA"


# Power units
class UnitOfPower(StrEnum):
    """Power units."""

    MILLIWATT = "mW"
    WATT = "W"
    KILO_WATT = "kW"
    MEGA_WATT = "MW"
    GIGA_WATT = "GW"
    TERA_WATT = "TW"
    BTU_PER_HOUR = "BTU/h"


# Reactive power units
class UnitOfReactivePower(StrEnum):
    """Reactive power units."""

    MILLIVOLT_AMPERE_REACTIVE = "mvar"
    VOLT_AMPERE_REACTIVE = "var"
    KILO_VOLT_AMPERE_REACTIVE = "kvar"


# Energy units
class UnitOfEnergy(StrEnum):
    """Energy units."""

    JOULE = "J"
    KILO_JOULE = "kJ"
    MEGA_JOULE = "MJ"
    GIGA_JOULE = "GJ"
    MILLIWATT_HOUR = "mWh"
    WATT_HOUR = "Wh"
    KILO_WATT_HOUR = "kWh"
    MEGA_WATT_HOUR = "MWh"
    GIGA_WATT_HOUR = "GWh"
    TERA_WATT_HOUR = "TWh"
    CALORIE = "cal"
    KILO_CALORIE = "kcal"
    MEGA_CALORIE = "Mcal"
    GIGA_CALORIE = "Gcal"


# Reactive energy units
class UnitOfReactiveEnergy(StrEnum):
    """Reactive energy units."""

    VOLT_AMPERE_REACTIVE_HOUR = "varh"
    KILO_VOLT_AMPERE_REACTIVE_HOUR = "kvarh"


# Energy Distance units
class UnitOfEnergyDistance(StrEnum):
    """Energy Distance units."""

    KILO_WATT_HOUR_PER_100_KM = "kWh/100km"
    WATT_HOUR_PER_KM = "Wh/km"
    MILES_PER_KILO_WATT_HOUR = "mi/kWh"
    KM_PER_KILO_WATT_HOUR = "km/kWh"


# Electric_current units
class UnitOfElectricCurrent(StrEnum):
    """Electric current units."""

    MILLIAMPERE = "mA"
    AMPERE = "A"


# Electric_potential units
class UnitOfElectricPotential(StrEnum):
    """Electric potential units."""

    MICROVOLT = "μV"
    MILLIVOLT = "mV"
    VOLT = "V"
    KILOVOLT = "kV"
    MEGAVOLT = "MV"


# Degree units
DEGREE: Final = "°"

# Currency units
CURRENCY_EURO: Final = "€"
CURRENCY_DOLLAR: Final = "$"
CURRENCY_CENT: Final = "¢"


# Temperature units
class UnitOfTemperature(StrEnum):
    """Temperature units."""

    CELSIUS = "°C"
    FAHRENHEIT = "°F"
    KELVIN = "K"


# Time units
class UnitOfTime(StrEnum):
    """Time units."""

    MICROSECONDS = "μs"
    MILLISECONDS = "ms"
    SECONDS = "s"
    MINUTES = "min"
    HOURS = "h"
    DAYS = "d"
    WEEKS = "w"
    MONTHS = "m"
    YEARS = "y"


# Length units
class UnitOfLength(StrEnum):
    """Length units."""

    MILLIMETERS = "mm"
    CENTIMETERS = "cm"
    METERS = "m"
    KILOMETERS = "km"
    INCHES = "in"
    FEET = "ft"
    YARDS = "yd"
    MILES = "mi"
    NAUTICAL_MILES = "nmi"


# Frequency units
class UnitOfFrequency(StrEnum):
    """Frequency units."""

    HERTZ = "Hz"
    KILOHERTZ = "kHz"
    MEGAHERTZ = "MHz"
    GIGAHERTZ = "GHz"


# Pressure units
class UnitOfPressure(StrEnum):
    """Pressure units."""

    MILLIPASCAL = "mPa"
    PA = "Pa"
    HPA = "hPa"
    KPA = "kPa"
    BAR = "bar"
    CBAR = "cbar"
    MBAR = "mbar"
    MMHG = "mmHg"
    INHG = "inHg"
    INH2O = "inH₂O"
    PSI = "psi"


# Sound pressure units
class UnitOfSoundPressure(StrEnum):
    """Sound pressure units."""

    DECIBEL = "dB"
    WEIGHTED_DECIBEL_A = "dBA"


# Volume units
class UnitOfVolume(StrEnum):
    """Volume units."""

    CUBIC_FEET = "ft³"
    CENTUM_CUBIC_FEET = "CCF"
    MILLE_CUBIC_FEET = "MCF"
    CUBIC_METERS = "m³"
    LITERS = "L"
    MILLILITERS = "mL"
    GALLONS = "gal"
    """Assumed to be US gallons in conversion utilities.

    British/Imperial gallons are not yet supported"""
    FLUID_OUNCES = "fl. oz."
    """Assumed to be US fluid ounces in conversion utilities.

    British/Imperial fluid ounces are not yet supported"""


# Volume Flow Rate units
class UnitOfVolumeFlowRate(StrEnum):
    """Volume flow rate units."""

    CUBIC_METERS_PER_HOUR = "m³/h"
    CUBIC_METERS_PER_MINUTE = "m³/min"
    CUBIC_METERS_PER_SECOND = "m³/s"
    CUBIC_FEET_PER_MINUTE = "ft³/min"
    LITERS_PER_HOUR = "L/h"
    LITERS_PER_MINUTE = "L/min"
    LITERS_PER_SECOND = "L/s"
    GALLONS_PER_HOUR = "gal/h"
    GALLONS_PER_MINUTE = "gal/min"
    GALLONS_PER_DAY = "gal/d"
    MILLILITERS_PER_SECOND = "mL/s"


class UnitOfArea(StrEnum):
    """Area units."""

    SQUARE_METERS = "m²"
    SQUARE_CENTIMETERS = "cm²"
    SQUARE_KILOMETERS = "km²"
    SQUARE_MILLIMETERS = "mm²"
    SQUARE_INCHES = "in²"
    SQUARE_FEET = "ft²"
    SQUARE_YARDS = "yd²"
    SQUARE_MILES = "mi²"
    ACRES = "ac"
    HECTARES = "ha"


# Mass units
class UnitOfMass(StrEnum):
    """Mass units."""

    GRAMS = "g"
    KILOGRAMS = "kg"
    MILLIGRAMS = "mg"
    MICROGRAMS = "μg"
    OUNCES = "oz"
    POUNDS = "lb"
    STONES = "st"


class UnitOfConductivity(StrEnum):
    """Conductivity units."""

    SIEMENS_PER_CM = "S/cm"
    MICROSIEMENS_PER_CM = "μS/cm"
    MILLISIEMENS_PER_CM = "mS/cm"


# Light units
LIGHT_LUX: Final = "lx"

# UV Index units
UV_INDEX: Final = "UV index"

# Percentage units
PERCENTAGE: Final = "%"

# Rotational speed units
REVOLUTIONS_PER_MINUTE: Final = "rpm"


# Irradiance units
class UnitOfIrradiance(StrEnum):
    """Irradiance units."""

    WATTS_PER_SQUARE_METER = "W/m²"
    BTUS_PER_HOUR_SQUARE_FOOT = "BTU/(h⋅ft²)"


class UnitOfVolumetricFlux(StrEnum):
    """Volumetric flux, commonly used for precipitation intensity.

    The derivation of these units is a volume of rain amassing in a container
    with constant cross section in a given time
    """

    INCHES_PER_DAY = "in/d"
    """Derived from in³/(in²⋅d)"""

    INCHES_PER_HOUR = "in/h"
    """Derived from in³/(in²⋅h)"""

    MILLIMETERS_PER_DAY = "mm/d"
    """Derived from mm³/(mm²⋅d)"""

    MILLIMETERS_PER_HOUR = "mm/h"
    """Derived from mm³/(mm²⋅h)"""


class UnitOfPrecipitationDepth(StrEnum):
    """Precipitation depth.

    The derivation of these units is a volume of rain amassing in a container
    with constant cross section
    """

    INCHES = "in"
    """Derived from in³/in²"""

    MILLIMETERS = "mm"
    """Derived from mm³/mm²"""

    CENTIMETERS = "cm"
    """Derived from cm³/cm²"""


# Concentration units
CONCENTRATION_GRAMS_PER_CUBIC_METER: Final = "g/m³"
CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER: Final = "mg/m³"
CONCENTRATION_MICROGRAMS_PER_CUBIC_METER: Final = "μg/m³"
CONCENTRATION_MICROGRAMS_PER_CUBIC_FOOT: Final = "μg/ft³"
CONCENTRATION_PARTS_PER_CUBIC_METER: Final = "p/m³"
CONCENTRATION_PARTS_PER_MILLION: Final = "ppm"
CONCENTRATION_PARTS_PER_BILLION: Final = "ppb"


class UnitOfBloodGlucoseConcentration(StrEnum):
    """Blood glucose concentration units."""

    MILLIGRAMS_PER_DECILITER = "mg/dL"
    MILLIMOLE_PER_LITER = "mmol/L"


# Speed units
class UnitOfSpeed(StrEnum):
    """Speed units."""

    BEAUFORT = "Beaufort"
    FEET_PER_SECOND = "ft/s"
    INCHES_PER_SECOND = "in/s"
    METERS_PER_MINUTE = "m/min"
    METERS_PER_SECOND = "m/s"
    KILOMETERS_PER_HOUR = "km/h"
    KNOTS = "kn"
    MILES_PER_HOUR = "mph"
    MILLIMETERS_PER_SECOND = "mm/s"


# Signal_strength units
SIGNAL_STRENGTH_DECIBELS: Final = "dB"
SIGNAL_STRENGTH_DECIBELS_MILLIWATT: Final = "dBm"


# Data units
class UnitOfInformation(StrEnum):
    """Information units."""

    BITS = "bit"
    KILOBITS = "kbit"
    MEGABITS = "Mbit"
    GIGABITS = "Gbit"
    BYTES = "B"
    KILOBYTES = "kB"
    MEGABYTES = "MB"
    GIGABYTES = "GB"
    TERABYTES = "TB"
    PETABYTES = "PB"
    EXABYTES = "EB"
    ZETTABYTES = "ZB"
    YOTTABYTES = "YB"
    KIBIBYTES = "KiB"
    MEBIBYTES = "MiB"
    GIBIBYTES = "GiB"
    TEBIBYTES = "TiB"
    PEBIBYTES = "PiB"
    EXBIBYTES = "EiB"
    ZEBIBYTES = "ZiB"
    YOBIBYTES = "YiB"


# Data_rate units
class UnitOfDataRate(StrEnum):
    """Data rate units."""

    BITS_PER_SECOND = "bit/s"
    KILOBITS_PER_SECOND = "kbit/s"
    MEGABITS_PER_SECOND = "Mbit/s"
    GIGABITS_PER_SECOND = "Gbit/s"
    BYTES_PER_SECOND = "B/s"
    KILOBYTES_PER_SECOND = "kB/s"
    MEGABYTES_PER_SECOND = "MB/s"
    GIGABYTES_PER_SECOND = "GB/s"
    KIBIBYTES_PER_SECOND = "KiB/s"
    MEBIBYTES_PER_SECOND = "MiB/s"
    GIBIBYTES_PER_SECOND = "GiB/s"
