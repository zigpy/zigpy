import asyncio
import importlib.util
import itertools
import pathlib
import pkgutil
import sys
from typing import Final

import pytest

from zigpy import zcl
from zigpy.const import (
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_MANUFACTURER,
    SIG_MODEL,
    SIG_MODELS_INFO,
    SIG_SKIP_CONFIG,
)
import zigpy.device
import zigpy.endpoint
import zigpy.quirks
from zigpy.quirks.registry import DeviceRegistry
import zigpy.types as t

from .async_mock import AsyncMock, MagicMock, patch, sentinel

ALLOWED_SIGNATURE = {
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_MANUFACTURER,
    SIG_MODEL,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
}
ALLOWED_REPLACEMENT = {SIG_ENDPOINTS}


def test_registry():
    class TestDevice(zigpy.quirks.CustomDevice):
        signature = {SIG_MODEL: "model"}

    assert TestDevice in zigpy.quirks._DEVICE_REGISTRY
    assert zigpy.quirks._DEVICE_REGISTRY.remove(TestDevice) is None  # :-/
    assert TestDevice not in zigpy.quirks._DEVICE_REGISTRY


@pytest.fixture
def real_device(app_mock):
    ieee = sentinel.ieee
    nwk = 0x2233
    real_device = zigpy.device.Device(app_mock, ieee, nwk)

    real_device.add_endpoint(1)
    real_device[1].profile_id = 255
    real_device[1].device_type = 255
    real_device.model = "model"
    real_device.manufacturer = "manufacturer"
    real_device[1].add_input_cluster(3)
    real_device[1].add_output_cluster(6)
    return real_device


@pytest.fixture
def real_device_2(app_mock):
    ieee = sentinel.ieee_2
    nwk = 0x3344
    real_device = zigpy.device.Device(app_mock, ieee, nwk)

    real_device.add_endpoint(1)
    real_device[1].profile_id = 255
    real_device[1].device_type = 255
    real_device.model = "model"
    real_device.manufacturer = "A different manufacturer"
    real_device[1].add_input_cluster(3)
    real_device[1].add_output_cluster(6)
    return real_device


def _dev_reg(device):
    registry = DeviceRegistry()
    registry.add_to_registry(device)
    return registry


def test_get_device_new_sig(real_device):
    class TestDevice:
        signature = {}

        def __init__(*args, **kwargs):
            pass

        def get_signature(self):
            pass

    registry = _dev_reg(TestDevice)

    assert registry.get_device(real_device) is real_device

    TestDevice.signature[SIG_ENDPOINTS] = {1: {SIG_EP_PROFILE: 1}}
    registry = _dev_reg(TestDevice)
    assert registry.get_device(real_device) is real_device

    TestDevice.signature[SIG_ENDPOINTS][1][SIG_EP_PROFILE] = 255
    TestDevice.signature[SIG_ENDPOINTS][1][SIG_EP_TYPE] = 1
    registry = _dev_reg(TestDevice)
    assert registry.get_device(real_device) is real_device

    TestDevice.signature[SIG_ENDPOINTS][1][SIG_EP_TYPE] = 255
    TestDevice.signature[SIG_ENDPOINTS][1][SIG_EP_INPUT] = [1]
    registry = _dev_reg(TestDevice)
    assert registry.get_device(real_device) is real_device

    TestDevice.signature[SIG_ENDPOINTS][1][SIG_EP_INPUT] = [3]
    TestDevice.signature[SIG_ENDPOINTS][1][SIG_EP_OUTPUT] = [1]
    registry = _dev_reg(TestDevice)
    assert registry.get_device(real_device) is real_device

    TestDevice.signature[SIG_ENDPOINTS][1][SIG_EP_OUTPUT] = [6]
    TestDevice.signature[SIG_MODEL] = "x"
    registry = _dev_reg(TestDevice)
    assert registry.get_device(real_device) is real_device

    TestDevice.signature[SIG_MODEL] = "model"
    TestDevice.signature[SIG_MANUFACTURER] = "x"
    registry = _dev_reg(TestDevice)
    assert registry.get_device(real_device) is real_device

    TestDevice.signature[SIG_MANUFACTURER] = "manufacturer"
    registry = _dev_reg(TestDevice)
    assert isinstance(registry.get_device(real_device), TestDevice)

    TestDevice.signature[SIG_ENDPOINTS][2] = {SIG_EP_PROFILE: 2}
    registry = _dev_reg(TestDevice)
    assert registry.get_device(real_device) is real_device
    assert zigpy.quirks.get_device(real_device, registry) is real_device


