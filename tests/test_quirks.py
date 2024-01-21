import asyncio
import itertools
from typing import Final

import pytest

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
from zigpy.exceptions import MultipleQuirksMatchException
from zigpy.profiles import zha
import zigpy.quirks
from zigpy.quirks.registry import DeviceRegistry, HAEntityType, signature_matches
import zigpy.types as t
import zigpy.zcl as zcl
from zigpy.zcl import ClusterType, foundation
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
        for range in zcl.Cluster._registry_range:
            if range[0] <= cluster <= range[1]:
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
    "cmd_name, manufacturer",
    (
        ("client_cmd0", None),
        ("client_cmd1", sentinel.manufacturer_id),
    ),
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
    "cmd_name, manufacturer",
    (
        ("server_cmd0", None),
        ("server_cmd1", sentinel.manufacturer_id),
    ),
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
    "attr_name, manufacturer",
    (
        ("attr0", None),
        ("attr1", sentinel.manufacturer_id),
    ),
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
    "attr_name, manufacturer",
    (
        ("attr0", None),
        ("attr1", sentinel.manufacturer_id),
    ),
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
    "attr_name, manufacturer",
    (
        ("attr0", None),
        ("attr1", sentinel.manufacturer_id),
    ),
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
    "attr_name, manufacturer",
    (
        ("attr0", None),
        ("attr1", sentinel.manufacturer_id),
    ),
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
        data = mock_call.args[2]
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
        data = mock_call.args[2]
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


async def test_quirks_v2(real_device):
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

    # fmt: off
    registry.add_to_registry_v2(real_device.manufacturer, real_device.model) \
        .matches(signature_matches(signature)) \
        .adds(Basic.cluster_id) \
        .adds(OnOff.cluster_id) \
        .exposes_enum_select(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
    # fmt: on

    quirked = registry.get_device(real_device)
    assert isinstance(quirked, zigpy.quirks.CustomDeviceV2)

    ep = quirked.endpoints[1]

    assert ep.basic is not None
    assert isinstance(ep.basic, Basic)

    assert ep.on_off is not None
    assert isinstance(ep.on_off, OnOff)

    additional_entities = quirked.exposes_metadata[
        (1, OnOff.cluster_id, zcl.ClusterType.Server)
    ]
    assert len(additional_entities) == 1
    assert additional_entities[0].endpoint_id == 1
    assert additional_entities[0].cluster_id == OnOff.cluster_id
    assert additional_entities[0].cluster_type == zcl.ClusterType.Server
    assert (
        additional_entities[0].entity_metadata.attribute_name
        == OnOff.AttributeDefs.start_up_on_off.name
    )
    assert additional_entities[0].entity_metadata.enum == OnOff.StartUpOnOff
    assert additional_entities[0].entity_metadata.ha_entity_type == HAEntityType.CONFIG


async def test_quirks_v2_signature_match(real_device):
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
    registry.add_to_registry_v2(real_device.manufacturer, real_device.model) \
        .matches(signature_matches(signature_no_match)) \
        .adds(Basic.cluster_id) \
        .adds(OnOff.cluster_id) \
        .exposes_enum_select(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
    # fmt: on

    quirked = registry.get_device(real_device)
    assert not isinstance(quirked, zigpy.quirks.CustomDeviceV2)


async def test_quirks_v2_multiple_matches_raises(real_device):
    registry = DeviceRegistry()

    # fmt: off
    registry.add_to_registry_v2(real_device.manufacturer, real_device.model) \
        .adds(Basic.cluster_id) \
        .adds(OnOff.cluster_id) \
        .exposes_enum_select(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
    # fmt: on

    # fmt: off
    registry.add_to_registry_v2(real_device.manufacturer, real_device.model) \
        .adds(Basic.cluster_id) \
        .adds(OnOff.cluster_id) \
        .exposes_enum_select(OnOff.AttributeDefs.start_up_on_off.name, OnOff.StartUpOnOff, OnOff.cluster_id)
    # fmt: on

    with pytest.raises(
        MultipleQuirksMatchException, match="Multiple matches found for device"
    ):
        registry.get_device(real_device)


async def test_quirks_v2_matches_v1(app_mock):
    registry = DeviceRegistry()

    class PowerConfig1CRCluster(zigpy.quirks.CustomCluster, PowerConfiguration):
        """Updating power attributes: 1 CR2032."""

        _CONSTANT_ATTRIBUTES = {
            PowerConfiguration.AttributeDefs.battery_size.id: 10,
            PowerConfiguration.AttributeDefs.battery_quantity.id: 1,
            PowerConfiguration.AttributeDefs.battery_rated_voltage.id: 30,
        }

    class ScenesCluster(zigpy.quirks.CustomCluster, Scenes):
        """Ikea Scenes cluster."""

        server_commands = Scenes.server_commands.copy()
        server_commands.update(
            {
                0x0007: foundation.ZCLCommandDef(
                    "press",
                    {"param1": t.int16s, "param2": t.int8s, "param3": t.int8s},
                    False,
                    is_manufacturer_specific=True,
                ),
                0x0008: foundation.ZCLCommandDef(
                    "hold",
                    {"param1": t.int16s, "param2": t.int8s},
                    False,
                    is_manufacturer_specific=True,
                ),
                0x0009: foundation.ZCLCommandDef(
                    "release",
                    {
                        "param1": t.int16s,
                    },
                    False,
                    is_manufacturer_specific=True,
                ),
            }
        )

    class IkeaTradfriRemote3(zigpy.quirks.CustomDevice):
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
    ikea_device = zigpy.device.Device(app_mock, ieee, nwk)

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
    registry.add_to_registry_v2(ikea_device.manufacturer, ikea_device.model) \
        .replaces(PowerConfig1CRCluster) \
        .replaces(ScenesCluster, cluster_type=ClusterType.Client)
    # fmt: on

    quirked_v2 = registry.get_device(ikea_device)

    assert isinstance(quirked_v2, zigpy.quirks.CustomDeviceV2)

    assert len(quirked_v2.endpoints[1].in_clusters) == 6
    assert len(quirked_v2.endpoints[1].out_clusters) == 7

    assert isinstance(
        quirked_v2.endpoints[1].in_clusters[PowerConfig1CRCluster.cluster_id],
        PowerConfig1CRCluster,
    )

    assert isinstance(
        quirked_v2.endpoints[1].out_clusters[ScenesCluster.cluster_id], ScenesCluster
    )

    for id, cluster in quirked.endpoints[1].in_clusters.items():
        assert isinstance(quirked_v2.endpoints[1].in_clusters[id], type(cluster))

    for id, cluster in quirked.endpoints[1].out_clusters.items():
        assert isinstance(quirked_v2.endpoints[1].out_clusters[id], type(cluster))
