"""Tests for the quirks v2 module."""

from typing import Final
from unittest.mock import AsyncMock

import pytest

from zigpy.const import (
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_MODELS_INFO,
)
from zigpy.device import Device
from zigpy.exceptions import MultipleQuirksMatchException
from zigpy.profiles import zha
from zigpy.quirks import CustomCluster, CustomDevice, signature_matches
from zigpy.quirks.registry import DeviceRegistry
from zigpy.quirks.v2 import (
    BinarySensorMetadata,
    CustomDeviceV2,
    EntityMetadata,
    EntityPlatform,
    EntityType,
    NumberMetadata,
    QuirkBuilder,
    SwitchMetadata,
    WriteAttributeButtonMetadata,
    ZCLCommandButtonMetadata,
    ZCLSensorMetadata,
    add_to_registry_v2,
)
import zigpy.types as t
from zigpy.zcl import ClusterType
from zigpy.zcl.clusters.general import (
    Alarms,
    Basic,
    Groups,
    Identify,
    LevelControl,
    OnOff,
    Ota,
    PowerConfiguration,
    Scenes,
)
from zigpy.zcl.clusters.homeautomation import Diagnostic
from zigpy.zcl.clusters.lightlink import LightLink
from zigpy.zcl.foundation import BaseAttributeDefs, ZCLAttributeDef, ZCLCommandDef
from zigpy.zdo.types import LogicalType, NodeDescriptor

from .async_mock import sentinel


@pytest.fixture(name="device_mock")
def real_device(app_mock) -> Device:
    """Device fixture with a single endpoint."""
    ieee = sentinel.ieee
    nwk = 0x2233
    device = Device(app_mock, ieee, nwk)

    device.add_endpoint(1)
    device[1].profile_id = 255
    device[1].device_type = 255
    device.model = "model"
    device.manufacturer = "manufacturer"
    device[1].add_input_cluster(3)
    device[1].add_output_cluster(6)
    return device


