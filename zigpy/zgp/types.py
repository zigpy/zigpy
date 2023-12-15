from __future__ import annotations
import typing
from click import command

from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from zigpy.profiles.zgp import (
    GREENPOWER_BROADCAST_GROUP,
    GREENPOWER_DEFAULT_LINK_KEY
)

from .foundation import GPDeviceType
from .security import zgp_decrypt, zgp_encrypt
from zigpy.types import basic
from zigpy.types.struct import Struct, StructField
from zigpy.types.named import (
    EUI64,
    NWK,
    ClusterId,
    KeyData
)

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

# Figure 76
class GPChannelSearchPayload(Struct):
    options: basic.bitmap8
    @property
    def next_channel(self) -> int:
        return self.options & 0xF
    @property
    def next_next_channel(self) -> int:
        return self.options >> 4

class GPReplyPayload(Struct):
    options: basic.uint8_t
    pan_id: NWK = StructField(
        requires=lambda s: s.pan_id_present,
        optional=True)
    key: KeyData = StructField(
        requires=lambda s: s.key_present,
        optional=True)
    key_mic: basic.uint32_t = StructField(
        requires=lambda s: s.key_encrypted,
        optional=True)
    frame_counter: basic.uint32_t = StructField(
        requires=lambda s: s.key_encrypted and s.security_level >= GPSecurityLevel.FullFrameCounterAndMIC,
        optional=True)

    @property
    def pan_id_present(self) -> bool:
        return self.options & 0b1
    @pan_id_present.setter
    def pan_id_present(self, value: bool):
        self.options = (self.options & (~0b1)) | value 

    @property
    def key_present(self) -> bool:
        return self.options & 0b10
    @key_present.setter
    def key_present(self, value: basic.uint1_t):
        self.options = (self.options & (~0b10)) | (value << 1)

    @property
    def key_encrypted(self) -> bool:
        return bool(self.options & 0b100)
    @key_encrypted.setter
    def key_encrypted(self, value):
        self.options = (self.options & (~0b100)) | (value << 2)

    @property
    def security_level(self) -> GPSecurityLevel:
        return GPSecurityLevel((self.options >> 3) & 0b11)
    @security_level.setter
    def security_level(self, value: GPSecurityLevel):
        self.options = (self.options & (~0b11000)) | (value << 3)

    @property
    def security_key_type(self) -> GPSecurityKeyType:
        return GPSecurityKeyType((self.options >> 5) & 0b111)
    @security_key_type.setter
    def security_key_type(self, value: GPSecurityKeyType):
        self.options = (self.options & (~0b11100000)) | (value << 5)

    def set_key_no_encryption(self, key:KeyData):
        self.key_present = 1
        self.key = key

    def set_key_with_encryption(self, key: KeyData, src_id: GreenPowerDeviceID, frame_counter: basic.uint32_t):
        self.key_present = 1
        self.key_encrypted = 1
        srcbytes = src_id.serialize()
        frame_counter = basic.uint32_t(frame_counter+1)
        # A.1.5.3.3.3
        encrypted_key, mic = zgp_encrypt(
            GREENPOWER_DEFAULT_LINK_KEY.serialize(),
            srcbytes+srcbytes+frame_counter.serialize()+bytes([0x05]),
            srcbytes,
            key.serialize()
        )
        self.key, _ = KeyData.deserialize(encrypted_key)
        self.key_mic, _ = basic.uint32_t.deserialize(mic)
        # This is new, apparently!
        if self.security_level >= GPSecurityLevel.FullFrameCounterAndMIC:
            self.frame_counter = frame_counter

def ClusterListFactory(len: basic.uint4_t) -> basic.CALLABLE_T:
    class _ClusterList(basic.FixedList, item_type=ClusterId, length=len):
        pass
    return _ClusterList

