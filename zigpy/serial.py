from __future__ import annotations

import asyncio
import logging
import typing
import urllib.parse

import async_timeout
import serial as pyserial

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
    parity=pyserial.PARITY_NONE,
    stopbits=pyserial.STOPBITS_ONE,
    **kwargs: typing.Any,
) -> tuple[asyncio.Transport, asyncio.Protocol]:
    """Wrapper around pyserial-asyncio that transparently substitutes a normal TCP
    transport and protocol when a `socket` connection URI is provided.
    """
    baudrate: int | None = kwargs.get("baudrate")
    LOGGER.debug("Opening a serial connection to %r (%s baudrate)", url, baudrate)

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
            loop, protocol_factory, url=url, **kwargs
        )

    return transport, protocol