def test_model_manuf_device_sig(real_device):
    class TestDevice:
        signature = {}

        def __init__(*args, **kwargs):
            pass

        def get_signature(self):
            pass

    registry = DeviceRegistry()
    registry.add_to_registry(TestDevice)

    assert registry.get_device(real_device) is real_device

    TestDevice.signature[SIG_ENDPOINTS] = {
        1: {
            SIG_EP_PROFILE: 255,
            SIG_EP_TYPE: 255,
            SIG_EP_INPUT: [3],
            SIG_EP_OUTPUT: [6],
        }
    }

    TestDevice.signature[SIG_MODEL] = "x"
    assert registry.get_device(real_device) is real_device

    TestDevice.signature[SIG_MODEL] = "model"
    TestDevice.signature[SIG_MANUFACTURER] = "x"
    assert registry.get_device(real_device) is real_device

    TestDevice.signature[SIG_MANUFACTURER] = "manufacturer"
    assert isinstance(registry.get_device(real_device), TestDevice)


def test_custom_devices():
    def _check_range(cluster):
        for left, right in zcl.Cluster._registry_range:
            if left <= cluster <= right:
                return True
        return False

    # Validate that all CustomDevices look sane
    reg = zigpy.quirks._DEVICE_REGISTRY.registry
    candidates = list(
        itertools.chain(*itertools.chain(*[m.values() for m in reg.values()]))
    )

    for device in candidates:
        # enforce new style of signature
        assert SIG_ENDPOINTS in device.signature
        numeric = [eid for eid in device.signature if isinstance(eid, int)]
        assert not numeric

        # Check that the signature data is OK
        signature = device.signature[SIG_ENDPOINTS]
        for profile_id, profile_data in signature.items():
            assert isinstance(profile_id, int)
            assert set(profile_data.keys()) - ALLOWED_SIGNATURE == set()

        # Check that the replacement data is OK
        assert set(device.replacement.keys()) - ALLOWED_REPLACEMENT == set()
        for epid, epdata in device.replacement.get(SIG_ENDPOINTS, {}).items():
            assert (epid in signature) or (
                "profile" in epdata and SIG_EP_TYPE in epdata
            )
            if "profile" in epdata:
                profile = epdata["profile"]
                assert isinstance(profile, int) and 0 <= profile <= 0xFFFF
            if SIG_EP_TYPE in epdata:
                device_type = epdata[SIG_EP_TYPE]
                assert isinstance(device_type, int) and 0 <= device_type <= 0xFFFF

            all_clusters = epdata.get(SIG_EP_INPUT, []) + epdata.get(SIG_EP_OUTPUT, [])
            for cluster in all_clusters:
                assert (
                    (isinstance(cluster, int) and cluster in zcl.Cluster._registry)
                    or (isinstance(cluster, int) and _check_range(cluster))
                    or issubclass(cluster, zcl.Cluster)
                )


def test_custom_device(app_mock):
    class Device(zigpy.quirks.CustomDevice):
        signature = {}

        class MyEndpoint:
            def __init__(self, device, endpoint_id, *args, **kwargs):
                assert args == (sentinel.custom_endpoint_arg, replaces)

        class MyCluster(zigpy.quirks.CustomCluster):
            cluster_id = 0x8888

        replacement = {
            SIG_ENDPOINTS: {
                1: {
                    SIG_EP_PROFILE: sentinel.profile_id,
                    SIG_EP_INPUT: [0x0000, MyCluster],
                    SIG_EP_OUTPUT: [0x0001, MyCluster],
                },
                2: (MyEndpoint, sentinel.custom_endpoint_arg),
            },
            SIG_MODEL: "Mock Model",
            SIG_MANUFACTURER: "Mock Manufacturer",
        }

    class Device2(zigpy.quirks.CustomDevice):
        signature = {}

        class MyEndpoint:
            def __init__(self, device, endpoint_id, *args, **kwargs):
                assert args == (sentinel.custom_endpoint_arg, replaces)

        class MyCluster(zigpy.quirks.CustomCluster):
            cluster_id = 0x8888

        replacement = {
            SIG_ENDPOINTS: {
                1: {
                    SIG_EP_PROFILE: sentinel.profile_id,
                    SIG_EP_INPUT: [0x0000, MyCluster],
                    SIG_EP_OUTPUT: [0x0001, MyCluster],
                },
                2: (MyEndpoint, sentinel.custom_endpoint_arg),
            },
            SIG_MODEL: "Mock Model",
            SIG_MANUFACTURER: "Mock Manufacturer",
            SIG_SKIP_CONFIG: True,
        }

    assert 0x8888 not in zcl.Cluster._registry

    replaces = MagicMock()
    replaces[1].device_type = sentinel.device_type
    test_device = Device(app_mock, None, 0x4455, replaces)
    test_device2 = Device2(app_mock, None, 0x4455, replaces)

    assert test_device2.skip_configuration is True

    assert test_device.manufacturer == "Mock Manufacturer"
    assert test_device.model == "Mock Model"
    assert test_device.skip_configuration is False

    assert test_device[1].profile_id == sentinel.profile_id
    assert test_device[1].device_type == sentinel.device_type

    assert 0x0000 in test_device[1].in_clusters
    assert 0x8888 in test_device[1].in_clusters
    assert isinstance(test_device[1].in_clusters[0x8888], Device.MyCluster)

    assert 0x0001 in test_device[1].out_clusters
    assert 0x8888 in test_device[1].out_clusters
    assert isinstance(test_device[1].out_clusters[0x8888], Device.MyCluster)

    assert isinstance(test_device[2], Device.MyEndpoint)

    test_device.add_endpoint(3)
    assert isinstance(test_device[3], zigpy.endpoint.Endpoint)

    assert zigpy.quirks._DEVICE_REGISTRY.remove(Device) is None  # :-/
    assert Device not in zigpy.quirks._DEVICE_REGISTRY