# Figure 71
class GPCommissioningPayload(Struct):
    device_type: basic.uint8_t
    options: basic.bitmap8
    ext_options: basic.bitmap8 = StructField(
        requires=lambda s: s.ext_opts_present,
        optional=True)
    gpd_key: KeyData = StructField(
        requires=lambda s: s.gpd_key_present,
        optional=True)
    gpd_key_mic: basic.uint32_t = StructField(
        requires=lambda s: s.gpd_key_encryption,
        optional=True)
    gpd_outgoing_counter: basic.uint32_t = StructField(
        requires=lambda s: s.gpd_outgoing_counter_present,
        optional=True)
    application_information: basic.uint8_t = StructField(
        requires=lambda s: s.application_info_present,
        optional=True)
    manufacturer_id: basic.uint16_t = StructField(
        requires=lambda s: s.manufacturer_id_present,
        optional=True)
    model_id: basic.uint16_t = StructField(
        requires=lambda s: s.model_id_present,
        optional=True)
    command_ids: basic.LVBytes = StructField(
        requires=lambda s: s.command_list_present,
        optional=True)
    server_cluster_length: basic.uint4_t = StructField(
        requires=lambda s: s.cluster_reports_present,
        optional=True)
    client_cluster_length: basic.uint4_t = StructField(
        requires=lambda s: s.cluster_reports_present,
        optional=True)
    server_cluster_list: None = StructField(
        requires=lambda s: s.cluster_reports_present and s.server_cluster_length > 0,
        optional=True,
        dynamic_type=lambda s: ClusterListFactory(s.server_cluster_length))
    client_cluster_list: None = StructField(
        requires=lambda s: s.cluster_reports_present and s.client_cluster_length > 0,
        optional=True,
        dynamic_type=lambda s: ClusterListFactory(s.client_cluster_length))

    @property
    def mac_seq_num_cap(self) -> basic.uint1_t:
        return basic.uint1_t(self.options & 0x1)
    @property
    def rx_on_cap(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 1) & 0x1)
    @property
    def application_info_present(self) -> basic.uint1_t:
        return basic.uint1_t((self.options >> 2) & 0x1)
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
        return self.ext_opts_present and self.gpd_key_present and basic.uint1_t((self.ext_options >> 6) & 0x1) or 0
    @property
    def gpd_outgoing_counter_present(self) -> basic.uint1_t:
        return self.ext_opts_present and basic.uint1_t((self.ext_options >> 7) & 0x1) or 0
    @property
    def manufacturer_id_present(self) -> bool:
        return self.application_info_present and (self.application_information & 0b1)
    @property
    def model_id_present(self) -> bool:
        return self.application_info_present and ((self.application_information >> 1) & 0b1)
    @property
    def command_list_present(self) -> bool:
        return self.application_info_present and ((self.application_information >> 2) & 0b1)
    @property
    def cluster_reports_present(self) -> bool:
        return self.application_info_present and ((self.application_information >> 3) & 0b1)

    def get_validated_key(self, src_id: GreenPowerDeviceID) -> KeyData:
        if not self.gpd_key_present:
            return KeyData.UNKNOWN
        
        # if we have MIC for key, test it
        if self.gpd_key_encryption:
            # else has gpd key with tagged mic
            srcbytes = src_id.serialize()
            _, passed, _ = zgp_decrypt(
                GREENPOWER_DEFAULT_LINK_KEY.serialize(), 
                srcbytes+srcbytes+srcbytes+bytes([0x05]),
                srcbytes,
                self.gpd_key.serialize(),
                self.gpd_key_mic.serialize()
            )
            if not passed:
                raise Exception(f"Failed to decrypt incoming GPD key from {src_id}; failing")

        # either we couldn't validate or the validation passed  
        return self.gpd_key

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
                instance.gpd_key_mic, data = basic.uint32_t.deserialize(data)
        
        if instance.gpd_outgoing_counter_present:
            instance.gpd_outgoing_counter, data = basic.uint32_t.deserialize(data)

        if instance.application_info_present:
            instance.application_information, data = basic.uint8_t.deserialize(data)
            if instance.manufacturer_id_present:
                instance.manufacturer_id, data = basic.uint16_t.deserialize(data)
            if instance.model_id_present:
                instance.model_id, data = basic.uint16_t.deserialize(data)
            if instance.command_list_present:
                instance.command_ids, data = basic.LVBytes.deserialize(data)
            if instance.cluster_reports_present:
                l, data = basic.uint8_t.deserialize(data)
                instance.server_cluster_length = l & 0b1111
                instance.client_cluster_length = l >> 4
                if instance.server_cluster_length > 0:
                    instance.server_cluster_list, data = ClusterListFactory(instance.server_cluster_length).deserialize(data)
                if instance.client_cluster_length > 0:
                    instance.client_cluster_list, data = ClusterListFactory(instance.client_cluster_length).deserialize(data)
        
        return [instance, data]