async def test_quirks_v2(device_mock):
    """Test adding a v2 quirk to the registry and getting back a quirked device."""
    registry = DeviceRegistry()

    signature = {
        SIG_MODELS_INFO: (("manufacturer", "model"),),
        SIG_ENDPOINTS: {
            1: {
                SIG_EP_PROFILE: 255,
                SIG_EP_TYPE: 255,
                SIG_EP_INPUT: [3],
                SIG_EP_OUTPUT: [6],
            }
        },
    }

    class TestCustomCluster(CustomCluster, Basic):
        """Custom cluster for testing quirks v2."""

        class AttributeDefs(BaseAttributeDefs):  # pylint: disable=too-few-public-methods
            """Attribute definitions for the custom cluster."""

            # pylint: disable=disallowed-name
            foo: Final = ZCLAttributeDef(id=0x0000, type=t.uint8_t)
            # pylint: disable=disallowed-name
            bar: Final = ZCLAttributeDef(id=0x0000, type=t.uint8_t)
            # pylint: disable=disallowed-name, invalid-name
            report: Final = ZCLAttributeDef(id=0x0000, type=t.uint8_t)

    entry = (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .filter(signature_matches(signature))
        .adds(
            TestCustomCluster,
            constant_attributes={TestCustomCluster.AttributeDefs.foo: 3},
        )
        .adds(OnOff.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .add_to_registry()
    )

    # coverage for overridden __eq__ method
    assert entry.adds_metadata[0] != entry.adds_metadata[1]
    assert entry.adds_metadata[0] != entry

    quirked = registry.get_device(device_mock)
    assert isinstance(quirked, CustomDeviceV2)
    assert quirked in registry
    # this would need to be updated if the line number of the call to QuirkBuilder
    # changes in this test in the future
    assert str(quirked.quirk_metadata.quirk_file).endswith(
        "zigpy/tests/test_quirks_v2.py"
    )
    assert quirked.quirk_metadata.quirk_file_line == 103

    ep = quirked.endpoints[1]

    assert ep.basic is not None
    assert isinstance(ep.basic, Basic)
    assert isinstance(ep.basic, TestCustomCluster)
    # pylint: disable=protected-access
    assert ep.basic._CONSTANT_ATTRIBUTES[TestCustomCluster.AttributeDefs.foo.name] == 3

    assert ep.on_off is not None
    assert isinstance(ep.on_off, OnOff)

    additional_entities = quirked.exposes_metadata[
        (1, OnOff.cluster_id, ClusterType.Server)
    ]
    assert len(additional_entities) == 1
    assert additional_entities[0].endpoint_id == 1
    assert additional_entities[0].cluster_id == OnOff.cluster_id
    assert additional_entities[0].cluster_type == ClusterType.Server
    assert (
        additional_entities[0].attribute_name
        == OnOff.AttributeDefs.start_up_on_off.name
    )
    assert additional_entities[0].enum == OnOff.StartUpOnOff
    assert additional_entities[0].entity_type == EntityType.CONFIG

    registry.remove(quirked)
    assert quirked not in registry


async def test_quirks_v2_model_manufacturer(device_mock):
    """Test the potential exceptions when model and manufacturer are set up incorrectly."""
    registry = DeviceRegistry()

    with pytest.raises(
        ValueError,
        match="manufacturer and model must be provided together or completely omitted.",
    ):
        (
            QuirkBuilder(device_mock.manufacturer, model=None, registry=registry)
            .adds(Basic.cluster_id)
            .adds(OnOff.cluster_id)
            .enum(
                OnOff.AttributeDefs.start_up_on_off.name,
                OnOff.StartUpOnOff,
                OnOff.cluster_id,
            )
            .add_to_registry()
        )

    with pytest.raises(
        ValueError,
        match="manufacturer and model must be provided together or completely omitted.",
    ):
        (
            QuirkBuilder(manufacturer=None, model=device_mock.model, registry=registry)
            .adds(Basic.cluster_id)
            .adds(OnOff.cluster_id)
            .enum(
                OnOff.AttributeDefs.start_up_on_off.name,
                OnOff.StartUpOnOff,
                OnOff.cluster_id,
            )
            .add_to_registry()
        )

    with pytest.raises(
        ValueError,
        match="At least one manufacturer and model must be specified for a v2 quirk.",
    ):
        (
            QuirkBuilder(registry=registry)
            .adds(Basic.cluster_id)
            .adds(OnOff.cluster_id)
            .enum(
                OnOff.AttributeDefs.start_up_on_off.name,
                OnOff.StartUpOnOff,
                OnOff.cluster_id,
                translation_key="start_up_on_off",
                fallback_name="Start up on/off",
            )
            .add_to_registry()
        )


async def test_quirks_v2_quirk_builder_cloning(device_mock):
    """Test the quirk builder clone functionality."""
    registry = DeviceRegistry()

    base = (
        QuirkBuilder(registry=registry)
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .applies_to("foo", "bar")
    )

    cloned = base.clone()
    base.add_to_registry()

    (
        cloned.adds(PowerConfiguration.cluster_id)
        .applies_to(device_mock.manufacturer, device_mock.model)
        .add_to_registry()
    )

    quirked = registry.get_device(device_mock)
    assert isinstance(quirked, CustomDeviceV2)
    assert (
        quirked.endpoints[1].in_clusters.get(PowerConfiguration.cluster_id) is not None
    )


async def test_quirks_v2_signature_match(device_mock):
    """Test the signature_matches filter."""
    registry = DeviceRegistry()

    signature_no_match = {
        SIG_MODELS_INFO: (("manufacturer", "model"),),
        SIG_ENDPOINTS: {
            1: {
                SIG_EP_PROFILE: 260,
                SIG_EP_TYPE: 255,
                SIG_EP_INPUT: [3],
            }
        },
    }

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .filter(signature_matches(signature_no_match))
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .add_to_registry()
    )

    quirked = registry.get_device(device_mock)
    assert not isinstance(quirked, CustomDeviceV2)