def test_custom_cluster_idx():
    class TestClusterIdx(zigpy.quirks.CustomCluster):
        cluster_id = 0x1234

        class AttributeDefs(zcl.foundation.BaseAttributeDefs):
            first_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x0000, type=t.uint8_t
            )
            second_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x00FF, type=t.enum8
            )

        class ServerCommandDefs(zcl.foundation.BaseCommandDefs):
            server_cmd_0: Final = zcl.foundation.ZCLCommandDef(
                id=0x00,
                schema={"param1": t.uint8_t, "param2": t.uint8_t},
                direction=False,
            )
            server_cmd_2: Final = zcl.foundation.ZCLCommandDef(
                id=0x01,
                schema={"param1": t.uint8_t, "param2": t.uint8_t},
                direction=False,
            )

        class ClientCommandDefs(zcl.foundation.BaseCommandDefs):
            client_cmd_0: Final = zcl.foundation.ZCLCommandDef(
                id=0x00, schema={"param1": t.uint8_t}, direction=True
            )
            client_cmd_1: Final = zcl.foundation.ZCLCommandDef(
                id=0x01, schema={"param1": t.uint8_t}, direction=True
            )

    assert hasattr(TestClusterIdx, "attributes_by_name")
    attr_idx_len = len(TestClusterIdx.attributes_by_name)
    attrs_len = len(TestClusterIdx.attributes)
    assert attr_idx_len == attrs_len
    for attr_name, attr in TestClusterIdx.attributes_by_name.items():
        assert TestClusterIdx.attributes[attr.id].name == attr_name


async def test_read_attributes_uncached():
    class TestCluster(zigpy.quirks.CustomCluster):
        cluster_id = 0x1234
        _CONSTANT_ATTRIBUTES = {0x0001: 5}

        class AttributeDefs(zcl.foundation.BaseAttributeDefs):
            first_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x0000, type=t.uint8_t
            )
            second_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x0001, type=t.uint8_t
            )
            third_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x0002, type=t.uint8_t
            )
            fouth_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x0003, type=t.enum8
            )

        class ServerCommandDefs(zcl.foundation.BaseCommandDefs):
            server_cmd_0: Final = zcl.foundation.ZCLCommandDef(
                id=0x00,
                schema={"param1": t.uint8_t, "param2": t.uint8_t},
                direction=False,
            )
            server_cmd_2: Final = zcl.foundation.ZCLCommandDef(
                id=0x01,
                schema={"param1": t.uint8_t, "param2": t.uint8_t},
                direction=False,
            )

        class ClientCommandDefs(zcl.foundation.BaseCommandDefs):
            client_cmd_0: Final = zcl.foundation.ZCLCommandDef(
                id=0x00, schema={"param1": t.uint8_t}, direction=True
            )
            client_cmd_1: Final = zcl.foundation.ZCLCommandDef(
                id=0x01, schema={"param1": t.uint8_t}, direction=True
            )

    class TestCluster2(zigpy.quirks.CustomCluster):
        cluster_id = 0x1235

        class AttributeDefs(zcl.foundation.BaseAttributeDefs):
            first_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x0000, type=t.uint8_t
            )

    epmock = MagicMock()
    epmock._device.get_sequence.return_value = 123
    epmock.device.get_sequence.return_value = 123
    cluster = TestCluster(epmock, True)
    cluster2 = TestCluster2(epmock, True)

    async def mockrequest(
        foundation, command, schema, args, manufacturer=None, **kwargs
    ):
        assert foundation is True
        assert command == 0x00
        rar0 = _mk_rar(0x0000, 99)
        rar99 = _mk_rar(0x0002, None, 1)
        rar199 = _mk_rar(0x0003, 199)
        return [[rar0, rar99, rar199]]

    # Unknown attribute read passes through
    with pytest.raises(KeyError):
        cluster.get("unknown_attribute", 123)

    assert "unknown_attribute" not in cluster._attr_cache

    # Constant attribute can be read with `get`
    assert cluster.get("second_attribute") == 5
    assert "second_attribute" not in cluster._attr_cache

    # test no constants
    cluster.request = mockrequest
    success, failure = await cluster.read_attributes([0, 2, 3])
    assert success[0x0000] == 99
    assert failure[0x0002] == 1
    assert success[0x0003] == 199
    assert cluster.get(0x0003) == 199

    # test mixed response with constant
    success, failure = await cluster.read_attributes([0, 1, 2, 3])
    assert success[0x0000] == 99
    assert success[0x0001] == 5
    assert failure[0x0002] == 1
    assert success[0x0003] == 199

    # test just constant attr
    success, failure = await cluster.read_attributes([1])
    assert success[1] == 5

    # test just constant attr
    cluster2.request = mockrequest
    success, failure = await cluster2.read_attributes([0, 2, 3])
    assert success[0x0000] == 99
    assert failure[0x0002] == 1
    assert success[0x0003] == 199


