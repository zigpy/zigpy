from __future__ import annotations

import asyncio
import typing
import urllib.parse

import async_timeout
import serial as pyserial
import serial_asyncio as pyserial_asyncio

DEFAULT_SOCKET_PORT = 6638
SOCKET_CONNECT_TIMEOUT = 5


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
