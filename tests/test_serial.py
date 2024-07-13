import unittest.mock

import zigpy.serial


@unittest.mock.patch(
    "zigpy.serial.pyserial_asyncio.create_serial_connection",
    unittest.mock.AsyncMock(
        return_value=(unittest.mock.AsyncMock(), unittest.mock.AsyncMock())
    ),
)
async def test_serial_normal(event_loop):
    protocol_factory = unittest.mock.Mock()

    await zigpy.serial.create_serial_connection(
        event_loop, protocol_factory, "/dev/ttyUSB1"
    )

    mock_calls = zigpy.serial.pyserial_asyncio.create_serial_connection.mock_calls
    assert len(mock_calls) == 1
    assert mock_calls[0].kwargs["url"] == "/dev/ttyUSB1"


async def test_serial_socket(event_loop):
    protocol_factory = unittest.mock.Mock()

    with unittest.mock.patch.object(
        event_loop,
        "create_connection",
        unittest.mock.AsyncMock(
            return_value=(unittest.mock.AsyncMock(), unittest.mock.AsyncMock())
        ),
    ):
        await zigpy.serial.create_serial_connection(
            event_loop, protocol_factory, "socket://1.2.3.4:5678"
        )
        await zigpy.serial.create_serial_connection(
            event_loop, protocol_factory, "socket://1.2.3.4"
        )

        assert len(event_loop.create_connection.mock_calls) == 2
        assert event_loop.create_connection.mock_calls[0].kwargs["host"] == "1.2.3.4"
        assert event_loop.create_connection.mock_calls[0].kwargs["port"] == 5678
        assert event_loop.create_connection.mock_calls[1].kwargs["host"] == "1.2.3.4"
        assert event_loop.create_connection.mock_calls[1].kwargs["port"] == 6638