async def test_read_attributes_default_response():
    class TestCluster(zigpy.quirks.CustomCluster):
        cluster_id = 0x1234
        _CONSTANT_ATTRIBUTES = {0x0001: 5}

        class AttributeDefs(zcl.foundation.BaseAttributeDefs):
            first_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x0000, type=t.uint8_t
            )
            second_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x0001, type=t.uint8_t
            )
            third_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x0002, type=t.uint8_t
            )
            fouth_attribute: Final = zcl.foundation.ZCLAttributeDef(
                id=0x0003, type=t.enum8
            )

        class ServerCommandDefs(zcl.foundation.BaseCommandDefs):
            server_cmd_0: Final = zcl.foundation.ZCLCommandDef(
                id=0x00,
                schema={"param1": t.uint8_t, "param2": t.uint8_t},
                direction=False,
            )
            server_cmd_2: Final = zcl.foundation.ZCLCommandDef(
                id=0x01,
                schema={"param1": t.uint8_t, "param2": t.uint8_t},
                direction=False,
            )

        class ClientCommandDefs(zcl.foundation.BaseCommandDefs):
            client_cmd_0: Final = zcl.foundation.ZCLCommandDef(
                id=0x00, schema={"param1": t.uint8_t}, direction=True
            )
            client_cmd_1: Final = zcl.foundation.ZCLCommandDef(
                id=0x01, schema={"param1": t.uint8_t}, direction=True
            )

    epmock = MagicMock()
    epmock._device.get_sequence.return_value = 123
    epmock.device.get_sequence.return_value = 123
    cluster = TestCluster(epmock, True)

    async def mockrequest(
        foundation, command, schema, args, manufacturer=None, **kwargs
    ):
        assert foundation is True
        assert command == 0
        return [0xC1]

    cluster.request = mockrequest
    # test constants with errors
    success, failure = await cluster.read_attributes([0, 1, 2, 3], allow_cache=False)
    assert success == {1: 5}
    assert failure == {0: 0xC1, 2: 0xC1, 3: 0xC1}


def _mk_rar(attrid, value, status=0):
    r = zcl.foundation.ReadAttributeRecord()
    r.attrid = attrid
    r.status = status
    r.value = zcl.foundation.TypeValue()
    r.value.value = value
    return r


class ManufacturerSpecificCluster(zigpy.quirks.CustomCluster):
    cluster_id = 0x2222
    ep_attribute = "just_a_cluster"

    class AttributeDefs(zcl.foundation.BaseAttributeDefs):
        attr0: Final = zcl.foundation.ZCLAttributeDef(id=0x0000, type=t.uint8_t)
        attr1: Final = zcl.foundation.ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, is_manufacturer_specific=True
        )

    class ServerCommandDefs(zcl.foundation.BaseCommandDefs):
        server_cmd0: Final = zcl.foundation.ZCLCommandDef(
            id=0x00, schema={}, direction=False
        )
        server_cmd1: Final = zcl.foundation.ZCLCommandDef(
            id=0x01, schema={}, direction=False, is_manufacturer_specific=True
        )

    class ClientCommandDefs(zcl.foundation.BaseCommandDefs):
        client_cmd0: Final = zcl.foundation.ZCLCommandDef(
            id=0x00, schema={}, direction=False
        )
        client_cmd1: Final = zcl.foundation.ZCLCommandDef(
            id=0x01, schema={}, direction=False, is_manufacturer_specific=True
        )


@pytest.fixture
def manuf_cluster():
    """Return a manufacturer specific cluster fixture."""

    ep = MagicMock()
    ep.manufacturer_id = sentinel.manufacturer_id
    return ManufacturerSpecificCluster.from_id(ep, 0x2222)