async def test_quirks_v2_multiple_matches_raises(device_mock):
    """Test that adding multiple quirks v2 entries for the same device raises."""
    registry = DeviceRegistry()

    entry1 = (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .add_to_registry()
    )

    entry2 = (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .adds(Identify.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .add_to_registry()
    )

    assert entry1 != entry2
    assert entry1 != registry

    with pytest.raises(
        MultipleQuirksMatchException, match="Multiple matches found for device"
    ):
        registry.get_device(device_mock)


async def test_quirks_v2_multiple_matches_not_raises(device_mock):
    """Test that adding multiple quirks v2 entries for the same device doesn't raise.

    When the quirk is EXACTLY the same the semantics of sets prevents us from
    having multiple quirks in the registry.
    """
    registry = DeviceRegistry()

    entry1 = (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .add_to_registry()
    )

    entry2 = (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .add_to_registry()
    )

    assert entry1 == entry2
    assert entry1 != registry
    assert isinstance(registry.get_device(device_mock), CustomDeviceV2)


async def test_quirks_v2_with_custom_device_class(device_mock):
    """Test adding a quirk with a custom device class to the registry."""
    registry = DeviceRegistry()

    class CustomTestDevice(CustomDeviceV2):
        """Custom test device for testing quirks v2."""

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .device_class(CustomTestDevice)
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .add_to_registry()
    )

    assert isinstance(registry.get_device(device_mock), CustomTestDevice)


async def test_quirks_v2_with_node_descriptor(device_mock):
    """Test adding a quirk with an overridden node descriptor to the registry."""
    registry = DeviceRegistry()

    node_descriptor = NodeDescriptor(
        logical_type=LogicalType.Router,
        complex_descriptor_available=0,
        user_descriptor_available=0,
        reserved=0,
        aps_flags=0,
        frequency_band=NodeDescriptor.FrequencyBand.Freq2400MHz,
        mac_capability_flags=NodeDescriptor.MACCapabilityFlags.AllocateAddress,
        manufacturer_code=4174,
        maximum_buffer_size=82,
        maximum_incoming_transfer_size=82,
        server_mask=0,
        maximum_outgoing_transfer_size=82,
        descriptor_capability_field=NodeDescriptor.DescriptorCapability.NONE,
    )

    assert device_mock.node_desc != node_descriptor

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .node_descriptor(node_descriptor)
        .add_to_registry()
    )

    quirked: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked, CustomDeviceV2)
    assert quirked.node_desc == node_descriptor


async def test_quirks_v2_replace_occurrences(device_mock):
    """Test adding a quirk that replaces all occurrences of a cluster."""
    registry = DeviceRegistry()

    device_mock[1].add_output_cluster(Identify.cluster_id)

    device_mock.add_endpoint(2)
    device_mock[2].profile_id = 255
    device_mock[2].device_type = 255
    device_mock[2].add_input_cluster(Identify.cluster_id)

    device_mock.add_endpoint(3)
    device_mock[3].profile_id = 255
    device_mock[3].device_type = 255
    device_mock[3].add_output_cluster(Identify.cluster_id)

    class CustomIdentifyCluster(CustomCluster, Identify):
        """Custom identify cluster for testing quirks v2."""

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .replace_cluster_occurrences(CustomIdentifyCluster)
        .add_to_registry()
    )

    quirked: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked, CustomDeviceV2)

    assert isinstance(
        quirked.endpoints[1].in_clusters[Identify.cluster_id], CustomIdentifyCluster
    )
    assert isinstance(
        quirked.endpoints[1].out_clusters[Identify.cluster_id], CustomIdentifyCluster
    )
    assert isinstance(
        quirked.endpoints[2].in_clusters[Identify.cluster_id], CustomIdentifyCluster
    )
    assert isinstance(
        quirked.endpoints[3].out_clusters[Identify.cluster_id], CustomIdentifyCluster
    )


async def test_quirks_v2_skip_configuration(device_mock):
    """Test adding a quirk that skips configuration to the registry."""
    registry = DeviceRegistry()

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .skip_configuration()
        .add_to_registry()
    )

    quirked: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked, CustomDeviceV2)
    assert quirked.skip_configuration is True


async def test_quirks_v2_removes(device_mock):
    """Test adding a quirk that removes a cluster to the registry."""
    registry = DeviceRegistry()

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .removes(Identify.cluster_id)
        .add_to_registry()
    )

    quirked_device: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked_device, CustomDeviceV2)

    assert quirked_device.endpoints[1].in_clusters.get(Identify.cluster_id) is None


