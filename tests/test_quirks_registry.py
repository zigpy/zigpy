from zigpy.quirks.registry import DeviceRegistry

from unittest import mock


def test_reg_get_model():
    class FakeDevice:
        def __init__(self):
            self.signature = {}

    fake_dev = FakeDevice()

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
    }
    assert DeviceRegistry.get_model(fake_dev) is mock.sentinel.ep_model

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


def test_reg_get_manufacturer():
    class FakeDevice:
        def __init__(self):
            self.signature = {}

    fake_dev = FakeDevice()

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
    }
    assert DeviceRegistry.get_manufacturer(fake_dev) is mock.sentinel.ep_manufacturer

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