@pytest.fixture
def manuf_cluster2():
    """Return a manufacturer specific cluster fixture."""

    class ManufCluster2(ManufacturerSpecificCluster):
        ep_attribute = "just_a_manufacturer_specific_cluster"
        cluster_id = 0xFC00

    ep = MagicMock()
    ep.manufacturer_id = sentinel.manufacturer_id2
    cluster = ManufCluster2(ep)
    cluster.cluster_id = 0xFC00
    return cluster


@pytest.mark.parametrize(
    ("cmd_name", "manufacturer"),
    [
        ("client_cmd0", None),
        ("client_cmd1", sentinel.manufacturer_id),
    ],
)
async def test_client_cmd_vendor_specific_by_name(
    manuf_cluster, manuf_cluster2, cmd_name, manufacturer
):
    """Test manufacturer specific client commands."""
    with patch.object(manuf_cluster, "reply", AsyncMock()) as cmd_mock:
        await getattr(manuf_cluster, cmd_name)()
        await asyncio.sleep(0.01)
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1][SIG_MANUFACTURER] is manufacturer

    with patch.object(manuf_cluster2, "reply", AsyncMock()) as cmd_mock:
        await getattr(manuf_cluster2, cmd_name)()
        await asyncio.sleep(0.01)
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1][SIG_MANUFACTURER] is sentinel.manufacturer_id2


@pytest.mark.parametrize(
    ("cmd_name", "manufacturer"),
    [
        ("server_cmd0", None),
        ("server_cmd1", sentinel.manufacturer_id),
    ],
)
async def test_srv_cmd_vendor_specific_by_name(
    manuf_cluster, manuf_cluster2, cmd_name, manufacturer
):
    """Test manufacturer specific server commands."""
    with patch.object(manuf_cluster, "request", AsyncMock()) as cmd_mock:
        await getattr(manuf_cluster, cmd_name)()
        await asyncio.sleep(0.01)
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is manufacturer

    with patch.object(manuf_cluster2, "request", AsyncMock()) as cmd_mock:
        await getattr(manuf_cluster2, cmd_name)()
        await asyncio.sleep(0.01)
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.manufacturer_id2


@pytest.mark.parametrize(
    ("attr_name", "manufacturer"),
    [
        ("attr0", None),
        ("attr1", sentinel.manufacturer_id),
    ],
)
async def test_read_attr_manufacture_specific(
    manuf_cluster, manuf_cluster2, attr_name, manufacturer
):
    """Test manufacturer specific read_attributes command."""
    with patch.object(zcl.Cluster, "_read_attributes", AsyncMock()) as cmd_mock:
        await manuf_cluster.read_attributes([attr_name])
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is manufacturer
        cmd_mock.reset_mock()
        await manuf_cluster.read_attributes(
            [attr_name], manufacturer=sentinel.another_id
        )
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.another_id

    with patch.object(zcl.Cluster, "_read_attributes", AsyncMock()) as cmd_mock:
        await manuf_cluster2.read_attributes([attr_name])
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.manufacturer_id2
        cmd_mock.reset_mock()
        await manuf_cluster2.read_attributes(
            [attr_name], manufacturer=sentinel.another_id
        )
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.another_id


@pytest.mark.parametrize(
    ("attr_name", "manufacturer"),
    [
        ("attr0", None),
        ("attr1", sentinel.manufacturer_id),
    ],
)
async def test_write_attr_manufacture_specific(
    manuf_cluster, manuf_cluster2, attr_name, manufacturer
):
    """Test manufacturer specific write_attributes command."""
    with patch.object(zcl.Cluster, "_write_attributes", AsyncMock()) as cmd_mock:
        await manuf_cluster.write_attributes({attr_name: 0x12})
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is manufacturer
        cmd_mock.reset_mock()
        await manuf_cluster.write_attributes(
            {attr_name: 0x12}, manufacturer=sentinel.another_id
        )
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.another_id

    with patch.object(zcl.Cluster, "_write_attributes", AsyncMock()) as cmd_mock:
        await manuf_cluster2.write_attributes({attr_name: 0x12})
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.manufacturer_id2
        cmd_mock.reset_mock()
        await manuf_cluster2.write_attributes(
            {attr_name: 0x12}, manufacturer=sentinel.another_id
        )
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.another_id


@pytest.mark.parametrize(
    ("attr_name", "manufacturer"),
    [
        ("attr0", None),
        ("attr1", sentinel.manufacturer_id),
    ],
)
async def test_write_attr_undivided_manufacture_specific(
    manuf_cluster, manuf_cluster2, attr_name, manufacturer
):
    """Test manufacturer specific write_attributes_undivided command."""
    with patch.object(
        zcl.Cluster, "_write_attributes_undivided", AsyncMock()
    ) as cmd_mock:
        await manuf_cluster.write_attributes_undivided({attr_name: 0x12})
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is manufacturer
        cmd_mock.reset_mock()
        await manuf_cluster.write_attributes_undivided(
            {attr_name: 0x12}, manufacturer=sentinel.another_id
        )
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.another_id

    with patch.object(
        zcl.Cluster, "_write_attributes_undivided", AsyncMock()
    ) as cmd_mock:
        await manuf_cluster2.write_attributes_undivided({attr_name: 0x12})
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.manufacturer_id2
        cmd_mock.reset_mock()
        await manuf_cluster2.write_attributes_undivided(
            {attr_name: 0x12}, manufacturer=sentinel.another_id
        )
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.another_id


