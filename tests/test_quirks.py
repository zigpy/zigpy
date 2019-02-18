from unittest import mock

import zigpy.device
import zigpy.endpoint
import zigpy.quirks
import zigpy.types as t
from zigpy.zcl import Cluster

ALLOWED_SIGNATURE = set([
    'profile_id',
    'device_type',
    'model',
    'manufacturer',
    'input_clusters',
    'output_clusters',
])
ALLOWED_REPLACEMENT = set([
    'endpoints',
])


def test_registry():
    class TestDevice(zigpy.quirks.CustomDevice):
        signature = {}

    assert TestDevice in zigpy.quirks._DEVICE_REGISTRY
    assert zigpy.quirks._DEVICE_REGISTRY.pop() == TestDevice  # :-/


def test_get_device():
    application = mock.sentinel.application
    ieee = mock.sentinel.ieee
    nwk = mock.sentinel.nwk
    real_device = zigpy.device.Device(application, ieee, nwk)

    real_device.add_endpoint(1)
    real_device[1].profile_id = 255
    real_device[1].device_type = 255
    real_device[1].model = 'model'
    real_device[1].manufacturer = 'manufacturer'
    real_device[1].add_input_cluster(3)
    real_device[1].add_output_cluster(6)

    class TestDevice:
        signature = {
        }

        def __init__(*args, **kwargs):
            pass

        def get_signature(self):
            pass

    registry = [TestDevice]

    get_device = zigpy.quirks.get_device

    assert get_device(real_device, registry) is real_device

    TestDevice.signature[1] = {'profile_id': 1}
    assert get_device(real_device, registry) is real_device

    TestDevice.signature[1]['profile_id'] = 255
    TestDevice.signature[1]['device_type'] = 1
    assert get_device(real_device, registry) is real_device

    TestDevice.signature[1]['device_type'] = 255
    TestDevice.signature[1]['model'] = 'x'
    assert get_device(real_device, registry) is real_device

    TestDevice.signature[1]['model'] = 'model'
    TestDevice.signature[1]['manufacturer'] = 'x'
    assert get_device(real_device, registry) is real_device

    TestDevice.signature[1]['manufacturer'] = 'manufacturer'
    TestDevice.signature[1]['input_clusters'] = [1]
    assert get_device(real_device, registry) is real_device

    TestDevice.signature[1]['input_clusters'] = [3]
    TestDevice.signature[1]['output_clusters'] = [1]
    assert get_device(real_device, registry) is real_device

    TestDevice.signature[1]['output_clusters'] = [6]
    assert isinstance(get_device(real_device, registry), TestDevice)


def test_custom_devices():
    def _check_range(cluster):
        for range in Cluster._registry_range.keys():
            if range[0] <= cluster <= range[1]:
                return True
        return False

    # Validate that all CustomDevices look sane
    for device in zigpy.quirks._DEVICE_REGISTRY:
        # Check that the signature data is OK
        for profile_id, profile_data in device.signature.items():
            assert isinstance(profile_id, int)
            assert set(profile_data.keys()) - ALLOWED_SIGNATURE == set()

        # Check that the replacement data is OK
        assert set(device.replacement.keys()) - ALLOWED_REPLACEMENT == set()
        for epid, epdata in device.replacement.get('endpoints', {}).items():
            assert (epid in device.signature) or (
                'profile' in epdata and 'device_type' in epdata)
            if 'profile' in epdata:
                profile = epdata['profile']
                assert isinstance(profile, int) and 0 <= profile <= 0xffff
            if 'device_type' in epdata:
                device_type = epdata['device_type']
                assert isinstance(device_type, int) and 0 <= device_type <= 0xffff

            all_clusters = (epdata.get('input_clusters', []) +
                            epdata.get('output_clusters', []))
            for cluster in all_clusters:
                assert (
                    (isinstance(cluster, int) and cluster in Cluster._registry) or
                    (isinstance(cluster, int) and _check_range(cluster)) or
                    issubclass(cluster, Cluster)
                )


