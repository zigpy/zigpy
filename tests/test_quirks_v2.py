"""Tests for the quirks v2 module."""

from typing import Final

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
from zigpy.quirks.v2 import CustomDeviceV2, EntityType, add_to_registry_v2
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

from .async_mock import sentinel


@pytest.fixture(name="device_mock")
def real_device(app_mock):
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

        class AttributeDefs(
            BaseAttributeDefs
        ):  # pylint: disable=too-few-public-methods
            """Attribute definitions for the custom cluster."""

            # pylint: disable=disallowed-name
            foo: Final = ZCLAttributeDef(id=0x0000, type=t.uint8_t)
            # pylint: disable=disallowed-name
            bar: Final = ZCLAttributeDef(id=0x0000, type=t.uint8_t)
            # pylint: disable=disallowed-name, invalid-name
            report: Final = ZCLAttributeDef(id=0x0000, type=t.uint8_t)

    # fmt: off
    add_to_registry_v2(device_mock.manufacturer, device_mock.model, registry=registry) \
        .filter(signature_matches(signature)) \
        .adds(
            TestCustomCluster,
            constant_attributes={TestCustomCluster.AttributeDefs.foo: 3},
            zcl_init_attributes={TestCustomCluster.AttributeDefs.bar},
            zcl_report_config={TestCustomCluster.AttributeDefs.report: (1, 2, 3)}) \
        .adds(OnOff.cluster_id) \
        .enum(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
    # fmt: on

    quirked = registry.get_device(device_mock)
    assert isinstance(quirked, CustomDeviceV2)

    ep = quirked.endpoints[1]

    assert ep.basic is not None
    assert isinstance(ep.basic, Basic)
    assert isinstance(ep.basic, TestCustomCluster)
    # pylint: disable=protected-access
    assert ep.basic._CONSTANT_ATTRIBUTES[TestCustomCluster.AttributeDefs.foo.name] == 3
    assert (
        TestCustomCluster.AttributeDefs.bar.name
        in ep.basic.application_metadata.zcl_init_attributes
    )
    assert len(ep.basic.application_metadata.zcl_init_attributes) == 1
    assert ep.basic.application_metadata.zcl_report_config[
        TestCustomCluster.AttributeDefs.report.name
    ] == (1, 2, 3)
    assert len(ep.basic.application_metadata.zcl_report_config) == 1

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
        additional_entities[0].entity_metadata.attribute_name
        == OnOff.AttributeDefs.start_up_on_off.name
    )
    assert additional_entities[0].entity_metadata.enum == OnOff.StartUpOnOff
    assert additional_entities[0].entity_type == EntityType.CONFIG


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
    # fmt: off
    add_to_registry_v2(device_mock.manufacturer, device_mock.model, registry=registry) \
        .filter(signature_matches(signature_no_match)) \
        .adds(Basic.cluster_id) \
        .adds(OnOff.cluster_id) \
        .enum(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
    # fmt: on

    quirked = registry.get_device(device_mock)
    assert not isinstance(quirked, CustomDeviceV2)


async def test_quirks_v2_multiple_matches_raises(device_mock):
    """Test that adding multiple quirks v2 entries for the same device raises."""
    registry = DeviceRegistry()

    # fmt: off
    add_to_registry_v2(device_mock.manufacturer, device_mock.model, registry=registry) \
        .adds(Basic.cluster_id) \
        .adds(OnOff.cluster_id) \
        .enum(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
    # fmt: on

    # fmt: off
    add_to_registry_v2(device_mock.manufacturer, device_mock.model, registry=registry) \
        .adds(Basic.cluster_id) \
        .adds(OnOff.cluster_id) \
        .enum(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
    # fmt: on

    with pytest.raises(
        MultipleQuirksMatchException, match="Multiple matches found for device"
    ):
        registry.get_device(device_mock)


async def test_quirks_v2_with_custom_device_class(device_mock):
    """Test adding a quirk with a custom device class to the registry."""
    registry = DeviceRegistry()

    class CustomTestDevice(CustomDeviceV2):
        """Custom test device for testing quirks v2."""

    # fmt: off
    add_to_registry_v2(device_mock.manufacturer, device_mock.model, registry=registry) \
        .device_class(CustomTestDevice) \
        .adds(Basic.cluster_id) \
        .adds(OnOff.cluster_id) \
        .enum(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
    # fmt: on

    assert isinstance(registry.get_device(device_mock), CustomTestDevice)


async def test_quirks_v2_removes(device_mock):
    """Test adding a quirk that removes a cluster to the registry."""
    registry = DeviceRegistry()

    # fmt: off
    add_to_registry_v2(device_mock.manufacturer, device_mock.model, registry=registry) \
        .removes(Identify.cluster_id)
    # fmt: on

    quirked_device: CustomDeviceV2 = registry.get_device(device_mock)
    assert isinstance(quirked_device, CustomDeviceV2)

    assert quirked_device.endpoints[1].in_clusters.get(Identify.cluster_id) is None


async def test_quirks_v2_also_applies_to(device_mock):
    """Test adding the same quirk for multiple manufacturers and models."""
    registry = DeviceRegistry()

    class CustomTestDevice(CustomDeviceV2):
        """Custom test device for testing quirks v2."""

    # fmt: off
    add_to_registry_v2(device_mock.manufacturer, device_mock.model, registry=registry) \
        .also_applies_to("manufacturer2", "model2") \
        .also_applies_to("manufacturer3", "model3") \
        .device_class(CustomTestDevice) \
        .adds(Basic.cluster_id) \
        .adds(OnOff.cluster_id) \
        .enum(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
    # fmt: on

    assert isinstance(registry.get_device(device_mock), CustomTestDevice)

    device_mock.manufacturer = "manufacturer2"
    device_mock.model = "model2"
    assert isinstance(registry.get_device(device_mock), CustomTestDevice)

    device_mock.manufacturer = "manufacturer3"
    device_mock.model = "model3"
    assert isinstance(registry.get_device(device_mock), CustomTestDevice)


async def test_quirks_v2_with_custom_device_class_raises(device_mock):
    """Test adding a quirk with a custom device class to the registry raises

    if the class is not a subclass of CustomDeviceV2."""
    registry = DeviceRegistry()

    class CustomTestDevice(CustomDevice):
        """Custom test device for testing quirks v2."""

    with pytest.raises(
        AssertionError,
        match="is not a subclass of CustomDeviceV2",
    ):
        # fmt: off
        add_to_registry_v2(device_mock.manufacturer, device_mock.model, registry=registry) \
            .device_class(CustomTestDevice) \
            .adds(Basic.cluster_id) \
            .adds(OnOff.cluster_id) \
            .enum(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
        # fmt: on


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
    # fmt: off
    add_to_registry_v2(ikea_device.manufacturer, ikea_device.model, registry=registry) \
        .replaces(PowerConfig1CRCluster) \
        .replaces(ScenesCluster, cluster_type=ClusterType.Client)
    # fmt: on

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
