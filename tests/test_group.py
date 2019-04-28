import asyncio
from unittest import mock

import pytest

import zigpy.types as t
from zigpy.application import ControllerApplication
import zigpy.group


@pytest.fixture
def groups():
    app_mock = mock.MagicMock(spec_set=ControllerApplication)
    return device.Device(app_mock, ieee, 65535)

