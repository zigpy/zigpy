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


class TestConstants:
    """Tests for GP constants."""

    def test_gp_endpoint(self) -> None:
        assert GP_ENDPOINT == 242

    def test_gp_cluster_id(self) -> None:
        assert GP_CLUSTER_ID == 0x0021

    def test_gp_group_id(self) -> None:
        assert GP_GROUP_ID == 0x0B84

    def test_default_link_key(self) -> None:
        assert DEFAULT_GP_LINK_KEY == b"ZigBeeAlliance09"
        assert len(DEFAULT_GP_LINK_KEY) == 16


class TestDeviceID:
    """Tests for GP Device ID type."""

    def test_device_id_is_uint32(self) -> None:
        d = DeviceID(0x12345678)
        assert int(d) == 0x12345678

    def test_device_id_hex_repr(self) -> None:
        d = DeviceID(0x02)
        assert "0x" in repr(d).lower()


class TestSecurityLevel:
    """Tests for SecurityLevel enum."""

    def test_no_security(self) -> None:
        assert SecurityLevel.NoSecurity == 0b00

    def test_short_counter_mic(self) -> None:
        assert SecurityLevel.Reserved == 0b01

    def test_full_counter_mic(self) -> None:
        assert SecurityLevel.FullFrameCounterAndMIC == 0b10

    def test_encrypted(self) -> None:
        assert SecurityLevel.Encrypted == 0b11


class TestSecurityKeyType:
    """Tests for SecurityKeyType enum."""

    def test_values(self) -> None:
        assert SecurityKeyType.NoKey == 0b000
        assert SecurityKeyType.NWKKey == 0b001
        assert SecurityKeyType.GPDGroupKey == 0b010
        assert SecurityKeyType.NWKKeyDerivedGPD == 0b011
        assert SecurityKeyType.IndividualKey == 0b100
        assert SecurityKeyType.DerivedIndividual == 0b111


class TestGPDCommandID:
    """Tests for GPD command identifiers."""

    def test_commissioning_commands(self) -> None:
        assert GPDCommandID.CommissioningRequest == 0xE0
        assert GPDCommandID.DecommissioningRequest == 0xE1
        assert GPDCommandID.SuccessReport == 0xE2
        assert GPDCommandID.ChannelRequest == 0xE3

    def test_on_off_commands(self) -> None:
        assert GPDCommandID.Off == 0x20
        assert GPDCommandID.On == 0x21
        assert GPDCommandID.Toggle == 0x22

    def test_level_commands(self) -> None:
        assert GPDCommandID.MoveUp == 0x30
        assert GPDCommandID.MoveDown == 0x31
        assert GPDCommandID.StepUp == 0x32
        assert GPDCommandID.StepDown == 0x33
        assert GPDCommandID.LevelControlStop == 0x34

    def test_identify(self) -> None:
        assert GPDCommandID.Identify == 0x00

    def test_scene_commands(self) -> None:
        assert GPDCommandID.RecallScene0 == 0x10
        assert GPDCommandID.RecallScene7 == 0x17
        assert GPDCommandID.StoreScene0 == 0x18
        assert GPDCommandID.StoreScene7 == 0x1F

    def test_color_commands(self) -> None:
        assert GPDCommandID.MoveHueStop == 0x40
        assert GPDCommandID.MoveHueUp == 0x41
        assert GPDCommandID.StepColor == 0x4B

    def test_door_lock_commands(self) -> None:
        assert GPDCommandID.LockDoor == 0x50
        assert GPDCommandID.UnlockDoor == 0x51

    def test_reporting_commands(self) -> None:
        assert GPDCommandID.AttributeReporting == 0xA0
        assert GPDCommandID.ManufacturerSpecificReporting == 0xA1
        assert GPDCommandID.MultiClusterReporting == 0xA2

    def test_application_description(self) -> None:
        assert GPDCommandID.ApplicationDescription == 0xE4

    def test_any_command(self) -> None:
        assert GPDCommandID.AnyCommand == 0xFF


class TestFrameType:
    """Tests for GP frame types."""

    def test_data_frame(self) -> None:
        assert FrameType.DataFrame == 0x00

    def test_maintenance_frame(self) -> None:
        assert FrameType.MaintenanceFrame == 0x01


class TestApplicationID:
    """Tests for Application ID values."""

    def test_src_id(self) -> None:
        assert ApplicationID.SrcID == 0b000

    def test_ieee(self) -> None:
        assert ApplicationID.IEEE == 0b010

    def test_lped(self) -> None:
        assert ApplicationID.LPED == 0b001


class TestCommunicationMode:
    """Tests for communication mode enum."""

    def test_unicast(self) -> None:
        assert CommunicationMode.Unicast == 0b00

    def test_groupcast(self) -> None:
        assert CommunicationMode.GroupcastForwardToDGroup == 0b01
        assert CommunicationMode.GroupcastForwardToCommGroup == 0b10

    def test_lightweight(self) -> None:
        assert CommunicationMode.UnicastLightweight == 0b11


class TestCommunicationDirection:
    """Tests for communication direction enum."""

    def test_directions(self) -> None:
        assert CommunicationDirection.GPDtoGPP == 0
        assert CommunicationDirection.GPPtoGPD == 1


class TestProxyCommissioningModeExitMode:
    """Tests for proxy commissioning exit mode."""

    def test_exit_modes(self) -> None:
        assert ProxyCommissioningModeExitMode.NotDefined == 0b000
        assert ProxyCommissioningModeExitMode.OnExpire == 0b001
        assert ProxyCommissioningModeExitMode.OnFirstPairing == 0b010
        assert ProxyCommissioningModeExitMode.OnExplicitExit == 0b100

    def test_combined_exit_modes(self) -> None:
        assert ProxyCommissioningModeExitMode.OnExpireOrFirstPairing == 0b011
        assert ProxyCommissioningModeExitMode.OnExpireOrExplicitExit == 0b101