async def test_quirks_v2_apply_custom_configuration(device_mock):
    """Test adding a quirk custom configuration to the registry."""
    registry = DeviceRegistry()

    class CustomOnOffCluster(CustomCluster, OnOff):
        """Custom on off cluster for testing quirks v2."""

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(CustomOnOffCluster)
        .adds(CustomOnOffCluster, cluster_type=ClusterType.Client)
        .add_to_registry()
    )

    quirked_device: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked_device, CustomDeviceV2)

    # pylint: disable=line-too-long
    quirked_cluster: CustomOnOffCluster = quirked_device.endpoints[1].in_clusters[
        CustomOnOffCluster.cluster_id
    ]
    assert isinstance(quirked_cluster, CustomOnOffCluster)

    quirked_cluster.apply_custom_configuration = AsyncMock()

    quirked_client_cluster: CustomOnOffCluster = quirked_device.endpoints[
        1
    ].out_clusters[CustomOnOffCluster.cluster_id]
    assert isinstance(quirked_client_cluster, CustomOnOffCluster)

    quirked_client_cluster.apply_custom_configuration = AsyncMock()

    await quirked_device.apply_custom_configuration()

    assert quirked_cluster.apply_custom_configuration.await_count == 1
    assert quirked_client_cluster.apply_custom_configuration.await_count == 1


async def test_quirks_v2_sensor(device_mock):
    """Test adding a quirk that defines a sensor to the registry."""
    registry = DeviceRegistry()

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(OnOff.cluster_id)
        .sensor(
            OnOff.AttributeDefs.on_time.name,
            OnOff.cluster_id,
            translation_key="on_time",
            fallback_name="On time",
        )
        .add_to_registry()
    )

    quirked_device: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked_device, CustomDeviceV2)

    assert quirked_device.endpoints[1].in_clusters.get(OnOff.cluster_id) is not None

    # pylint: disable=line-too-long
    sensor_metadata: EntityMetadata = quirked_device.exposes_metadata[
        (1, OnOff.cluster_id, ClusterType.Server)
    ][0]
    assert sensor_metadata.entity_type == EntityType.STANDARD
    assert sensor_metadata.entity_platform == EntityPlatform.SENSOR
    assert sensor_metadata.cluster_id == OnOff.cluster_id
    assert sensor_metadata.endpoint_id == 1
    assert sensor_metadata.cluster_type == ClusterType.Server
    assert isinstance(sensor_metadata, ZCLSensorMetadata)
    assert sensor_metadata.attribute_name == OnOff.AttributeDefs.on_time.name
    assert sensor_metadata.divisor == 1
    assert sensor_metadata.multiplier == 1


async def test_quirks_v2_sensor_validation_failure_no_translation_key(device_mock):
    """Test translation key and device class both not set causes exception."""
    registry = DeviceRegistry()

    with pytest.raises(ValueError, match="must have a translation_key or device_class"):
        (
            QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
            .adds(OnOff.cluster_id)
            .sensor(
                OnOff.AttributeDefs.on_time.name,
                OnOff.cluster_id,
                fallback_name="On time",
            )
            .add_to_registry()
        )


async def test_quirks_v2_switch(device_mock):
    """Test adding a quirk that defines a switch to the registry."""
    registry = DeviceRegistry()

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(OnOff.cluster_id)
        .switch(
            OnOff.AttributeDefs.on_time.name,
            OnOff.cluster_id,
            force_inverted=True,
            invert_attribute_name=OnOff.AttributeDefs.off_wait_time.name,
            translation_key="on_time",
            fallback_name="On time",
        )
        .add_to_registry()
    )

    quirked_device: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked_device, CustomDeviceV2)

    assert quirked_device.endpoints[1].in_clusters.get(OnOff.cluster_id) is not None

    switch_metadata: EntityMetadata = quirked_device.exposes_metadata[
        (1, OnOff.cluster_id, ClusterType.Server)
    ][0]
    assert switch_metadata.entity_type == EntityType.CONFIG
    assert switch_metadata.entity_platform == EntityPlatform.SWITCH
    assert switch_metadata.cluster_id == OnOff.cluster_id
    assert switch_metadata.endpoint_id == 1
    assert switch_metadata.cluster_type == ClusterType.Server
    assert isinstance(switch_metadata, SwitchMetadata)
    assert switch_metadata.attribute_name == OnOff.AttributeDefs.on_time.name
    assert switch_metadata.force_inverted is True
    assert (
        switch_metadata.invert_attribute_name == OnOff.AttributeDefs.off_wait_time.name
    )


