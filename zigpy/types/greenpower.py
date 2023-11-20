from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import enum
import typing

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from zigpy.profiles.zgp import GPDeviceType

from . import basic
from .struct import Struct
from .named import KeyData

if typing.TYPE_CHECKING:
    from typing_extensions import Self

class GreenPowerDeviceID(basic.uint32_t, repr="hex"):
    pass

class GPFrameType(basic.enum2):
    DataFrame = 0x00
    MaintenanceFrame = 0x01

class GPApplicationID(basic.enum3):
    GPZero = 0b000
    GPTwo  = 0b010
    LPED   = 0b001

# Table 13
class GPSecurityLevel(basic.enum2):
    NoSecurity = 0b00
    ShortFrameCounterAndMIC = 0b01
    FullFrameCounterAndMIC = 0b10
    Encrypted = 0b11

# Table 14
class GPSecurityKeyType(basic.enum3):
    NoKey = 0b000
    NWKKey = 0b001
    GPDGroupKey = 0b010
    NWKKeyDerivedGPD = 0b011
    IndividualKey = 0b100
    DerivedIndividual = 0b111

# ZGP spec Figure 22
class GPProxyCommissioningModeExitMode(basic.enum3):
    NotDefined = 0b000
    OnExpire = 0b001
    OnFirstPairing = 0b010
    OnExplicitExit = 0b100
    OnExpireOrFirstPairing = 0b011
    OnExpireOrExplicitExit = 0b101

# Table 29
class GPCommunicationMode(basic.enum2):
    Unicast = 0b00
    GroupcastForwardToDGroup = 0b01
    GroupcastForwardToCommGroup = 0b10
    UnicastLightweight = 0b11


class GPCommunicationDirection(basic.enum1):
    GPDtoGPP = 0
    GPPtoGPD = 1


# Figure 71
class GPCommissioningPayload(Struct):
    device_type: basic.uint8_t
    options: basic.bitmap8
    ext_options: basic.Optional(basic.bitmap8)
    gpd_key: basic.Optional(KeyData)
    gpd_key_mic: basic.Optional(basic.uint32_t)
    gpd_outgoing_counter: basic.Optional(basic.uint32_t)

    @property
    def mac_seq_num_cap(self) -> basic.uint1_t:
        return basic.uint1_t(self.options & 0x1)
    @property
    def rx_on_cap(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 1) & 0x1)
    @property
    def pan_id_req(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 4) & 0x1)
    @property
    def gp_sec_key_req(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 5) & 0x1)
    @property
    def fixed_loc(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 6) & 0x1)
    @property
    def ext_opts_present(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 7) & 0x1)
    
    @property
    def security_level(self) -> GPSecurityLevel:
        return self.ext_opts_present and GPSecurityLevel(self.ext_options & 0b11) or GPSecurityLevel.NoSecurity
    @property
    def key_type(self) -> GPSecurityKeyType:
        return self.ext_opts_present and GPSecurityKeyType((self.ext_options >> 2) & 0b111) or GPSecurityKeyType.NoKey
    @property
    def gpd_key_present(self) -> basic.uint1_t:
        return self.ext_opts_present and basic.uint1_t((self.ext_options >> 5) & 0x1) or 0
    @property
    def gpd_key_encryption(self) -> basic.uint1_t:
        return self.ext_opts_present and basic.uint1_t((self.ext_options >> 6) & 0x1) or 0
    @property
    def gpd_outgoing_counter_present(self) -> basic.uint1_t:
        return self.ext_opts_present and basic.uint1_t((self.ext_options >> 7) & 0x1) or 0

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[GPCommissioningPayload, bytes]:
        instance = GPCommissioningPayload()
        instance.device_type, data = basic.uint8_t.deserialize(data)
        instance.options, data = basic.bitmap8.deserialize(data)
        if instance.ext_opts_present:
            instance.ext_options, data = basic.bitmap8.deserialize(data)
        
        if instance.gpd_key_present:
            instance.gpd_key, data = KeyData.deserialize(data)
            if instance.gpd_key_encryption:
                instance.gpd_key_mic, data = basic.uint32_t(data)
        
        if instance.gpd_outgoing_counter_present:
            instance.gpd_outgoing_counter, data = basic.uint32_t(data)
        
        return [instance, data]


