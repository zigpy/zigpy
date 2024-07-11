from __future__ import annotations

import asyncio
import logging
import typing
import urllib.parse

import async_timeout
import serial as pyserial

from typing import Literal

LOGGER = logging.getLogger(__name__)
DEFAULT_SOCKET_PORT = 6638
SOCKET_CONNECT_TIMEOUT = 5

try:
    import serial_asyncio_fast as pyserial_asyncio

    LOGGER.info("Using pyserial-asyncio-fast in place of pyserial-asyncio")
except ImportError:
    import serial_asyncio as pyserial_asyncio


async def create_serial_connection(
    loop: asyncio.BaseEventLoop,
    protocol_factory: typing.Callable[[], asyncio.Protocol],
    url: str,
    *,
    baudrate: int,
    parity: Literal[
        pyserial.PARITY_NONE,
        pyserial.PARITY_EVEN,
        pyserial.PARITY_ODD,
        pyserial.PARITY_MARK,
        pyserial.PARITY_SPACE,
    ] = pyserial.PARITY_NONE,
    stopbits: Literal[
        pyserial.STOPBITS_ONE,
        pyserial.STOPBITS_ONE_POINT_FIVE,
        pyserial.STOPBITS_TWO,
    ] = pyserial.STOPBITS_ONE,
    exclusive: bool = True,  # We open serial ports exclusively by default
    xonxoff: bool = False,
    rtscts: bool = False,
    **kwargs: typing.Any,
) -> tuple[asyncio.Transport, asyncio.Protocol]:
    """Wrapper around pyserial-asyncio that transparently substitutes a normal TCP
    transport and protocol when a `socket` connection URI is provided.
    """
    LOGGER.debug(
        "Opening a serial connection to %r (baudrate=%s, xonxoff=%s, rtscts=%s)",
        url,
        baudrate,
        xonxoff,
        rtscts,
    )

    parsed_url = urllib.parse.urlparse(url)

    if parsed_url.scheme in ("socket", "tcp"):
        async with async_timeout.timeout(SOCKET_CONNECT_TIMEOUT):
            transport, protocol = await loop.create_connection(
                protocol_factory=protocol_factory,
                host=parsed_url.hostname,
                port=parsed_url.port or DEFAULT_SOCKET_PORT,
            )
    else:
        transport, protocol = await pyserial_asyncio.create_serial_connection(
            loop,
            protocol_factory,
            url=url,
            exclusive=exclusive,
            xonxoff=xonxoff,
            rtscts=rtscts,
            **kwargs,
        )

    return transport, protocol
