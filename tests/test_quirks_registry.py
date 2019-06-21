from zigpy.quirks.registry import DeviceRegistry, SIG_MODELS_INFO

import pytest
from unittest import mock


class FakeDevice:
    def __init__(self):
        self.signature = {}


@pytest.fixture
def fake_dev():
    return FakeDevice()


def test_reg_get_model(fake_dev):
    assert DeviceRegistry.get_model(fake_dev) is None

    fake_dev.signature = {
        1: {},
        2: {},
        3: {'model': mock.sentinel.legacy_model},
    }
    assert DeviceRegistry.get_model(fake_dev) is mock.sentinel.legacy_model

    fake_dev.signature = {
        1: {},
        2: {},
        3: {'model': mock.sentinel.legacy_model},
        'endpoints': {
            1: {},
            2: {},
            3: {'model': mock.sentinel.ep_model}
        },
        'model': mock.sentinel.model
    }
    assert DeviceRegistry.get_model(fake_dev) is mock.sentinel.model


def test_reg_get_manufacturer(fake_dev):
    assert DeviceRegistry.get_manufacturer(fake_dev) is None

    fake_dev.signature = {
        1: {},
        2: {},
        3: {'manufacturer': mock.sentinel.legacy_manufacturer},
    }
    assert DeviceRegistry.get_manufacturer(fake_dev) is mock.sentinel.legacy_manufacturer

    fake_dev.signature = {
        1: {},
        2: {},
        3: {'manufacturer': mock.sentinel.legacy_manufacturer},
        'endpoints': {
            1: {},
            2: {},
            3: {'manufacturer': mock.sentinel.ep_manufacturer}
        },
        'manufacturer': mock.sentinel.manufacturer
    }
    assert DeviceRegistry.get_manufacturer(fake_dev) is mock.sentinel.manufacturer


def test_add_to_registry_legacy_sig(fake_dev):
    reg = DeviceRegistry()

    quirk_list = mock.MagicMock()
    model_dict = mock.MagicMock(spec_set=dict)
    model_dict.__getitem__.return_value = quirk_list
    manuf_dict = mock.MagicMock()
    manuf_dict.__getitem__.return_value = model_dict

    reg._registry = manuf_dict

    fake_dev.signature = {
        1: {},
        2: {},
        3: {
            'manufacturer': mock.sentinel.legacy_manufacturer,
            'model': mock.sentinel.legacy_model,
        },
    }

    reg.add_to_registry(fake_dev)
    assert manuf_dict.__getitem__.call_count == 1
    assert manuf_dict.__getitem__.call_args[0][0] is mock.sentinel.legacy_manufacturer
    assert model_dict.__getitem__.call_count == 1
    assert model_dict.__getitem__.call_args[0][0] is mock.sentinel.legacy_model
    assert quirk_list.append.call_count == 1
    assert quirk_list.append.call_args[0][0] is fake_dev


def test_add_to_registry_new_sig(fake_dev):
    fake_dev.signature = {
        1: {},
        2: {},
        3: {
            'manufacturer': mock.sentinel.legacy_manufacturer,
            'model': mock.sentinel.legacy_model,
        },
        'endpoints': {
            1: {
                'manufacturer': mock.sentinel.manufacturer,
                'model': mock.sentinel.model,
            }
        },
        'manufacturer': mock.sentinel.dev_manufacturer,
        'model': mock.sentinel.dev_model,
    }

    reg = DeviceRegistry()

    quirk_list = mock.MagicMock()
    model_dict = mock.MagicMock(spec_set=dict)
    model_dict.__getitem__.return_value = quirk_list
    manuf_dict = mock.MagicMock()
    manuf_dict.__getitem__.return_value = model_dict
    reg._registry = manuf_dict

    reg.add_to_registry(fake_dev)
    assert manuf_dict.__getitem__.call_count == 1
    assert manuf_dict.__getitem__.call_args[0][0] is mock.sentinel.dev_manufacturer
    assert model_dict.__getitem__.call_count == 1
    assert model_dict.__getitem__.call_args[0][0] is mock.sentinel.dev_model
    assert quirk_list.append.call_count == 1
    assert quirk_list.append.call_args[0][0] is fake_dev
    quirk_list.reset_mock()
    model_dict.reset_mock()
    manuf_dict.reset_mock()


