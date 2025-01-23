from collections import deque
from unittest import mock

import pytest

from zigpy.const import SIG_MODELS_INFO
from zigpy.quirks.registry import DeviceRegistry


class FakeDevice:
    def __init__(self):
        self.signature = {}


@pytest.fixture
def fake_dev():
    return FakeDevice()


def test_add_to_registry_new_sig(fake_dev):
    fake_dev.signature = {
        1: {},
        2: {},
        3: {
            "manufacturer": mock.sentinel.legacy_manufacturer,
            "model": mock.sentinel.legacy_model,
        },
        "endpoints": {
            1: {
                "manufacturer": mock.sentinel.manufacturer,
                "model": mock.sentinel.model,
            }
        },
        "manufacturer": mock.sentinel.dev_manufacturer,
        "model": mock.sentinel.dev_model,
    }

    reg = DeviceRegistry()
    reg.add_to_registry(fake_dev)

    assert reg._registry_v1[mock.sentinel.dev_manufacturer][
        mock.sentinel.dev_model
    ] == deque([fake_dev])


def test_add_to_registry_models_info(fake_dev):
    fake_dev.signature = {
        1: {},
        2: {},
        3: {
            "manufacturer": mock.sentinel.legacy_manufacturer,
            "model": mock.sentinel.legacy_model,
        },
        "endpoints": {
            1: {
                "manufacturer": mock.sentinel.manufacturer,
                "model": mock.sentinel.model,
            }
        },
        SIG_MODELS_INFO: [
            (mock.sentinel.manuf_1, mock.sentinel.model_1),
            (mock.sentinel.manuf_2, mock.sentinel.model_2),
        ],
    }

    reg = DeviceRegistry()
    reg.add_to_registry(fake_dev)

    assert reg._registry_v1[mock.sentinel.manuf_1][mock.sentinel.model_1] == deque(
        [fake_dev]
    )
    assert reg._registry_v1[mock.sentinel.manuf_2][mock.sentinel.model_2] == deque(
        [fake_dev]
    )


def test_remove_new_sig(fake_dev):
    fake_dev.signature = {
        1: {},
        2: {},
        3: {
            "manufacturer": mock.sentinel.legacy_manufacturer,
            "model": mock.sentinel.legacy_model,
        },
        "endpoints": {
            1: {
                "manufacturer": mock.sentinel.manufacturer,
                "model": mock.sentinel.model,
            }
        },
        "manufacturer": mock.sentinel.dev_manufacturer,
        "model": mock.sentinel.dev_model,
    }

    reg = DeviceRegistry()

    quirk_list = mock.MagicMock()
    model_dict = mock.MagicMock(spec_set=dict)
    model_dict.__getitem__.return_value = quirk_list
    manuf_dict = mock.MagicMock()
    manuf_dict.__getitem__.return_value = model_dict
    reg._registry_v1 = manuf_dict

    reg.remove(fake_dev)
    assert manuf_dict.__getitem__.call_count == 1
    assert manuf_dict.__getitem__.call_args[0][0] is mock.sentinel.dev_manufacturer
    assert model_dict.__getitem__.call_count == 1
    assert model_dict.__getitem__.call_args[0][0] is mock.sentinel.dev_model
    assert quirk_list.insert.call_count == 0
    assert quirk_list.remove.call_count == 1
    assert quirk_list.remove.call_args[0][0] is fake_dev


def test_remove_models_info(fake_dev):
    fake_dev.signature = {
        1: {},
        2: {},
        3: {
            "manufacturer": mock.sentinel.legacy_manufacturer,
            "model": mock.sentinel.legacy_model,
        },
        "endpoints": {
            1: {
                "manufacturer": mock.sentinel.manufacturer,
                "model": mock.sentinel.model,
            }
        },
        SIG_MODELS_INFO: [
            (mock.sentinel.manuf_1, mock.sentinel.model_1),
            (mock.sentinel.manuf_2, mock.sentinel.model_2),
        ],
    }

    reg = DeviceRegistry()

    quirk_list = mock.MagicMock()
    model_dict = mock.MagicMock(spec_set=dict)
    model_dict.__getitem__.return_value = quirk_list
    manuf_dict = mock.MagicMock()
    manuf_dict.__getitem__.return_value = model_dict
    reg._registry_v1 = manuf_dict

    reg.remove(fake_dev)
    assert manuf_dict.__getitem__.call_count == 2
    assert manuf_dict.__getitem__.call_args_list[0][0][0] is mock.sentinel.manuf_1
    assert manuf_dict.__getitem__.call_args_list[1][0][0] is mock.sentinel.manuf_2
    assert model_dict.__getitem__.call_count == 2
    assert model_dict.__getitem__.call_args_list[0][0][0] is mock.sentinel.model_1
    assert model_dict.__getitem__.call_args_list[1][0][0] is mock.sentinel.model_2
    assert quirk_list.insert.call_count == 0
    assert quirk_list.remove.call_count == 2
    assert quirk_list.remove.call_args_list[0][0][0] is fake_dev
    assert quirk_list.remove.call_args_list[1][0][0] is fake_dev


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_property_accessors():
    reg = DeviceRegistry()
    assert reg.registry is reg._registry_v1
    assert reg.registry_v1 is reg._registry_v1
    assert reg.registry_v2 is reg._registry_v2