# Table 27
class SinkTableEntry(Struct):
    options: basic.bitmap16
    gpd_id: GreenPowerDeviceID
    device_id: GPDeviceType
    group_list: basic.LVBytes = StructField(optional=True)
    radius: basic.uint8_t 
    sec_options: basic.bitmap8 = StructField(
        requires=lambda s: s.security_use,
        optional=True)
    sec_frame_counter: basic.uint32_t = StructField(
        requires=lambda s: s.sequence_number_cap,
        optional=True)
    key: KeyData = StructField(
        requires=lambda s: s.security_key_type is not GPSecurityKeyType.NoKey,
        optional=True)

    @property
    def application_id(self) -> GPApplicationID:
        return GPApplicationID(self.options & 0b111)
    @application_id.setter
    def application_id(self, value: GPApplicationID):
        self.options = (self.options & ~(0b111)) | value
    
    @property
    def security_level(self) -> GPSecurityLevel:
        if self.sec_options is None:
            return GPSecurityLevel.NoSecurity
        return GPSecurityLevel(self.sec_options & 0b11)
    @security_level.setter
    def security_level(self, value: GPSecurityLevel):
        if self.sec_options is None:
            return
        self.sec_options = (self.sec_options & ~(0b11)) | (value)

    @property
    def security_key_type(self) -> GPSecurityKeyType:
        if self.sec_options is None:
            return GPSecurityKeyType.NoKey
        return GPSecurityKeyType((self.sec_options >> 2) & 0b111)
    @security_key_type.setter
    def security_key_type(self, value: GPSecurityKeyType):
        if self.sec_options is None:
            return
        self.sec_options = (self.sec_options & ~(0b111 << 2)) | (value << 2)

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

class GreenPowerDeviceData(Struct):
    gpd_id: GreenPowerDeviceID
    device_id: GPDeviceType
    unicast_proxy: EUI64
    security_level: GPSecurityLevel
    security_key_type: GPSecurityKeyType
    communication_mode: GPCommunicationMode
    frame_counter: basic.uint32_t
    raw_key: KeyData
    assigned_alias: bool
    fixed_location: bool
    rx_on_cap: bool
    sequence_number_cap: bool
    manufacturer_id: basic.uint16_t
    model_id: basic.uint16_t

    @property
    def ieee(self) -> EUI64:
        return EUI64(self.gpd_id.serialize() + bytes([0,0,0,0]))
    
    @property
    def nwk(self) -> NWK:
        return NWK(self.gpd_id & 0xFFFF)
    
    @property
    def sink_table_entry(self) -> SinkTableEntry:
        instance = SinkTableEntry(
            options=0,
            gpd_id=self.gpd_id,
            device_id=self.device_id,
            radius=0xFF
        )
        if self.communication_mode in (GPCommunicationMode.GroupcastForwardToCommGroup, GPCommunicationMode.GroupcastForwardToDGroup):
            instance.group_list=basic.LVBytes(
                GREENPOWER_BROADCAST_GROUP.to_bytes(2, "little") + 0xFF.to_bytes(1) + 0xFF.to_bytes(1)
            )

        instance.security_use = self.security_level is not GPSecurityLevel.NoSecurity
        if instance.security_use:
            instance.sec_options = 0
            instance.security_level = self.security_level
            instance.security_key_type = self.security_key_type
            if instance.security_key_type != GPSecurityKeyType.NoKey:
                instance.key = self.encrypt_key_for_gpp()
        instance.rx_on_cap = self.rx_on_cap
        instance.sequence_number_cap = self.sequence_number_cap
        if instance.sequence_number_cap:
            instance.sec_frame_counter = self.frame_counter
        
        return instance

    def encrypt_key_for_gpp(self) -> tuple[bytes, bytes]:
        # A.1.5.9.1
        src_bytes = self.gpd_id.serialize()
        return zgp_encrypt(
            GREENPOWER_DEFAULT_LINK_KEY.serialize(),
            src_bytes + src_bytes + src_bytes + bytes([0x05]),
            src_bytes,
            self.raw_key.serialize()
        )

