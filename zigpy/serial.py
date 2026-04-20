from __future__ import annotations

import asyncio
from collections.abc import Callable
import errno
import logging
import pathlib
from typing import Any, Literal, cast

from serialx import (
    SerialTransport,
    create_serial_connection as serialx_create_serial_connection,
)

from zigpy.typing import UNDEFINED, UndefinedType

LOGGER = logging.getLogger(__name__)


class SerialProtocol(asyncio.Protocol):
    """Base class for packet-parsing serial protocol implementations."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._transport: SerialTransport | None = None

        self._connected_event = asyncio.Event()
        self._disconnected_event = asyncio.Event()
        self._disconnected_event.set()

    async def wait_until_connected(self) -> None:
        """Wait for the protocol's transport to be connected."""
        await self._connected_event.wait()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        LOGGER.debug("Connection made: %s", transport)

        self._transport = cast(SerialTransport, transport)
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
    loop: asyncio.AbstractEventLoop,
    protocol_factory: Callable[[], asyncio.Protocol],
    url: pathlib.Path | str,
    *,
    baudrate: int = 115200,  # We default to 115200 instead of 9600
    xonxoff: bool | UndefinedType = UNDEFINED,
    rtscts: bool | UndefinedType = UNDEFINED,
    flow_control: Literal["hardware", "software"] | None | UndefinedType = UNDEFINED,
    **kwargs: Any,
) -> tuple[asyncio.Transport, asyncio.Protocol]:
    """Wrapper for serialx that provides simplified flow control kwargs."""

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

    try:
        transport, protocol = await serialx_create_serial_connection(
            loop,
            protocol_factory,
            url=url,
            baudrate=baudrate,
            xonxoff=xonxoff,
            rtscts=rtscts,
            **kwargs,
        )
    except OSError as exc:
        if exc.errno == errno.EBUSY:
            # Re-raise a more useful exception
            raise PermissionError(
                "The serial port is locked by another application"
            ) from exc

        raise

    return transport, protocol
