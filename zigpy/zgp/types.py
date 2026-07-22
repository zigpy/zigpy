from __future__ import annotations

import zigpy.types as t
from zigpy.types import basic

__all__ = [
    "GP_ENDPOINT",
    "GP_CLUSTER_ID",
    "GP_GROUP_ID",
    "DEFAULT_GP_LINK_KEY",
    "DeviceID",
    "GPDCommandID",
    "FrameType",
    "ApplicationID",
    "SecurityLevel",
    "SecurityKeyType",
    "ProxyCommissioningModeExitMode",
    "CommunicationMode",
    "CommunicationDirection",
]

# Green Power endpoint as defined in the ZGP specification
GP_ENDPOINT: int = 242

# Green Power cluster ID
GP_CLUSTER_ID: int = 0x0021

# Green Power group ID used for groupcast forwarding
GP_GROUP_ID: int = 0x0B84

# Default ZigBee Green Power shared key ("ZigBeeAlliance09" TC link key).
# Used to unwrap GP security keys that a GPD provides during commissioning
# when no out-of-band key was pre-provisioned.
DEFAULT_GP_LINK_KEY = t.KeyData(b"ZigBeeAlliance09")


class DeviceID(basic.uint32_t, repr="hex"):
    pass


# GPD Command IDs (Tables 54-56 in the ZGP specification)
class GPDCommandID(basic.enum8):
    """GPD command identifiers sent by Green Power Devices."""

    # Identify
    Identify = 0x00

    # Scenes
    RecallScene0 = 0x10
    RecallScene1 = 0x11
    RecallScene2 = 0x12
    RecallScene3 = 0x13
    RecallScene4 = 0x14
    RecallScene5 = 0x15
    RecallScene6 = 0x16
    RecallScene7 = 0x17
    StoreScene0 = 0x18
    StoreScene1 = 0x19
    StoreScene2 = 0x1A
    StoreScene3 = 0x1B
    StoreScene4 = 0x1C
    StoreScene5 = 0x1D
    StoreScene6 = 0x1E
    StoreScene7 = 0x1F

    # On/Off
    Off = 0x20
    On = 0x21
    Toggle = 0x22
    Release = 0x23

    # Level Control
    LevelControlStop = 0x34
    MoveUp = 0x30
    MoveDown = 0x31
    StepUp = 0x32
    StepDown = 0x33

    # Color Control
    MoveHueStop = 0x40
    MoveHueUp = 0x41
    MoveHueDown = 0x42
    StepHueUp = 0x43
    StepHueDown = 0x44
    MoveSaturationStop = 0x45
    MoveSaturationUp = 0x46
    MoveSaturationDown = 0x47
    StepSaturationUp = 0x48
    StepSaturationDown = 0x49
    MoveColor = 0x4A
    StepColor = 0x4B

    # Door Lock
    LockDoor = 0x50
    UnlockDoor = 0x51

    # Generic switch button events (Table 54)
    Press1of1 = 0x60
    Release1of1 = 0x61
    Press1of2 = 0x62
    Release1of2 = 0x63
    Press2of2 = 0x64
    Release2of2 = 0x65
    ShortPress1of1 = 0x66
    ShortPress1of2 = 0x67
    ShortPress2of2 = 0x68

    # Attribute Reporting
    AttributeReporting = 0xA0
    ManufacturerSpecificReporting = 0xA1

    # Multi-Cluster Reporting
    MultiClusterReporting = 0xA2
    ManufacturerSpecificMultiClusterReporting = 0xA3

    # Commissioning
    CommissioningRequest = 0xE0
    DecommissioningRequest = 0xE1
    SuccessReport = 0xE2
    ChannelRequest = 0xE3

    # Application Description
    ApplicationDescription = 0xE4

    # Commands sent to the GPD (sink → GPD)
    CommissioningReply = 0xF0
    ChannelConfiguration = 0xF3

    # Any GPD command
    AnyCommand = 0xFF


class FrameType(basic.enum2):
    DataFrame = 0x00
    MaintenanceFrame = 0x01


class ApplicationID(basic.enum3):
    SrcID = 0b000
    IEEE = 0b010
    LPED = 0b001


# Table 11
class SecurityLevel(basic.enum2):
    NoSecurity = 0b00
    Reserved = 0b01
    FullFrameCounterAndMIC = 0b10
    Encrypted = 0b11


# Table 53
class SecurityKeyType(basic.enum3):
    NoKey = 0b000
    NWKKey = 0b001
    GPDGroupKey = 0b010
    NWKKeyDerivedGPD = 0b011
    IndividualKey = 0b100
    DerivedIndividual = 0b111


# ZGP spec Figure 22 — each bit is an independent exit condition and
# can be combined with the others.
class ProxyCommissioningModeExitMode(basic.bitmap3):
    NotDefined = 0b000
    OnExpire = 0b001
    OnFirstPairing = 0b010
    OnExplicitExit = 0b100


# Table 27
class CommunicationMode(basic.enum2):
    Unicast = 0b00
    GroupcastForwardToDGroup = 0b01
    GroupcastForwardToCommGroup = 0b10
    UnicastLightweight = 0b11


class CommunicationDirection(basic.enum1):
    GPDtoGPP = 0
    GPPtoGPD = 1