def test_custom_device():
    class Device(zigpy.quirks.CustomDevice):
        signature = {}

        class MyEndpoint:
            def __init__(self, device, endpoint_id, *args, **kwargs):
                assert args == (mock.sentinel.custom_endpoint_arg, replaces)

        class MyCluster(zigpy.quirks.CustomCluster):
            cluster_id = 0x8888

        replacement = {
            'endpoints': {
                1: {
                    'profile_id': mock.sentinel.profile_id,
                    'input_clusters': [0x0000, MyCluster],
                    'output_clusters': [0x0001, MyCluster],
                },
                2: (MyEndpoint, mock.sentinel.custom_endpoint_arg),
            }
        }

    assert 0x8888 not in Cluster._registry

    replaces = mock.MagicMock()
    replaces[1].device_type = mock.sentinel.device_type
    test_device = Device(None, None, None, replaces)
    assert test_device[1].profile_id == mock.sentinel.profile_id
    assert test_device[1].device_type == mock.sentinel.device_type

    assert 0x0000 in test_device[1].in_clusters
    assert 0x8888 in test_device[1].in_clusters
    assert isinstance(test_device[1].in_clusters[0x8888], Device.MyCluster)

    assert 0x0001 in test_device[1].out_clusters
    assert 0x8888 in test_device[1].out_clusters
    assert isinstance(test_device[1].out_clusters[0x8888], Device.MyCluster)

    assert isinstance(test_device[2], Device.MyEndpoint)

    test_device.add_endpoint(3)
    assert isinstance(test_device[3], zigpy.endpoint.Endpoint)

    assert zigpy.quirks._DEVICE_REGISTRY.pop() == Device  # :-/


def test_kof_no_reply():
    class TestCluster(zigpy.quirks.kof.NoReplyMixin, zigpy.quirks.CustomCluster):
        cluster_id = 0x1234
        void_input_commands = [0x0002]
        server_commands = {
            0x0001: ('noop', (), False),
            0x0002: ('noop_noreply', (), False),
        }
        client_commands = {}

    ep = mock.MagicMock()
    cluster = TestCluster(ep)

    cluster.command(0x0001)
    ep.request.assert_called_with(mock.ANY, mock.ANY, mock.ANY, expect_reply=True)
    ep.reset_mock()

    cluster.command(0x0001, expect_reply=False)
    ep.request.assert_called_with(mock.ANY, mock.ANY, mock.ANY, expect_reply=False)
    ep.reset_mock()

    cluster.command(0x0002)
    ep.request.assert_called_with(mock.ANY, mock.ANY, mock.ANY, expect_reply=False)
    ep.reset_mock()

    cluster.command(0x0002, expect_reply=True)
    ep.request.assert_called_with(mock.ANY, mock.ANY, mock.ANY, expect_reply=True)
    ep.reset_mock()


def test_custom_cluster_idx():
    class TestClusterIdx(zigpy.quirks.CustomCluster):
        cluster_Id = 0x1234
        attributes = {
            0x0000: ('first_attribute', t.uint8_t),
            0x00ff: ('2nd_attribute', t.enum8)
        }
        server_commands = {
            0x00: ('server_cmd_0', (t.uint8_t, t.uint8_t), False),
            0x01: ('server_cmd_2', (t.uint8_t, t.uint8_t), False),
        }
        client_commands = {
            0x00: ('client_cmd_0', (t.uint8_t, ), True),
            0x01: ('client_cmd_1', (t.uint8_t, ), True),
        }

    def _test_cmd(cmd_set, cmd_set_idx):
        assert hasattr(TestClusterIdx, cmd_set_idx)
        idx_len = len(getattr(TestClusterIdx, cmd_set_idx))
        cmd_set_len = len(getattr(TestClusterIdx, cmd_set))
        assert idx_len == cmd_set_len
        for cmd_name, cmd_id in getattr(TestClusterIdx, cmd_set_idx).items():
            assert getattr(TestClusterIdx, cmd_set)[cmd_id][0] == cmd_name

    assert hasattr(TestClusterIdx, '_attridx')
    attr_idx_len = len(TestClusterIdx._attridx)
    attrs_len = len(TestClusterIdx.attributes)
    assert attr_idx_len == attrs_len
    for attr_name, attr_id in TestClusterIdx._attridx.items():
        assert TestClusterIdx.attributes[attr_id][0] == attr_name

    _test_cmd('server_commands', '_server_command_idx')
    _test_cmd('client_commands', '_client_command_idx')