@pytest.mark.parametrize(
    ("attr_name", "manufacturer"),
    [
        ("attr0", None),
        ("attr1", sentinel.manufacturer_id),
    ],
)
async def test_configure_reporting_manufacture_specific(
    manuf_cluster, manuf_cluster2, attr_name, manufacturer
):
    """Test manufacturer specific configure_reporting command."""
    with patch.object(zcl.Cluster, "_configure_reporting", AsyncMock()) as cmd_mock:
        await manuf_cluster.configure_reporting(
            attr_name, min_interval=1, max_interval=1, reportable_change=1
        )
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is manufacturer
        cmd_mock.reset_mock()
        await manuf_cluster.configure_reporting(
            attr_name,
            min_interval=1,
            max_interval=1,
            reportable_change=1,
            manufacturer=sentinel.another_id,
        )
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.another_id

    with patch.object(zcl.Cluster, "_configure_reporting", AsyncMock()) as cmd_mock:
        await manuf_cluster2.configure_reporting(
            attr_name, min_interval=1, max_interval=1, reportable_change=1
        )
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.manufacturer_id2
        cmd_mock.reset_mock()
        await manuf_cluster2.configure_reporting(
            attr_name,
            min_interval=1,
            max_interval=1,
            reportable_change=1,
            manufacturer=sentinel.another_id,
        )
        assert cmd_mock.call_count == 1
        assert cmd_mock.call_args[1]["manufacturer"] is sentinel.another_id


def test_different_manuf_same_model(real_device, real_device_2):
    """Test quirk matching for same model, but different manufacturers."""

    class TestDevice_1(zigpy.quirks.CustomDevice):
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

        def get_signature(self):
            pass

    class TestDevice_2(zigpy.quirks.CustomDevice):
        signature = {
            SIG_MODELS_INFO: (("A different manufacturer", "model"),),
            SIG_ENDPOINTS: {
                1: {
                    SIG_EP_PROFILE: 255,
                    SIG_EP_TYPE: 255,
                    SIG_EP_INPUT: [3],
                    SIG_EP_OUTPUT: [6],
                }
            },
        }

        def get_signature(self):
            pass

    registry = DeviceRegistry()
    registry.add_to_registry(TestDevice_1)

    assert isinstance(registry.get_device(real_device), TestDevice_1)

    assert registry.get_device(real_device_2) is real_device_2
    registry.add_to_registry(TestDevice_2)
    assert isinstance(registry.get_device(real_device_2), TestDevice_2)

    assert not zigpy.quirks.get_quirk_list("manufacturer", "no such model")
    assert not zigpy.quirks.get_quirk_list("manufacturer", "no such model", registry)
    assert not zigpy.quirks.get_quirk_list("A different manufacturer", "no such model")
    assert not zigpy.quirks.get_quirk_list(
        "A different manufacturer", "no such model", registry
    )
    assert not zigpy.quirks.get_quirk_list("no such manufacturer", "model")
    assert not zigpy.quirks.get_quirk_list("no such manufacturer", "model", registry)

    manuf1_list = zigpy.quirks.get_quirk_list("manufacturer", "model", registry)
    assert len(manuf1_list) == 1
    assert manuf1_list[0] is TestDevice_1

    manuf2_list = zigpy.quirks.get_quirk_list(
        "A different manufacturer", "model", registry
    )
    assert len(manuf2_list) == 1
    assert manuf2_list[0] is TestDevice_2


def test_quirk_match_order(real_device, real_device_2):
    """Test quirk matching order to allow user overrides via custom quirks."""

    class BuiltInQuirk(zigpy.quirks.CustomDevice):
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

        def get_signature(self):
            pass

    class CustomQuirk(BuiltInQuirk):
        pass

    registry = DeviceRegistry()
    registry.add_to_registry(BuiltInQuirk)
    # With only a single matching quirk there is no choice but to use the first one
    assert type(registry.get_device(real_device)) is BuiltInQuirk

    registry.add_to_registry(CustomQuirk)
    # A quirk registered later that also matches the device will be preferred
    assert type(registry.get_device(real_device)) is CustomQuirk


