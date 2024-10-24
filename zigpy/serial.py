from __future__ import annotations

import asyncio
import logging
import pathlib
import typing
from typing import Literal
import urllib.parse

import async_timeout
import serial as pyserial

from zigpy.typing import UNDEFINED, UndefinedType

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
    url: pathlib.Path | str,
    *,
    baudrate: int = 115200,  # We default to 115200 instead of 9600
    exclusive: bool | None = None,
    xonxoff: bool | UndefinedType = UNDEFINED,
    rtscts: bool | UndefinedType = UNDEFINED,
    flow_control: Literal["hardware", "software", None] | UndefinedType = UNDEFINED,
    **kwargs: typing.Any,
) -> tuple[asyncio.Transport, asyncio.Protocol]:
    """Wrapper around pyserial-asyncio that transparently substitutes a normal TCP
    transport and protocol when a `socket` connection URI is provided.
    """

    if flow_control is not UNDEFINED:
        xonxoff = flow_control == "software"
        rtscts = flow_control == "hardware"

    if xonxoff is UNDEFINED:
        xonxoff = False

    if rtscts is UNDEFINED:
        rtscts = False

    LOGGER.debug(
        "Opening a serial connection to %r (baudrate=%s, xonxoff=%s, rtscts=%s)",
        url,
        baudrate,
        xonxoff,
        rtscts,
    )

    url = str(url)
    parsed_url = urllib.parse.urlparse(url)

    if parsed_url.scheme in ("socket", "tcp"):
        async with async_timeout.timeout(SOCKET_CONNECT_TIMEOUT):
            transport, protocol = await loop.create_connection(
                protocol_factory=protocol_factory,
                host=parsed_url.hostname,
                port=parsed_url.port or DEFAULT_SOCKET_PORT,
            )
    else:
        try:
            transport, protocol = await pyserial_asyncio.create_serial_connection(
                loop,
                protocol_factory,
                url=url,
                baudrate=baudrate,
                exclusive=exclusive,
                xonxoff=xonxoff,
                rtscts=rtscts,
                **kwargs,
            )
        except pyserial.SerialException as exc:
            # Unwrap unnecessarily wrapped PySerial exceptions
            if exc.__context__ is not None:
                raise exc.__context__ from None

            raise

    return transport, protocol
