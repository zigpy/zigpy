from __future__ import annotations

from typing import Self

import zigpy.types as t
from zigpy.types import basic

__all__ = [
    "GP_ENDPOINT",
    "GP_CLUSTER_ID",
    "GP_GROUP_ID",
    "DEFAULT_GP_LINK_KEY",
    "SrcID",
    "DeviceID",
    "GPDCommandID",
    "SwitchType",
    "FrameType",
    "ApplicationID",
    "SecurityLevel",
    "SecurityKeyType",
    "SecurityStatus",
    "ProxyCommissioningModeExitMode",
    "CommunicationMode",
    "CommunicationDirection",
    "GPLinkQuality",
    "GPPGPDLink",
    "GPDCommandPayload",
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


class SrcID(basic.uint32_t, repr="hex"):
    pass


# GPD DeviceIDs, defined in the "List of Green Power Device Definitions"
# (CSA document 13-0166, normative reference [13] of the ZGP specification)
class DeviceID(basic.enum8):
    SimpleGenericOneStateSwitch = 0x00
    SimpleGenericTwoStateSwitch = 0x01
    OnOffSwitch = 0x02
    LevelControlSwitch = 0x03
    SimpleSensor = 0x04
    AdvancedGenericOneStateSwitch = 0x05
    AdvancedGenericTwoStateSwitch = 0x06
    GenericSwitch = 0x07
    ColorDimmerSwitch = 0x10
    LightSensor = 0x11
    OccupancySensor = 0x12
    DoorLockController = 0x20
    TemperatureSensor = 0x30
    PressureSensor = 0x31
    FlowSensor = 0x32
    IndoorEnvironmentSensor = 0x33
    Undefined = 0xFE


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
    MoveUp = 0x30
    MoveDown = 0x31
    StepUp = 0x32
    StepDown = 0x33
    LevelControlStop = 0x34
    MoveUpWithOnOff = 0x35
    MoveDownWithOnOff = 0x36
    StepUpWithOnOff = 0x37
    StepDownWithOnOff = 0x38

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

    # Advanced generic switch (Table 55)
    Press8BitVector = 0x69
    Release8BitVector = 0x6A

    # Attribute Reporting
    AttributeReporting = 0xA0
    ManufacturerSpecificReporting = 0xA1

    # Multi-Cluster Reporting
    MultiClusterReporting = 0xA2
    ManufacturerSpecificMultiClusterReporting = 0xA3

    # Bidirectional operation
    RequestAttributes = 0xA4
    ReadAttributesResponse = 0xA5
    ZCLTunneling = 0xA6

    CompactAttributeReporting = 0xA8

    # Commissioning
    CommissioningRequest = 0xE0
    DecommissioningRequest = 0xE1
    SuccessReport = 0xE2
    ChannelRequest = 0xE3

    # Application Description
    ApplicationDescription = 0xE4

    # Commands sent to the GPD (sink → GPD, Table 56)
    CommissioningReply = 0xF0
    WriteAttributes = 0xF1
    ReadAttributes = 0xF2
    ChannelConfiguration = 0xF3
    ZCLTunnelingToGPD = 0xF6

    # Translation Table pseudo-IDs: these never appear as the CommandID of a GPDF.
    # 0xAF stands for any of the sensor commands 0xA0 - 0xA3 (but never 0xA8), and
    # 0xFF for every GPD command. Both only compact Translation Table entries.
    AnySensorCommand = 0xAF
    AnyCommand = 0xFF


# Table 57
class SwitchType(basic.enum2):
    Unknown = 0b00
    Button = 0b01
    Rocker = 0b10


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


# Table 5, the `Status` parameter of the GP-DATA.indication primitive: the outcome of
# GPDF security processing, which is what makes the other security fields meaningful
class SecurityStatus(basic.enum8):
    SecuritySuccess = 0x00
    NoSecurity = 0x01
    CounterFailure = 0x02
    AuthFailure = 0x03
    Unprocessed = 0x04

    @property
    def is_trusted(self) -> bool:
        """Whether the frame was verified, and its key type and payload usable."""
        return self in (SecurityStatus.SecuritySuccess, SecurityStatus.NoSecurity)


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


# Table 32
class GPLinkQuality(basic.enum2):
    Poor = 0b00
    Moderate = 0b01
    High = 0b10
    Excellent = 0b11


# Figure 27 — GPP-GPD link field appended to notifications by the forwarding proxy
class GPPGPDLink(t.IntStruct, basic.uint8_t):
    rssi: basic.uint6_t
    link_quality: GPLinkQuality

    @property
    def rssi_dbm(self) -> int:
        # The proxy caps RSSI to [-109, +8] dBm, adds 110, and halves it
        return self.rssi * 2 - 110


class GPDCommandPayload(basic.LVBytes):
    """GPD command payload; a length byte of 0xff means unspecified/no payload."""

    # An unspecified payload is empty, but it is not the same as an explicitly empty
    # one, so it round-trips back to the 0xff marker rather than to a zero length.
    # Note that `==` and `hash` compare only the bytes content, not the marker.
    unspecified: bool = False

    def __new__(cls, *args) -> Self:
        instance = super().__new__(cls, *args)

        if args and isinstance(args[0], cls):
            instance.unspecified = args[0].unspecified

        return instance

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[Self, bytes]:
        if data[:1] == b"\xff":
            instance = cls(b"")
            instance.unspecified = True

            return instance, data[1:]

        return super().deserialize(data)

    def serialize(self) -> bytes:
        if self.unspecified:
            return b"\xff"

        return super().serialize()