async def test_quirks_v2_number(device_mock):
    """Test adding a quirk that defines a number to the registry."""
    registry = DeviceRegistry()

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(OnOff.cluster_id)
        .number(
            OnOff.AttributeDefs.on_time.name,
            OnOff.cluster_id,
            min_value=0,
            max_value=100,
            step=1,
            unit="s",
            translation_key="on_time",
            fallback_name="On time",
        )
        .add_to_registry()
    )

    quirked_device: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked_device, CustomDeviceV2)

    assert quirked_device.endpoints[1].in_clusters.get(OnOff.cluster_id) is not None

    # pylint: disable=line-too-long
    number_metadata: EntityMetadata = quirked_device.exposes_metadata[
        (1, OnOff.cluster_id, ClusterType.Server)
    ][0]
    assert number_metadata.entity_type == EntityType.CONFIG
    assert number_metadata.entity_platform == EntityPlatform.NUMBER
    assert number_metadata.cluster_id == OnOff.cluster_id
    assert number_metadata.endpoint_id == 1
    assert number_metadata.cluster_type == ClusterType.Server
    assert isinstance(number_metadata, NumberMetadata)
    assert number_metadata.attribute_name == OnOff.AttributeDefs.on_time.name
    assert number_metadata.min == 0
    assert number_metadata.max == 100
    assert number_metadata.step == 1
    assert number_metadata.unit == "s"
    assert number_metadata.mode is None
    assert number_metadata.multiplier is None


async def test_quirks_v2_binary_sensor(device_mock):
    """Test adding a quirk that defines a binary sensor to the registry."""
    registry = DeviceRegistry()

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(OnOff.cluster_id)
        .binary_sensor(
            OnOff.AttributeDefs.on_off.name,
            OnOff.cluster_id,
            translation_key="on_off",
            fallback_name="On/off",
        )
        .add_to_registry()
    )

    quirked_device: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked_device, CustomDeviceV2)

    assert quirked_device.endpoints[1].in_clusters.get(OnOff.cluster_id) is not None

    # pylint: disable=line-too-long
    binary_sensor_metadata: EntityMetadata = quirked_device.exposes_metadata[
        (1, OnOff.cluster_id, ClusterType.Server)
    ][0]
    assert binary_sensor_metadata.entity_type == EntityType.DIAGNOSTIC
    assert binary_sensor_metadata.entity_platform == EntityPlatform.BINARY_SENSOR
    assert binary_sensor_metadata.cluster_id == OnOff.cluster_id
    assert binary_sensor_metadata.endpoint_id == 1
    assert binary_sensor_metadata.cluster_type == ClusterType.Server
    assert isinstance(binary_sensor_metadata, BinarySensorMetadata)
    assert binary_sensor_metadata.attribute_name == OnOff.AttributeDefs.on_off.name


async def test_quirks_v2_write_attribute_button(device_mock):
    """Test adding a quirk that defines a write attr button to the registry."""
    registry = DeviceRegistry()

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(OnOff.cluster_id)
        .write_attr_button(
            OnOff.AttributeDefs.on_time.name,
            20,
            OnOff.cluster_id,
            translation_key="on_time",
            fallback_name="On time",
        )
        .add_to_registry()
    )

    quirked_device: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked_device, CustomDeviceV2)

    assert quirked_device.endpoints[1].in_clusters.get(OnOff.cluster_id) is not None

    # pylint: disable=line-too-long
    write_attribute_button: EntityMetadata = quirked_device.exposes_metadata[
        (1, OnOff.cluster_id, ClusterType.Server)
    ][0]
    assert write_attribute_button.entity_type == EntityType.CONFIG
    assert write_attribute_button.entity_platform == EntityPlatform.BUTTON
    assert write_attribute_button.cluster_id == OnOff.cluster_id
    assert write_attribute_button.endpoint_id == 1
    assert write_attribute_button.cluster_type == ClusterType.Server
    assert isinstance(write_attribute_button, WriteAttributeButtonMetadata)
    assert write_attribute_button.attribute_name == OnOff.AttributeDefs.on_time.name
    assert write_attribute_button.attribute_value == 20


