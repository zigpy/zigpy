from __future__ import annotations

from zigpy.types import basic


class DeviceID(basic.uint32_t, repr="hex"):
    pass


class FrameType(basic.enum2):
    DataFrame = 0x00
    MaintenanceFrame = 0x01


class ApplicationID(basic.enum3):
    SrcID = 0b000
    IEEE = 0b010
    LPED = 0b001


# Table 13
class SecurityLevel(basic.enum2):
    NoSecurity = 0b00
    ShortFrameCounterAndMIC = 0b01
    FullFrameCounterAndMIC = 0b10
    Encrypted = 0b11


# Table 14
class SecurityKeyType(basic.enum3):
    NoKey = 0b000
    NWKKey = 0b001
    GPDGroupKey = 0b010
    NWKKeyDerivedGPD = 0b011
    IndividualKey = 0b100
    DerivedIndividual = 0b111


# ZGP spec Figure 22
class ProxyCommissioningModeExitMode(basic.enum3):
    NotDefined = 0b000
    OnExpire = 0b001
    OnFirstPairing = 0b010
    OnExplicitExit = 0b100
    OnExpireOrFirstPairing = 0b011
    OnExpireOrExplicitExit = 0b101


# Table 29
class CommunicationMode(basic.enum2):
    Unicast = 0b00
    GroupcastForwardToDGroup = 0b01
    GroupcastForwardToCommGroup = 0b10
    UnicastLightweight = 0b11


class CommunicationDirection(basic.enum1):
    GPDtoGPP = 0
    GPPtoGPD = 1