def test_quirk_wildcard_manufacturer(real_device, real_device_2):
    """Test quirk matching with a wildcard (None) manufacturer."""

    class BaseDev(zigpy.quirks.CustomDevice):
        def get_signature(self):
            pass

    class ModelsQuirk(BaseDev):
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

    class ModelsQuirkNoMatch(BaseDev):
        # same model and manufacture, different endpoint signature
        signature = {
            SIG_MODELS_INFO: (("manufacturer", "model"),),
            SIG_ENDPOINTS: {
                1: {
                    SIG_EP_PROFILE: 260,
                    SIG_EP_TYPE: 255,
                    SIG_EP_INPUT: [3],
                    SIG_EP_OUTPUT: [6],
                }
            },
        }

    class ModelOnlyQuirk(BaseDev):
        # Wildcard Manufacturer
        signature = {
            SIG_MODEL: "model",
            SIG_ENDPOINTS: {
                1: {
                    SIG_EP_PROFILE: 255,
                    SIG_EP_TYPE: 255,
                    SIG_EP_INPUT: [3],
                    SIG_EP_OUTPUT: [6],
                }
            },
        }

    class ModelOnlyQuirkNoMatch(BaseDev):
        # Wildcard Manufacturer, none matching endpoint signature
        signature = {
            SIG_MODEL: "model",
            SIG_ENDPOINTS: {
                1: {
                    SIG_EP_PROFILE: 260,
                    SIG_EP_TYPE: 255,
                    SIG_EP_INPUT: [3],
                    SIG_EP_OUTPUT: [6],
                }
            },
        }

    registry = DeviceRegistry()
    for quirk in ModelsQuirk, ModelsQuirkNoMatch, ModelOnlyQuirk, ModelOnlyQuirkNoMatch:
        registry.add_to_registry(quirk)

    quirked = registry.get_device(real_device)
    assert isinstance(quirked, ModelsQuirk)

    quirked = registry.get_device(real_device_2)
    assert isinstance(quirked, ModelOnlyQuirk)

    real_device.manufacturer = (
        "We are expected to match a manufacturer wildcard quirk now"
    )
    quirked = registry.get_device(real_device)
    assert isinstance(quirked, ModelOnlyQuirk)

    real_device.model = "And now we should not match any quirk"
    quirked = registry.get_device(real_device)
    assert quirked is real_device


async def test_manuf_id_disable(real_device):
    class TestCluster(ManufacturerSpecificCluster):
        cluster_id = 0xFF00

    real_device.manufacturer_id_override = 0x1234

    ep = real_device.endpoints[1]
    ep.add_input_cluster(TestCluster.cluster_id, TestCluster(ep))
    assert isinstance(ep.just_a_cluster, TestCluster)

    assert ep.manufacturer_id == 0x1234

    # The default behavior for a manufacturer-specific cluster, command, or attribute is
    # to include the manufacturer ID in the request
    with patch.object(ep, "request", AsyncMock()) as request_mock:
        request_mock.return_value = (zcl.foundation.Status.SUCCESS, "done")
        await ep.just_a_cluster.command(
            ep.just_a_cluster.commands_by_name["server_cmd0"].id,
        )
        await ep.just_a_cluster.read_attributes(["attr0"])
        await ep.just_a_cluster.write_attributes({"attr0": 1})

    assert len(request_mock.mock_calls) == 3

    for mock_call in request_mock.mock_calls:
        data = mock_call.kwargs["data"]
        hdr, _ = zcl.foundation.ZCLHeader.deserialize(data)
        assert hdr.manufacturer == 0x1234

    # But it can be disabled by passing NO_MANUFACTURER_ID
    with patch.object(ep, "request", AsyncMock()) as request_mock:
        request_mock.return_value = (zcl.foundation.Status.SUCCESS, "done")
        await ep.just_a_cluster.command(
            ep.just_a_cluster.commands_by_name["server_cmd0"].id,
            manufacturer=zcl.foundation.ZCLHeader.NO_MANUFACTURER_ID,
        )
        await ep.just_a_cluster.read_attributes(
            ["attr0"], manufacturer=zcl.foundation.ZCLHeader.NO_MANUFACTURER_ID
        )
        await ep.just_a_cluster.write_attributes(
            {"attr0": 1}, manufacturer=zcl.foundation.ZCLHeader.NO_MANUFACTURER_ID
        )

    assert len(request_mock.mock_calls) == 3

    for mock_call in request_mock.mock_calls:
        data = mock_call.kwargs["data"]
        hdr, _ = zcl.foundation.ZCLHeader.deserialize(data)
        assert hdr.manufacturer is None