async def test_quirks_v2_command_button(device_mock):
    """Test adding a quirk that defines a command button to the registry."""
    registry = DeviceRegistry()

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(OnOff.cluster_id)
        .command_button(
            OnOff.ServerCommandDefs.on_with_timed_off.name,
            OnOff.cluster_id,
            command_kwargs={"on_off_control": OnOff.OnOffControl.Accept_Only_When_On},
            translation_key="on_with_timed_off",
            fallback_name="On with timed off",
        )
        .command_button(
            OnOff.ServerCommandDefs.on_with_timed_off.name,
            OnOff.cluster_id,
            command_kwargs={
                "on_off_control_foo": OnOff.OnOffControl.Accept_Only_When_On
            },
            translation_key="on_with_timed_off",
            fallback_name="On with timed off",
        )
        .command_button(
            OnOff.ServerCommandDefs.on_with_timed_off.name,
            OnOff.cluster_id,
            translation_key="on_with_timed_off",
            fallback_name="On with timed off",
        )
        .add_to_registry()
    )

    quirked_device: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked_device, CustomDeviceV2)

    assert quirked_device.endpoints[1].in_clusters.get(OnOff.cluster_id) is not None

    button: EntityMetadata = quirked_device.exposes_metadata[
        (1, OnOff.cluster_id, ClusterType.Server)
    ][0]
    assert button.entity_type == EntityType.CONFIG
    assert button.entity_platform == EntityPlatform.BUTTON
    assert button.cluster_id == OnOff.cluster_id
    assert button.endpoint_id == 1
    assert button.cluster_type == ClusterType.Server
    assert isinstance(button, ZCLCommandButtonMetadata)
    assert button.command_name == OnOff.ServerCommandDefs.on_with_timed_off.name
    assert len(button.kwargs) == 1
    assert button.kwargs["on_off_control"] == OnOff.OnOffControl.Accept_Only_When_On

    # coverage for overridden eq method
    assert (
        button
        != quirked_device.exposes_metadata[(1, OnOff.cluster_id, ClusterType.Server)][1]
    )
    assert button != quirked_device

    button = quirked_device.exposes_metadata[(1, OnOff.cluster_id, ClusterType.Server)][
        2
    ]

    assert button.kwargs == {}
    assert button.args == ()


async def test_quirks_v2_also_applies_to(device_mock):
    """Test adding the same quirk for multiple manufacturers and models."""
    registry = DeviceRegistry()

    class CustomTestDevice(CustomDeviceV2):
        """Custom test device for testing quirks v2."""

    (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .also_applies_to("manufacturer2", "model2")
        .also_applies_to("manufacturer3", "model3")
        .device_class(CustomTestDevice)
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .add_to_registry()
    )

    assert isinstance(registry.get_device(device_mock), CustomTestDevice)

    device_mock.manufacturer = "manufacturer2"
    device_mock.model = "model2"
    assert isinstance(registry.get_device(device_mock), CustomTestDevice)

    device_mock.manufacturer = "manufacturer3"
    device_mock.model = "model3"
    assert isinstance(registry.get_device(device_mock), CustomTestDevice)


async def test_quirks_v2_with_custom_device_class_raises(device_mock):
    """Test adding a quirk with a custom device class to the registry raises

    if the class is not a subclass of CustomDeviceV2.
    """
    registry = DeviceRegistry()

    class CustomTestDevice(CustomDevice):
        """Custom test device for testing quirks v2."""

    with pytest.raises(
        AssertionError,
        match="is not a subclass of CustomDeviceV2",
    ):
        (
            QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
            .device_class(CustomTestDevice)
            .adds(Basic.cluster_id)
            .adds(OnOff.cluster_id)
            .enum(
                OnOff.AttributeDefs.start_up_on_off.name,
                OnOff.StartUpOnOff,
                OnOff.cluster_id,
            )
            .add_to_registry()
        )