class GPDataFrame(Struct):
    options: basic.bitmap8
    frame_control_ext: basic.bitmap8 = StructField(
        requires=lambda s: s.has_frame_control_ext, 
        optional=True)
    src_id: GreenPowerDeviceID = StructField(
        requires=lambda s: s.has_src_id,
        optional=True)
    frame_counter: basic.uint32_t = StructField(
        requires=lambda s: s.has_frame_counter,
        optional=True)
    command_id: basic.uint32_t
    command_payload: basic.SerializableBytes = StructField(optional=True)
    mic: basic.uint32_t = StructField(optional=True) # TODO: this could be 0/2/4, fix with dynamic_type, tho that hits before options is populated

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
    def has_frame_counter(self) -> bool: 
        return self.has_frame_control_ext and self.security_level in (GPSecurityLevel.FullFrameCounterAndMIC, GPSecurityLevel.Encrypted)

    @property
    def has_src_id(self) -> bool: 
        return (self.frame_type == GPFrameType.DataFrame and self.application_id == GPApplicationID.GPZero or
            self.frame_type == GPFrameType.MaintenanceFrame and self.has_frame_control_ext and self.application_id == GPApplicationID.GPZero)

    @property
    def direction(self) -> GPCommunicationDirection:
        return self.has_frame_control_ext and GPCommunicationDirection((self.frame_control_ext >> 7) & 0x01) or GPCommunicationDirection.GPDtoGPP
    
    # Very likely originated from code found here: https://lucidar.me/en/zigbee/zigbee-frame-encryption-with-aes-128-ccm/
    def calculate_mic(self, key: KeyData) -> basic.uint32_t:
        key_bytes = key.serialize()
        src_id = self.src_id.serialize()
        frame_counter = self.frame_counter.serialize()
        nonce = src_id + src_id + frame_counter + bytes([0x05])
        header = self.options.serialize() + self.frame_control_ext.serialize()
        header = header + src_id + frame_counter
        a = header + self.command_payload
        La = len(a).to_bytes(2)
        AddAuthData = La + a
        AddAuthData += bytes([0x00] * (16 - len(AddAuthData)))
        B0 = bytes([0x49]) + nonce
        B0 += bytes([0x00] * (16 - len(B0)))
        B1 = AddAuthData
        X0 = bytes([0x00] * 16)
        cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(B0))
        encryptor = cipher.encryptor()
        X1 = encryptor.update(X0) + encryptor.finalize()
        cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(B1))
        encryptor = cipher.encryptor()
        X2 = encryptor.update(X1) + encryptor.finalize()
        A0 = bytes([0x01]) + nonce + bytes([0x00, 0x00])
        cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(int.from_bytes(A0, "big")))
        encryptor = cipher.encryptor()
        result_bytes = encryptor.update(X2[0:4]) + encryptor.finalize()
        result, _ = basic.uint32_t.deserialize(result_bytes)
        return result

    @classmethod
    def deserialize(cls: GPDataFrame, data: bytes) -> tuple[GPDataFrame, bytes]:
        instance : GPDataFrame = GPDataFrame()
        instance.options, data = basic.bitmap8.deserialize(data)
        if instance.frame_type not in (GPFrameType.DataFrame, GPFrameType.MaintenanceFrame):
            raise Exception("Bad GDPF type %d", instance.frame_type)
        instance.frame_control_ext = 0
        if instance.has_frame_control_ext:
            instance.frame_control_ext, data = basic.bitmap8.deserialize(data)
        if instance.application_id not in (GPApplicationID.GPZero, GPApplicationID.GPTwo, GPApplicationID.LPED):
            raise Exception("Bad Application ID %d", instance.application_id)
        
        if instance.has_src_id:
            instance.src_id, data = GreenPowerDeviceID.deserialize(data)
        
        if instance.has_frame_counter:
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