async def test_request_with_kwargs(real_device):
    class CustomLevel(zigpy.quirks.CustomCluster, zcl.clusters.general.LevelControl):
        pass

    class TestQuirk(zigpy.quirks.CustomDevice):
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

        replacement = {
            SIG_ENDPOINTS: {
                1: {
                    SIG_EP_PROFILE: 255,
                    SIG_EP_TYPE: 255,
                    SIG_EP_INPUT: [3, CustomLevel],
                    SIG_EP_OUTPUT: [6],
                }
            },
        }

    registry = DeviceRegistry()
    registry.add_to_registry(TestQuirk)

    quirked = registry.get_device(real_device)
    assert isinstance(quirked, TestQuirk)

    ep = quirked.endpoints[1]

    with patch.object(ep, "request", AsyncMock()) as request_mock:
        ep.device.get_sequence = MagicMock(return_value=1)

        await ep.level.move_to_level(0x00, 123)
        await ep.level.move_to_level(0x00, transition_time=123)
        await ep.level.move_to_level(level=0x00, transition_time=123)

        assert len(request_mock.mock_calls) == 3
        assert all(c == request_mock.mock_calls[0] for c in request_mock.mock_calls)


def test_purge_custom_quirks(tmp_path: pathlib.Path, app_mock) -> None:
    def load_quirks():
        for importer, modname, _ in pkgutil.walk_packages(path=[str(tmp_path)]):
            spec = importer.find_spec(modname)
            module = importlib.util.module_from_spec(spec)
            sys.modules[modname] = module
            spec.loader.exec_module(module)

    (tmp_path / "quirk1.py").write_text("""
import zigpy.quirks
from zigpy.zcl.clusters.general import LevelControl
from zigpy.const import (
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_MODELS_INFO,
)

class CustomLevel1(zigpy.quirks.CustomCluster, LevelControl):
    pass

class TestQuirk1(zigpy.quirks.CustomDevice):
    signature = {
        SIG_MODELS_INFO: (("manufacturer1", "model1"),),
        SIG_ENDPOINTS: {
            1: {
                SIG_EP_PROFILE: 255,
                SIG_EP_TYPE: 255,
                SIG_EP_INPUT: [3],
                SIG_EP_OUTPUT: [6],
            }
        },
    }

    replacement = {
        SIG_ENDPOINTS: {
            1: {
                SIG_EP_PROFILE: 255,
                SIG_EP_TYPE: 255,
                SIG_EP_INPUT: [3, CustomLevel1],
                SIG_EP_OUTPUT: [6],
            }
        },
    }""")

    (tmp_path / "quirk2.py").write_text("""
import zigpy.quirks

from zigpy.quirks.v2 import QuirkBuilder
from zigpy.zcl import ClusterType
from zigpy.zcl.clusters.general import LevelControl

class CustomLevel2(zigpy.quirks.CustomCluster, LevelControl):
    pass

QuirkBuilder("manufacturer2", "model2").adds(
    cluster=CustomLevel2,
    cluster_type=ClusterType.Server,
    endpoint_id=1,
).add_to_registry()
""")

    dev1 = zigpy.device.Device(
        app_mock, t.EUI64.convert("11:11:11:11:11:11:11:11"), 0x1234
    )
    dev1.add_endpoint(1)
    dev1[1].profile_id = 255
    dev1[1].device_type = 255
    dev1.model = "model1"
    dev1.manufacturer = "manufacturer1"
    dev1[1].add_input_cluster(3)
    dev1[1].add_output_cluster(6)

    dev2 = zigpy.device.Device(
        app_mock, t.EUI64.convert("22:22:22:22:22:22:22:22"), 0x5678
    )
    dev2.add_endpoint(1)
    dev2[1].profile_id = 255
    dev2[1].device_type = 255
    dev2.model = "model2"
    dev2.manufacturer = "manufacturer2"
    dev2[1].add_input_cluster(3)
    dev2[1].add_output_cluster(6)

    registry = zigpy.quirks.DEVICE_REGISTRY

    assert not registry._registry.get("manufacturer1", {}).get("model1", [])
    assert not registry._registry_v2.get(("manufacturer2", "model2"), set())

    load_quirks()

    assert registry._registry.get("manufacturer1", {}).get("model1", [])
    assert registry._registry_v2.get(("manufacturer2", "model2"), set())

    assert type(registry.get_device(dev1)).__name__ == "TestQuirk1"
    assert registry.get_device(dev2).quirk_metadata.quirk_file.name == "quirk2.py"

    # Only quirks from the passed directory are purged so this is a no-op
    registry.purge_custom_quirks(tmp_path / "some_other_dir")
    assert registry._registry.get("manufacturer1", {}).get("model1", [])
    assert registry._registry_v2.get(("manufacturer2", "model2"), set())

    # Now we really remove them
    registry.purge_custom_quirks(tmp_path)
    assert not registry._registry.get("manufacturer1", {}).get("model1", [])
    assert not registry._registry_v2.get(("manufacturer2", "model2"), set())

    assert registry.get_device(dev1) is dev1
    assert registry.get_device(dev2) is dev2
