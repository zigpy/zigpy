"""Listeners for frames received by zigpy, keyed on the sending device's IEEE address."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Iterator
import contextlib
import dataclasses
import enum
import inspect
import logging
import typing
from typing import Any, Generic, TypeVar

import zigpy.types as t
from zigpy.zcl import foundation
import zigpy.zdo.types as zdo_t

if typing.TYPE_CHECKING:
    from zigpy.device import BaseDevice, GreenPowerDevice, ZigbeeDevice

LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Frame:
    """A received frame."""

    @property
    def ieee(self) -> t.EUI64 | None:
        """The IEEE address of the sending device, None if it is not yet known."""
        raise NotImplementedError  # pragma: no cover


@dataclasses.dataclass(frozen=True, kw_only=True)
class RawFrame(Frame):
    """A Zigbee packet, before its sending device is resolved."""

    packet: t.ZigbeePacket

    @property
    def ieee(self) -> None:
        return None


@dataclasses.dataclass(frozen=True, kw_only=True)
class DeviceFrame(Frame):
    """A frame processed by the device object that received it."""

    device: BaseDevice

    @property
    def ieee(self) -> t.EUI64:
        return self.device.ieee


@dataclasses.dataclass(frozen=True, kw_only=True)
class ZCLFrame(DeviceFrame):
    device: ZigbeeDevice
    packet: t.ZigbeePacket
    header: foundation.ZCLHeader
    command: foundation.CommandSchema


@dataclasses.dataclass(frozen=True, kw_only=True)
class ZDOFrame(DeviceFrame):
    device: ZigbeeDevice
    packet: t.ZigbeePacket
    header: zdo_t.ZDOHeader
    command: list[Any]


@dataclasses.dataclass(frozen=True, kw_only=True)
class GPFrame(DeviceFrame):
    device: GreenPowerDevice
    # Security processed, so the command ID is no longer ciphertext
    packet: t.ZigbeeGpPacket
    command: t.Struct | None


F = TypeVar("F", bound=Frame)


@dataclasses.dataclass(frozen=True)
class Matcher(Generic[F]):
    """Matches frames of one type, optionally only those passing a predicate."""

    frame_type: type[F]
    predicate: Callable[[F], bool] | None = None


def zcl_command(command: foundation.ZCLCommandDef) -> Matcher[ZCLFrame]:
    """Match ZCL frames carrying a command."""
    return Matcher(ZCLFrame, lambda frame: isinstance(frame.command, command.schema))


def gp_command(command_id: t.uint8_t) -> Matcher[GPFrame]:
    """Match GP frames carrying a GPD command."""
    return Matcher(GPFrame, lambda frame: frame.packet.command_id == command_id)


@dataclasses.dataclass(frozen=True)
class FutureListener(Generic[F]):
    match: Callable[[F], bool] | None
    future: asyncio.Future

    def result(self, frame: F) -> Any:
        return frame


@dataclasses.dataclass(frozen=True)
class CallbackListener(Generic[F]):
    match: Callable[[F], bool] | None
    callback: Callable[[F], Any]


Listener = FutureListener | CallbackListener


class FrameListeners:
    """Dispatches received frames to the listeners registered for them."""

    def __init__(
        self, create_task: Callable[[Coroutine[Any, Any, Any], str], asyncio.Task]
    ) -> None:
        self._create_task = create_task
        self._listeners: dict[tuple[type[Frame], t.EUI64 | None], list[Listener]] = {}

    def _add(
        self, frame_type: type[Frame], ieee: t.EUI64 | None, listener: Listener
    ) -> Callable[[], None]:
        key = (frame_type, ieee)
        self._listeners.setdefault(key, []).append(listener)

        def remove() -> None:
            listeners = self._listeners[key]
            listeners.remove(listener)

            if not listeners:
                del self._listeners[key]

        return remove

    def subscribe(
        self,
        match: Matcher[F] | type[F],
        callback: Callable[[F], Any],
        *,
        ieee: t.EUI64 | None = None,
    ) -> Callable[[], None]:
        """Call `callback` with every matching frame, from one device or from any.

        A coroutine returned by the callback runs as a task. Exceptions are logged.
        """
        if not isinstance(match, Matcher):
            match = Matcher(match)

        return self._add(
            match.frame_type,
            ieee,
            CallbackListener(match=match.predicate, callback=callback),
        )

    @contextlib.contextmanager
    def wait_for(
        self,
        match: Matcher[F] | type[F],
        *,
        ieee: t.EUI64 | None = None,
    ) -> Iterator[asyncio.Future[F]]:
        """Resolve a future with the next matching frame, which it consumes."""
        if not isinstance(match, Matcher):
            match = Matcher(match)

        listener = FutureListener(
            match=match.predicate, future=asyncio.get_running_loop().create_future()
        )
        remove = self._add(match.frame_type, ieee, listener)

        try:
            yield listener.future
        finally:
            remove()

    def dispatch(self, frame: Frame) -> None:
        """Pass a frame to its listeners, until a future listener consumes it."""
        keys = [(type(frame), None)]

        if frame.ieee is not None:
            keys.append((type(frame), frame.ieee))

        for key in keys:
            if key not in self._listeners:
                continue

            # Callbacks can add and remove listeners
            for listener in list(self._listeners[key]):
                if listener.match is not None and not listener.match(frame):
                    continue

                if isinstance(listener, CallbackListener):
                    self._run_callback(listener.callback, frame)
                elif not listener.future.done():
                    listener.future.set_result(listener.result(frame))
                    return

    def _run_callback(self, callback: Callable[[Frame], Any], frame: Frame) -> None:
        try:
            result = callback(frame)
        except Exception:  # noqa: BLE001
            LOGGER.warning("Frame callback %r failed", callback, exc_info=True)
            return

        if inspect.isawaitable(result):
            self._create_task(
                self._await_callback(callback, result), f"frame_callback-{callback!r}"
            )

    async def _await_callback(
        self, callback: Callable[[Frame], Any], awaitable: typing.Awaitable[Any]
    ) -> None:
        try:
            await awaitable
        except Exception:  # noqa: BLE001
            LOGGER.warning("Frame callback %r failed", callback, exc_info=True)


# Deprecated `ControllerApplication.wait_for_response` and friends, on ZCL and ZDO frames


class AnyDeviceType(enum.Enum):
    """Singleton type for "any device"."""

    _singleton = 0


ANY_DEVICE = AnyDeviceType._singleton  # noqa: SLF001

LegacyMatcherType = foundation.CommandSchema | Callable[[Any, Any], bool]


@dataclasses.dataclass(frozen=True)
class _LegacyFutureListener(FutureListener[ZCLFrame | ZDOFrame]):
    def result(self, frame: ZCLFrame | ZDOFrame) -> Any:
        return frame.header, frame.command


def _legacy_match(
    filters: list[LegacyMatcherType],
) -> Callable[[ZCLFrame | ZDOFrame], bool]:
    def match(frame: ZCLFrame | ZDOFrame) -> bool:
        for matcher in filters:
            # A command schema matches its command, whatever the field values
            if isinstance(matcher, foundation.CommandSchema):
                if isinstance(frame.command, type(matcher)):
                    return True
            elif matcher(frame.header, frame.command):
                return True

        return False

    return match


def _legacy_add(
    listeners: FrameListeners,
    src: BaseDevice | AnyDeviceType,
    listener: Listener,
) -> Callable[[], None]:
    ieee = None if src is ANY_DEVICE else src.ieee
    removers = [
        listeners._add(frame_type, ieee, listener)  # noqa: SLF001
        for frame_type in (ZCLFrame, ZDOFrame)
    ]

    def remove() -> None:
        for remover in removers:
            remover()

    return remove


def legacy_subscribe(
    listeners: FrameListeners,
    src: BaseDevice | AnyDeviceType,
    filters: list[LegacyMatcherType],
    callback: Callable[[Any, Any], Any],
) -> Callable[[], None]:
    return _legacy_add(
        listeners,
        src,
        CallbackListener(
            match=_legacy_match(filters),
            callback=lambda frame: callback(frame.header, frame.command),
        ),
    )


@contextlib.contextmanager
def legacy_wait_for(
    listeners: FrameListeners,
    src: BaseDevice | AnyDeviceType,
    filters: list[LegacyMatcherType],
) -> Iterator[asyncio.Future]:
    listener = _LegacyFutureListener(
        match=_legacy_match(filters),
        future=asyncio.get_running_loop().create_future(),
    )
    remove = _legacy_add(listeners, src, listener)

    try:
        yield listener.future
    finally:
        remove()
