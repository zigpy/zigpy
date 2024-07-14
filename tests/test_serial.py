from __future__ import annotations

import pytest
import asyncio
import unittest.mock

import zigpy.serial
from zigpy.typing import UNDEFINED, UndefinedType

# fmt: off
@pytest.mark.parametrize(("url", "flow_control", "xonxoff", "rtscts", "expected_kwargs"), [
    # `flow_control` on its own
    ("/dev/ttyUSB1", "hardware", UNDEFINED, UNDEFINED, {"xonxoff": False, "rtscts": True}),
    ("/dev/ttyUSB1", "software", UNDEFINED, UNDEFINED, {"xonxoff": True,  "rtscts": False}),
    ("/dev/ttyUSB1", None,       UNDEFINED, UNDEFINED, {"xonxoff": False, "rtscts": False}),

    # `flow_control` overrides `xonxoff` and `rtscts`
    ("/dev/ttyUSB1", "hardware", True,      False,     {"xonxoff": False, "rtscts": True}),
    ("/dev/ttyUSB1", "software", False,      True,     {"xonxoff": True,  "rtscts": False}),
    ("/dev/ttyUSB1", None,       True,      False,     {"xonxoff": False, "rtscts": False}),

    # `flow_control` defaults to undefined so `xonxoff` and `rtscts` are used
    ("/dev/ttyUSB1", UNDEFINED,  True,      False,     {"xonxoff": True,  "rtscts": False}),
    ("/dev/ttyUSB1", UNDEFINED,  False,      True,     {"xonxoff": False, "rtscts": True}),
    ("/dev/ttyUSB1", UNDEFINED,  True,       True,     {"xonxoff": True,  "rtscts": True}),

    # The defaults are used when `flow_control`, `xonxoff`, and `rtscts` are all undefined
    ("/dev/ttyUSB1", UNDEFINED,  UNDEFINED, UNDEFINED, {"xonxoff": False, "rtscts": False}),
])
# fmt: on
async def test_serial_normal(
    url: str,
    flow_control: str | UndefinedType,
    xonxoff: bool | UndefinedType,
    rtscts: bool | UndefinedType,
    expected_kwargs: dict[str, bool],
) -> None:
    loop = asyncio.get_running_loop()
    protocol_factory = unittest.mock.Mock()

    kwargs = {"url": url}

    if flow_control is not UNDEFINED:
        kwargs["flow_control"] = flow_control

    if xonxoff is not UNDEFINED:
        kwargs["xonxoff"] = xonxoff

    if rtscts is not UNDEFINED:
        kwargs["rtscts"] = rtscts

    with unittest.mock.patch(
        "zigpy.serial.pyserial_asyncio.create_serial_connection",
        unittest.mock.AsyncMock(
            return_value=(unittest.mock.AsyncMock(), unittest.mock.AsyncMock())
        ),
    ) as mock_create_serial_connection:
        await zigpy.serial.create_serial_connection(loop, protocol_factory, **kwargs)

    mock_calls = mock_create_serial_connection.mock_calls
    assert len(mock_calls) == 1

    assert mock_calls[0].kwargs["url"] == "/dev/ttyUSB1"
    assert mock_calls[0].kwargs["baudrate"] == 115200

    for kwarg in expected_kwargs:
        assert mock_calls[0].kwargs[kwarg] == expected_kwargs[kwarg]


async def test_serial_socket() -> None:
    loop = asyncio.get_running_loop()
    protocol_factory = unittest.mock.Mock()

    with unittest.mock.patch.object(
        loop,
        "create_connection",
        unittest.mock.AsyncMock(
            return_value=(unittest.mock.AsyncMock(), unittest.mock.AsyncMock())
        ),
    ):
        await zigpy.serial.create_serial_connection(
            loop, protocol_factory, "socket://1.2.3.4:5678"
        )
        await zigpy.serial.create_serial_connection(
            loop, protocol_factory, "socket://1.2.3.4"
        )

        assert len(loop.create_connection.mock_calls) == 2
        assert loop.create_connection.mock_calls[0].kwargs["host"] == "1.2.3.4"
        assert loop.create_connection.mock_calls[0].kwargs["port"] == 5678
        assert loop.create_connection.mock_calls[1].kwargs["host"] == "1.2.3.4"
        assert loop.create_connection.mock_calls[1].kwargs["port"] == 6638
