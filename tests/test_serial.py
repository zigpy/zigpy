from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

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
    protocol_factory = Mock()

    kwargs = {"url": url}

    if flow_control is not UNDEFINED:
        kwargs["flow_control"] = flow_control

    if xonxoff is not UNDEFINED:
        kwargs["xonxoff"] = xonxoff

    if rtscts is not UNDEFINED:
        kwargs["rtscts"] = rtscts

    with patch(
        "zigpy.serial.pyserial_asyncio.create_serial_connection",
        AsyncMock(
            return_value=(AsyncMock(), AsyncMock())
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
    protocol_factory = Mock()

    with patch.object(
        loop,
        "create_connection",
        AsyncMock(
            return_value=(AsyncMock(), AsyncMock())
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


async def test_pyserial_error_remapping(tmp_path: pathlib.Path) -> None:
    loop = asyncio.get_running_loop()
    protocol_factory = Mock()

    # FileNotFoundError
    missing_port = tmp_path / "missing"
    assert not missing_port.exists()

    with pytest.raises(FileNotFoundError):
        await zigpy.serial.create_serial_connection(
            loop, protocol_factory, url=missing_port
        )

    # PermissionError
    denied_port = tmp_path / "denied"
    denied_port.touch()
    denied_port.chmod(0o000)

    with pytest.raises(PermissionError):
        await zigpy.serial.create_serial_connection(
            loop, protocol_factory, url=denied_port
        )

    # IsADirectoryError
    a_folder = tmp_path / "a_folder"
    a_folder.mkdir()

    with pytest.raises(IsADirectoryError):
        await zigpy.serial.create_serial_connection(
            loop, protocol_factory, url=a_folder
        )


async def test_serial_protocol() -> None:
    class SampleSerialProtocol(zigpy.serial.SerialProtocol):
        pass

    loop = asyncio.get_running_loop()

    protocol = SampleSerialProtocol()

    transport = Mock()
    loop.call_soon(protocol.connection_made, transport)

    # Connect
    await protocol.wait_until_connected()

    # Receive some data
    protocol.data_received(b"Hello")
    protocol.data_received(b" ")
    protocol.data_received(b"world")
    assert protocol._buffer == b"Hello world"

    # Close the transport
    asyncio.get_event_loop().call_soon(protocol.connection_lost, None)
    await protocol.disconnect()
    assert transport.close.mock_calls == [call()]