def test_add_to_registry_models_info(fake_dev):
    fake_dev.signature = {
        1: {},
        2: {},
        3: {
            'manufacturer': mock.sentinel.legacy_manufacturer,
            'model': mock.sentinel.legacy_model,
        },
        'endpoints': {
            1: {
                'manufacturer': mock.sentinel.manufacturer,
                'model': mock.sentinel.model,
            }
        },
        SIG_MODELS_INFO: [
            (mock.sentinel.manuf_1, mock.sentinel.model_1),
            (mock.sentinel.manuf_2, mock.sentinel.model_2),
        ]
    }

    reg = DeviceRegistry()

    quirk_list = mock.MagicMock()
    model_dict = mock.MagicMock(spec_set=dict)
    model_dict.__getitem__.return_value = quirk_list
    manuf_dict = mock.MagicMock()
    manuf_dict.__getitem__.return_value = model_dict
    reg._registry = manuf_dict

    reg.add_to_registry(fake_dev)
    assert manuf_dict.__getitem__.call_count == 2
    assert manuf_dict.__getitem__.call_args_list[0][0][0] is mock.sentinel.manuf_1
    assert manuf_dict.__getitem__.call_args_list[1][0][0] is mock.sentinel.manuf_2
    assert model_dict.__getitem__.call_count == 2
    assert model_dict.__getitem__.call_args_list[0][0][0] is mock.sentinel.model_1
    assert model_dict.__getitem__.call_args_list[1][0][0] is mock.sentinel.model_2
    assert quirk_list.append.call_count == 2
    assert quirk_list.append.call_args_list[0][0][0] is fake_dev
    assert quirk_list.append.call_args_list[1][0][0] is fake_dev
    quirk_list.reset_mock()
    model_dict.reset_mock()
    manuf_dict.reset_mock()


def test_remove_legacy_sig(fake_dev):
    reg = DeviceRegistry()

    quirk_list = mock.MagicMock()
    model_dict = mock.MagicMock(spec_set=dict)
    model_dict.__getitem__.return_value = quirk_list
    manuf_dict = mock.MagicMock()
    manuf_dict.__getitem__.return_value = model_dict

    reg._registry = manuf_dict

    fake_dev.signature = {
        1: {},
        2: {},
        3: {
            'manufacturer': mock.sentinel.legacy_manufacturer,
            'model': mock.sentinel.legacy_model,
        },
    }

    reg.remove(fake_dev)
    assert manuf_dict.__getitem__.call_count == 1
    assert manuf_dict.__getitem__.call_args[0][0] is mock.sentinel.legacy_manufacturer
    assert model_dict.__getitem__.call_count == 1
    assert model_dict.__getitem__.call_args[0][0] is mock.sentinel.legacy_model
    assert quirk_list.append.call_count == 0
    assert quirk_list.remove.call_count == 1
    assert quirk_list.remove.call_args[0][0] is fake_dev


def test_remove_new_sig(fake_dev):
    fake_dev.signature = {
        1: {},
        2: {},
        3: {
            'manufacturer': mock.sentinel.legacy_manufacturer,
            'model': mock.sentinel.legacy_model,
        },
        'endpoints': {
            1: {
                'manufacturer': mock.sentinel.manufacturer,
                'model': mock.sentinel.model,
            }
        },
        'manufacturer': mock.sentinel.dev_manufacturer,
        'model': mock.sentinel.dev_model,
    }

    reg = DeviceRegistry()

    quirk_list = mock.MagicMock()
    model_dict = mock.MagicMock(spec_set=dict)
    model_dict.__getitem__.return_value = quirk_list
    manuf_dict = mock.MagicMock()
    manuf_dict.__getitem__.return_value = model_dict
    reg._registry = manuf_dict

    reg.remove(fake_dev)
    assert manuf_dict.__getitem__.call_count == 1
    assert manuf_dict.__getitem__.call_args[0][0] is mock.sentinel.dev_manufacturer
    assert model_dict.__getitem__.call_count == 1
    assert model_dict.__getitem__.call_args[0][0] is mock.sentinel.dev_model
    assert quirk_list.append.call_count == 0
    assert quirk_list.remove.call_count == 1
    assert quirk_list.remove.call_args[0][0] is fake_dev


def test_remove_models_info(fake_dev):
    fake_dev.signature = {
        1: {},
        2: {},
        3: {
            'manufacturer': mock.sentinel.legacy_manufacturer,
            'model': mock.sentinel.legacy_model,
        },
        'endpoints': {
            1: {
                'manufacturer': mock.sentinel.manufacturer,
                'model': mock.sentinel.model,
            }
        },
        SIG_MODELS_INFO: [
            (mock.sentinel.manuf_1, mock.sentinel.model_1),
            (mock.sentinel.manuf_2, mock.sentinel.model_2),
        ]
    }

    reg = DeviceRegistry()

    quirk_list = mock.MagicMock()
    model_dict = mock.MagicMock(spec_set=dict)
    model_dict.__getitem__.return_value = quirk_list
    manuf_dict = mock.MagicMock()
    manuf_dict.__getitem__.return_value = model_dict
    reg._registry = manuf_dict

    reg.remove(fake_dev)
    assert manuf_dict.__getitem__.call_count == 2
    assert manuf_dict.__getitem__.call_args_list[0][0][0] is mock.sentinel.manuf_1
    assert manuf_dict.__getitem__.call_args_list[1][0][0] is mock.sentinel.manuf_2
    assert model_dict.__getitem__.call_count == 2
    assert model_dict.__getitem__.call_args_list[0][0][0] is mock.sentinel.model_1
    assert model_dict.__getitem__.call_args_list[1][0][0] is mock.sentinel.model_2
    assert quirk_list.append.call_count == 0
    assert quirk_list.remove.call_count == 2
    assert quirk_list.remove.call_args_list[0][0][0] is fake_dev
    assert quirk_list.remove.call_args_list[1][0][0] is fake_dev


