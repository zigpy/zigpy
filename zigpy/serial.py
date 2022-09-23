from __future__ import annotations

import asyncio
import typing

import serial as pyserial
import serial_asyncio as pyserial_asyncio
import yarl

DEFAULT_SOCKET_PORT = 6638


async def create_serial_connection(
    loop: asyncio.BaseEventLoop,
    protocol_factory: typing.Callable[[], asyncio.Protocol],
    url: str,
    *,
    parity=pyserial.PARITY_NONE,
    stopbits=pyserial.STOPBITS_ONE,
    **kwargs: typing.Any,
) -> tuple[asyncio.Transport, asyncio.Protocol]:
    """
    Wrapper around pyserial-asyncio that transparently substitutes a normal TCP
    transport and protocol when a `socket` connection URI is provided.
    """
    parsed_url = yarl.URL(url)

    if parsed_url.scheme in ("socket", "tcp"):
        # It's convention at this point to use port 6638
        if parsed_url.port is None:
            parsed_url = parsed_url.with_port(DEFAULT_SOCKET_PORT)

        transport, protocol = await loop.create_connection(
            protocol_factory, parsed_url.host, parsed_url.port
        )
    else:
        transport, protocol = await pyserial_asyncio.create_serial_connection(
            loop, protocol_factory, url=url, **kwargs
        )

    return transport, protocol