# Figure 74
class GPCommissioningReplyPayload(Struct):
    options: basic.bitmap8
    pan_id: basic.Optional(basic.uint16_t)
    security_key: basic.Optional(KeyData)
    gpd_key_mic: basic.Optional(basic.uint32_t)



# Table 27
class SinkTableEntry(Struct):
    options: basic.bitmap16
    gpd_id: GreenPowerDeviceID
    device_id: GPDeviceType
    group_list: basic.Optional(basic.LVBytes)
    radius: basic.uint8_t 
    sec_options: basic.Optional(basic.bitmap8)
    sec_frame_counter: basic.Optional(basic.uint32_t)
    key: basic.Optional(KeyData)

    @property
    def application_id(self) -> GPApplicationID:
        return GPApplicationID(self.options & 0b111)
    @application_id.setter
    def application_id(self, value: GPApplicationID):
        self.options = (self.options & ~(0b111)) | value
    
    @property
    def communication_mode(self) -> GPCommunicationMode:
        return GPCommunicationMode((self.options >> 3) & 0b11)
    @communication_mode.setter
    def communication_mode(self, value: GPCommunicationMode):
        self.options = (self.options & ~(0b11 << 3)) | (value << 3)

    @property
    def sequence_number_cap(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 5) & 0x01)
    @sequence_number_cap.setter
    def sequence_number_cap(self, value: basic.uint1_t):
        self.options = (self.options & ~(1 << 5)) | (value << 5)

    @property
    def rx_on_cap(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 6) & 0x01)
    @rx_on_cap.setter
    def rx_on_cap(self, value: basic.uint1_t):
        self.options = (self.options & ~(1 << 6)) | (value << 6)

    @property
    def fixed_location(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 7) & 0x01)
    @fixed_location.setter
    def fixed_location(self, value: basic.uint1_t):
        self.options = (self.options & ~(1 << 7)) | (value << 7)

    @property
    def assigned_alias(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 8) & 0x01)
    @assigned_alias.setter
    def assigned_alias(self, value: basic.uint1_t):
        self.options = (self.options & ~(1 << 8)) | (value << 8)

    @property
    def security_use(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 9) & 0x01)
    @security_use.setter
    def security_use(self, value: basic.uint1_t):
        self.options = (self.options & ~(1 << 9)) | (value << 9)