async def test_quirks_v2_matches_v1(app_mock):
    """Test that quirks v2 entries are equivalent to quirks v1."""
    registry = DeviceRegistry()

    class PowerConfig1CRCluster(CustomCluster, PowerConfiguration):
        """Updating power attributes: 1 CR2032."""

        _CONSTANT_ATTRIBUTES = {
            PowerConfiguration.AttributeDefs.battery_size.id: 10,
            PowerConfiguration.AttributeDefs.battery_quantity.id: 1,
            PowerConfiguration.AttributeDefs.battery_rated_voltage.id: 30,
        }

    class ScenesCluster(CustomCluster, Scenes):
        """Ikea Scenes cluster."""

        server_commands = Scenes.server_commands.copy()
        server_commands.update(
            {
                0x0007: ZCLCommandDef(
                    "press",
                    {"param1": t.int16s, "param2": t.int8s, "param3": t.int8s},
                    False,
                    is_manufacturer_specific=True,
                ),
                0x0008: ZCLCommandDef(
                    "hold",
                    {"param1": t.int16s, "param2": t.int8s},
                    False,
                    is_manufacturer_specific=True,
                ),
                0x0009: ZCLCommandDef(
                    "release",
                    {
                        "param1": t.int16s,
                    },
                    False,
                    is_manufacturer_specific=True,
                ),
            }
        )

    # pylint: disable=invalid-name
    SHORT_PRESS = "remote_button_short_press"
    TURN_ON = "turn_on"
    COMMAND = "command"
    COMMAND_RELEASE = "release"
    COMMAND_TOGGLE = "toggle"
    CLUSTER_ID = "cluster_id"
    ENDPOINT_ID = "endpoint_id"
    PARAMS = "params"
    LONG_PRESS = "remote_button_long_press"
    triggers = {
        (SHORT_PRESS, TURN_ON): {
            COMMAND: COMMAND_TOGGLE,
            CLUSTER_ID: 6,
            ENDPOINT_ID: 1,
        },
        (LONG_PRESS, TURN_ON): {
            COMMAND: COMMAND_RELEASE,
            CLUSTER_ID: 5,
            ENDPOINT_ID: 1,
            PARAMS: {"param1": 0},
        },
    }

    class IkeaTradfriRemote3(CustomDevice):
        """Custom device representing variation of IKEA five button remote."""

        signature = {
            # <SimpleDescriptor endpoint=1 profile=260 device_type=2064
            # device_version=2
            # input_clusters=[0, 1, 3, 9, 2821, 4096]
            # output_clusters=[3, 4, 5, 6, 8, 25, 4096]>
            SIG_MODELS_INFO: [("IKEA of Sweden", "TRADFRI remote control")],
            SIG_ENDPOINTS: {
                1: {
                    SIG_EP_PROFILE: zha.PROFILE_ID,
                    SIG_EP_TYPE: zha.DeviceType.COLOR_SCENE_CONTROLLER,
                    SIG_EP_INPUT: [
                        Basic.cluster_id,
                        PowerConfiguration.cluster_id,
                        Identify.cluster_id,
                        Alarms.cluster_id,
                        Diagnostic.cluster_id,
                        LightLink.cluster_id,
                    ],
                    SIG_EP_OUTPUT: [
                        Identify.cluster_id,
                        Groups.cluster_id,
                        Scenes.cluster_id,
                        OnOff.cluster_id,
                        LevelControl.cluster_id,
                        Ota.cluster_id,
                        LightLink.cluster_id,
                    ],
                }
            },
        }

        replacement = {
            SIG_ENDPOINTS: {
                1: {
                    SIG_EP_PROFILE: zha.PROFILE_ID,
                    SIG_EP_TYPE: zha.DeviceType.COLOR_SCENE_CONTROLLER,
                    SIG_EP_INPUT: [
                        Basic.cluster_id,
                        PowerConfig1CRCluster,
                        Identify.cluster_id,
                        Alarms.cluster_id,
                        LightLink.cluster_id,
                    ],
                    SIG_EP_OUTPUT: [
                        Identify.cluster_id,
                        Groups.cluster_id,
                        ScenesCluster,
                        OnOff.cluster_id,
                        LevelControl.cluster_id,
                        Ota.cluster_id,
                        LightLink.cluster_id,
                    ],
                }
            }
        }

        device_automation_triggers = triggers

    ieee = sentinel.ieee
    nwk = 0x2233
    ikea_device = Device(app_mock, ieee, nwk)

    ikea_device.add_endpoint(1)
    ikea_device[1].profile_id = zha.PROFILE_ID
    ikea_device[1].device_type = zha.DeviceType.COLOR_SCENE_CONTROLLER
    ikea_device.model = "TRADFRI remote control"
    ikea_device.manufacturer = "IKEA of Sweden"
    ikea_device[1].add_input_cluster(Basic.cluster_id)
    ikea_device[1].add_input_cluster(PowerConfiguration.cluster_id)
    ikea_device[1].add_input_cluster(Identify.cluster_id)
    ikea_device[1].add_input_cluster(Alarms.cluster_id)
    ikea_device[1].add_input_cluster(Diagnostic.cluster_id)
    ikea_device[1].add_input_cluster(LightLink.cluster_id)

    ikea_device[1].add_output_cluster(Identify.cluster_id)
    ikea_device[1].add_output_cluster(Groups.cluster_id)
    ikea_device[1].add_output_cluster(Scenes.cluster_id)
    ikea_device[1].add_output_cluster(OnOff.cluster_id)
    ikea_device[1].add_output_cluster(LevelControl.cluster_id)
    ikea_device[1].add_output_cluster(Ota.cluster_id)
    ikea_device[1].add_output_cluster(LightLink.cluster_id)

    registry.add_to_registry(IkeaTradfriRemote3)

    quirked = registry.get_device(ikea_device)

    assert isinstance(quirked, IkeaTradfriRemote3)

    registry = DeviceRegistry()

    (
        QuirkBuilder(ikea_device.manufacturer, ikea_device.model, registry=registry)
        .replaces(PowerConfig1CRCluster)
        .replaces(ScenesCluster, cluster_type=ClusterType.Client)
        .device_automation_triggers(triggers)
        .add_to_registry()
    )

    quirked_v2 = registry.get_device(ikea_device)

    assert isinstance(quirked_v2, CustomDeviceV2)

    assert len(quirked_v2.endpoints[1].in_clusters) == 6
    assert len(quirked_v2.endpoints[1].out_clusters) == 7

    assert isinstance(
        quirked_v2.endpoints[1].in_clusters[PowerConfig1CRCluster.cluster_id],
        PowerConfig1CRCluster,
    )

    assert isinstance(
        quirked_v2.endpoints[1].out_clusters[ScenesCluster.cluster_id], ScenesCluster
    )

    for cluster_id, cluster in quirked.endpoints[1].in_clusters.items():
        assert isinstance(
            quirked_v2.endpoints[1].in_clusters[cluster_id], type(cluster)
        )

    for cluster_id, cluster in quirked.endpoints[1].out_clusters.items():
        assert isinstance(
            quirked_v2.endpoints[1].out_clusters[cluster_id], type(cluster)
        )

    assert quirked.device_automation_triggers == quirked_v2.device_automation_triggers


