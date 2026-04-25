"""Tests for Green Power type definitions."""

from __future__ import annotations

from zigpy.zgp.types import (
    DEFAULT_GP_LINK_KEY,
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    GP_GROUP_ID,
    ApplicationID,
    CommunicationDirection,
    CommunicationMode,
    DeviceID,
    FrameType,
    GPDCommandID,
    ProxyCommissioningModeExitMode,
    SecurityKeyType,
    SecurityLevel,
)


def test_gp_endpoint():
    assert GP_ENDPOINT == 242


def test_gp_cluster_id():
    assert GP_CLUSTER_ID == 0x0021


def test_gp_group_id():
    assert GP_GROUP_ID == 0x0B84


def test_default_link_key():
    assert bytes(DEFAULT_GP_LINK_KEY) == b"ZigBeeAlliance09"
    assert len(DEFAULT_GP_LINK_KEY) == 16


def test_device_id_is_uint32():
    d = DeviceID(0x12345678)
    assert int(d) == 0x12345678


def test_device_id_hex_repr():
    d = DeviceID(0x02)
    assert "0x" in repr(d).lower()


def test_no_security():
    assert SecurityLevel.NoSecurity == 0b00


def test_short_counter_mic():
    assert SecurityLevel.Reserved == 0b01


def test_full_counter_mic():
    assert SecurityLevel.FullFrameCounterAndMIC == 0b10


def test_encrypted():
    assert SecurityLevel.Encrypted == 0b11


def test_values():
    assert SecurityKeyType.NoKey == 0b000
    assert SecurityKeyType.NWKKey == 0b001
    assert SecurityKeyType.GPDGroupKey == 0b010
    assert SecurityKeyType.NWKKeyDerivedGPD == 0b011
    assert SecurityKeyType.IndividualKey == 0b100
    assert SecurityKeyType.DerivedIndividual == 0b111


def test_commissioning_commands():
    assert GPDCommandID.CommissioningRequest == 0xE0
    assert GPDCommandID.DecommissioningRequest == 0xE1
    assert GPDCommandID.SuccessReport == 0xE2
    assert GPDCommandID.ChannelRequest == 0xE3


def test_on_off_commands():
    assert GPDCommandID.Off == 0x20
    assert GPDCommandID.On == 0x21
    assert GPDCommandID.Toggle == 0x22


def test_level_commands():
    assert GPDCommandID.MoveUp == 0x30
    assert GPDCommandID.MoveDown == 0x31
    assert GPDCommandID.StepUp == 0x32
    assert GPDCommandID.StepDown == 0x33
    assert GPDCommandID.LevelControlStop == 0x34


def test_identify():
    assert GPDCommandID.Identify == 0x00


def test_scene_commands():
    assert GPDCommandID.RecallScene0 == 0x10
    assert GPDCommandID.RecallScene7 == 0x17
    assert GPDCommandID.StoreScene0 == 0x18
    assert GPDCommandID.StoreScene7 == 0x1F


def test_color_commands():
    assert GPDCommandID.MoveHueStop == 0x40
    assert GPDCommandID.MoveHueUp == 0x41
    assert GPDCommandID.StepColor == 0x4B


def test_door_lock_commands():
    assert GPDCommandID.LockDoor == 0x50
    assert GPDCommandID.UnlockDoor == 0x51


def test_reporting_commands():
    assert GPDCommandID.AttributeReporting == 0xA0
    assert GPDCommandID.ManufacturerSpecificReporting == 0xA1
    assert GPDCommandID.MultiClusterReporting == 0xA2


def test_application_description():
    assert GPDCommandID.ApplicationDescription == 0xE4


def test_any_command():
    assert GPDCommandID.AnyCommand == 0xFF


def test_data_frame():
    assert FrameType.DataFrame == 0x00


def test_maintenance_frame():
    assert FrameType.MaintenanceFrame == 0x01


def test_src_id():
    assert ApplicationID.SrcID == 0b000


def test_ieee():
    assert ApplicationID.IEEE == 0b010


def test_lped():
    assert ApplicationID.LPED == 0b001


def test_unicast():
    assert CommunicationMode.Unicast == 0b00


def test_groupcast():
    assert CommunicationMode.GroupcastForwardToDGroup == 0b01
    assert CommunicationMode.GroupcastForwardToCommGroup == 0b10


def test_lightweight():
    assert CommunicationMode.UnicastLightweight == 0b11


def test_directions():
    assert CommunicationDirection.GPDtoGPP == 0
    assert CommunicationDirection.GPPtoGPD == 1


def test_exit_modes():
    assert ProxyCommissioningModeExitMode.NotDefined == 0b000
    assert ProxyCommissioningModeExitMode.OnExpire == 0b001
    assert ProxyCommissioningModeExitMode.OnFirstPairing == 0b010
    assert ProxyCommissioningModeExitMode.OnExplicitExit == 0b100


def test_combined_exit_modes():
    assert ProxyCommissioningModeExitMode.OnExpireOrFirstPairing == 0b011
    assert ProxyCommissioningModeExitMode.OnExpireOrExplicitExit == 0b101
