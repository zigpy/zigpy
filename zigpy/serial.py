from __future__ import annotations

import asyncio
import logging
import pathlib
import sys
import typing
from typing import Literal
import urllib.parse

if sys.version_info[:2] < (3, 11):
    from async_timeout import timeout as asyncio_timeout  # pragma: no cover
else:
    from asyncio import timeout as asyncio_timeout  # pragma: no cover

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


class SerialProtocol(asyncio.Protocol):
    """Base class for packet-parsing serial protocol implementations."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._transport: pyserial_asyncio.SerialTransport | None = None

        self._connected_event = asyncio.Event()
        self._disconnected_event = asyncio.Event()
        self._disconnected_event.set()

    async def wait_until_connected(self) -> None:
        """Wait for the protocol's transport to be connected."""
        await self._connected_event.wait()

    def connection_made(self, transport: pyserial_asyncio.SerialTransport) -> None:
        LOGGER.debug("Connection made: %s", transport)

        self._transport = transport
        self._disconnected_event.clear()
        self._connected_event.set()

    def connection_lost(self, exc: BaseException | None) -> None:
        LOGGER.debug("Connection lost: %r", exc)
        self._connected_event.clear()
        self._disconnected_event.set()
        self._transport = None

    def data_received(self, data: bytes) -> None:
        self._buffer += data

    def close(self) -> None:
        self._buffer.clear()

        if self._transport is not None:
            self._transport.close()

    async def wait_until_closed(self) -> None:
        LOGGER.debug("Waiting for serial port to close")
        await self._disconnected_event.wait()

    async def disconnect(self) -> None:
        self.close()
        await self.wait_until_closed()


async def create_serial_connection(
    loop: asyncio.BaseEventLoop,
    protocol_factory: typing.Callable[[], asyncio.Protocol],
    url: pathlib.Path | str,
    *,
    baudrate: int = 115200,  # We default to 115200 instead of 9600
    exclusive: bool | None = True,
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
        async with asyncio_timeout(SOCKET_CONNECT_TIMEOUT):
            transport, protocol = await loop.create_connection(
                protocol_factory=protocol_factory,
                host=parsed_url.hostname,
                port=parsed_url.port or DEFAULT_SOCKET_PORT,
            )
    else:
        try:
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
        except BlockingIOError as exc:
            # Re-raise a more useful exception
            raise PermissionError(
                "The serial port is locked by another application"
            ) from exc

    return transport, protocol