async def test_quirks_v2_add_to_registry_v2_logs_error(caplog):
    """Test adding a quirk with old API logs."""
    registry = DeviceRegistry()

    (
        add_to_registry_v2("foo", "bar", registry=registry)
        .adds(OnOff.cluster_id)
        .binary_sensor(
            OnOff.AttributeDefs.on_off.name,
            OnOff.cluster_id,
            translation_key="on_off",
            fallback_name="On/off",
        )
        .add_to_registry()
    )

    assert (
        "add_to_registry_v2 is deprecated and will be removed in a future release"
        in caplog.text
    )


async def test_quirks_v2_friendly_name(device_mock: Device) -> None:
    registry = DeviceRegistry()

    entry = (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .friendly_name(model="Real Model Name", manufacturer="Real Manufacturer")
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .add_to_registry()
    )

    assert entry.friendly_name is not None
    assert entry.friendly_name.model == "Real Model Name"
    assert entry.friendly_name.manufacturer == "Real Manufacturer"


async def test_quirks_v2_no_friendly_name(device_mock: Device) -> None:
    registry = DeviceRegistry()

    entry = (
        QuirkBuilder(device_mock.manufacturer, device_mock.model, registry=registry)
        .adds(Basic.cluster_id)
        .adds(OnOff.cluster_id)
        .enum(
            OnOff.AttributeDefs.start_up_on_off.name,
            OnOff.StartUpOnOff,
            OnOff.cluster_id,
            translation_key="start_up_on_off",
            fallback_name="Start up on/off",
        )
        .add_to_registry()
    )

    assert entry.friendly_name is None