class GPDataFrame(Struct):
    options: basic.bitmap8
    frame_control_ext: basic.Optional(basic.bitmap8)
    src_id: basic.Optional(GreenPowerDeviceID)
    frame_counter: basic.Optional(basic.uint32_t)
    command_id: basic.uint32_t
    command_payload: basic.Optional(basic.SerializableBytes)
    mic: basic.Optional(basic.uint32_t) # TODO this could be either 0/2/4 bytes, not just 0/4

    @property
    def auto_commissioning(self) -> bool:
        return bool(self.options & 0b01000000)

    @property
    def has_frame_control_ext(self) -> bool:
        return bool(self.options & 0b10000000)
    
    @property
    def frame_type(self) -> GPFrameType:
        return GPFrameType(self.options & 0b0000011)
    
    @property
    def application_id(self) -> GPApplicationID:
        return self.has_frame_control_ext and GPApplicationID(self.frame_control_ext & 0b111) or GPApplicationID.GPZero

    @property
    def security_level(self) -> GPSecurityLevel:
        return self.has_frame_control_ext and GPSecurityLevel((self.frame_control_ext >> 3) & 0b11) or GPSecurityLevel.NoSecurity

    @property
    def has_security_key(self) -> basic.uint1_t:
        return self.has_frame_control_ext and basic.uint1_t((self.frame_control_ext >> 5) & 0x01) or 0
    
    @property
    def rx_after_tx(self) -> basic.uint1_t: 
        return self.has_frame_control_ext and basic.uint1_t((self.frame_control_ext >> 6) & 0x01) or 0

    @property
    def direction(self) -> GPCommunicationDirection:
        return self.has_frame_control_ext and GPCommunicationDirection((self.frame_control_ext >> 7) & 0x01) or GPCommunicationDirection.GPDtoGPP
    
    def calculate_mic(self, key: KeyData) -> basic.uint32_t:
        src_id: bytes = self.src_id.to_bytes(4, "little")
        frame_counter: bytes = self.frame_counter.to_bytes(4, "little")
        nonce = src_id + src_id + frame_counter + (0x05).to_bytes(1)
        header = self.options.to_bytes(1) + self.frame_control_ext.to_bytes(1)
        header = header + src_id + frame_counter
        a = header + self.command_payload
        La = len(a).to_bytes(2)
        AddAuthData = La + a
        AddAuthData += (0x00).to_bytes(1) * (16 - len(AddAuthData))
        B0 = (0x49).to_bytes(1) + nonce
        B0 += (0x00).to_bytes(1) * (16 - len(B0))
        B1 = AddAuthData
        X0 = (0x00000000000000000000000000000000).to_bytes(16)
        cipher = Cipher(algorithms.AES(key), modes.CBC(B0))
        encryptor = cipher.encryptor()
        X1 = encryptor.update(X0) + encryptor.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(B1))
        encryptor = cipher.encryptor()
        X2 = encryptor.update(X1) + encryptor.finalize()
        A0 = (0x01).to_bytes(1) + nonce + (0x0000).to_bytes(2)
        cipher = Cipher(algorithms.AES(key), modes.CTR(int.from_bytes(A0, byteorder="big")))
        encryptor = cipher.encryptor()
        result = encryptor.update(X2[0:4]) + encryptor.finalize()
        return basic.uint32_t.from_bytes(result, byteorder="little")

    @classmethod
    def deserialize(cls: type[GPDataFrame], data: bytes) -> tuple[GPDataFrame, bytes]:
        instance : GPDataFrame = GPDataFrame()
        instance.options, data = basic.bitmap8.deserialize(data)
        if instance.frame_type not in (GPFrameType.DataFrame, GPFrameType.MaintenanceFrame):
            raise Exception("Bad GDPF type %d", instance.frame_type)
        instance.frame_control_ext = 0
        if instance.has_frame_control_ext:
            instance.frame_control_ext, data = basic.bitmap8.deserialize(data)
        if instance.application_id not in (GPApplicationID.GPZero, GPApplicationID.GPTwo, GPApplicationID.LPED):
            raise Exception("Bad Application ID %d", instance.application_id)
        
        if instance.frame_type == GPFrameType.DataFrame and instance.application_id == GPApplicationID.GPZero:
            instance.src_id, data = GreenPowerDeviceID.deserialize(data)
        elif instance.frame_type == GPFrameType.MaintenanceFrame and instance.has_frame_control_ext and instance.application_id == GPApplicationID.GPZero:
            instance.src_id, data = GreenPowerDeviceID.deserialize(data)
        
        if instance.has_frame_control_ext and instance.security_level in (GPSecurityLevel.FullFrameCounterAndMIC, GPSecurityLevel.Encrypted):
            instance.frame_counter, data = basic.uint32_t.deserialize(data)
        
        if instance.application_id != GPApplicationID.LPED:
            instance.command_id, data = basic.uint8_t.deserialize(data)

            if instance.security_level == GPSecurityLevel.ShortFrameCounterAndMIC:
                instance.mic, _ = basic.uint16_t.deserialize(data[-2:])
                data = data[:-2]
            elif instance.security_level in (GPSecurityLevel.FullFrameCounterAndMIC, GPSecurityLevel.Encrypted):
                instance.mic, _ = basic.uint32_t.deserialize(data[-4:])
                data = data[:-4]
                
            instance.command_payload = basic.SerializableBytes(data)
        
        return instance, bytes()
    