"""Frames received by the application, and listeners for them keyed by source NWK.

Frames are parsed without a device object, so only ZDO and general ZCL commands are
decoded. Cluster-specific ZCL commands need the device's clusters and are matched by the
device-level listeners in `zigpy.listeners`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Iterator
import contextlib
import dataclasses
import logging
import typing

from zigpy.profiles import zha, zll
import zigpy.types as t
from zigpy.zcl import foundation
import zigpy.zdo
import zigpy.zdo.commands as zdo_c

LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class RawFrame:
    """A packet that is neither ZDO nor ZCL, or that failed to parse."""

    packet: t.ZigbeePacket


@dataclasses.dataclass(frozen=True)
class ZDOFrame:
    packet: t.ZigbeePacket
    command: zdo_c.ZDOCommand


@dataclasses.dataclass(frozen=True)
class ZCLFrame:
    packet: t.ZigbeePacket
    header: foundation.ZCLHeader
    # General commands are parsed, cluster-specific commands are left as raw bytes
    command: foundation.CommandSchema | bytes


Frame = RawFrame | ZDOFrame | ZCLFrame
FramePredicate = Callable[[Frame], bool]
FrameCallback = Callable[[Frame], typing.Any]


def parse_frame(packet: t.ZigbeePacket) -> Frame:
    """Parse a packet as far as is possible without a device object."""
    data = packet.data.serialize()

    if zigpy.zdo.ZDO_ENDPOINT in (packet.src_ep, packet.dst_ep):
        try:
            zdo_command = zdo_c.ZDOCommand.deserialize(packet.cluster_id, data)
        except ValueError:
            LOGGER.debug("Could not parse ZDO frame from packet %r", packet)
            return RawFrame(packet=packet)

        return ZDOFrame(packet=packet, command=zdo_command)

    if packet.profile_id not in (zha.PROFILE_ID, zll.PROFILE_ID):
        return RawFrame(packet=packet)

    try:
        header, data = foundation.ZCLHeader.deserialize(data)
    except ValueError:
        LOGGER.debug("Could not parse ZCL header from packet %r", packet)
        return RawFrame(packet=packet)

    if (
        header.frame_control.frame_type != foundation.FrameType.GLOBAL_COMMAND
        or header.command_id not in foundation.GENERAL_COMMANDS
    ):
        return ZCLFrame(packet=packet, header=header, command=data)

    schema = foundation.GENERAL_COMMANDS[
        foundation.GeneralCommand(header.command_id)
    ].schema

    try:
        command, _ = schema.deserialize(data)
    except ValueError:
        LOGGER.debug("Could not parse general ZCL command from packet %r", packet)
        return ZCLFrame(packet=packet, header=header, command=data)

    return ZCLFrame(packet=packet, header=header, command=command)


@dataclasses.dataclass(frozen=True)
class _Listener:
    predicate: FramePredicate


@dataclasses.dataclass(frozen=True)
class _CallbackListener(_Listener):
    callback: FrameCallback


@dataclasses.dataclass(frozen=True)
class _FutureListener(_Listener):
    future: asyncio.Future[Frame]


class FrameListeners:
    """Listeners for received frames, keyed by source NWK.

    A frame is offered to the listeners of its source NWK first, then to the listeners
    of any source. Every matching callback is called. The first matching future
    consumes the frame: later listeners do not see it, and neither does the device.
    """

    def __init__(
        self,
        create_task: Callable[[Coroutine[typing.Any, typing.Any, None], str], object],
    ) -> None:
        self._create_task = create_task
        self._listeners: dict[t.NWK | None, list[_Listener]] = {}

    def _add(self, nwk: t.NWK | None, listener: _Listener) -> Callable[[], None]:
        self._listeners.setdefault(nwk, []).append(listener)

        def remove() -> None:
            listeners = self._listeners[nwk]
            listeners.remove(listener)

            if not listeners:
                del self._listeners[nwk]

        return remove

    def subscribe(
        self, nwk: t.NWK | None, predicate: FramePredicate, callback: FrameCallback
    ) -> Callable[[], None]:
        """Call `callback` with every matching frame from `nwk`, or from any source if
        `nwk` is `None`. Returns a function that unsubscribes.
        """
        return self._add(nwk, _CallbackListener(predicate=predicate, callback=callback))

    @contextlib.contextmanager
    def wait_for(
        self, nwk: t.NWK | None, predicate: FramePredicate
    ) -> Iterator[asyncio.Future[Frame]]:
        """Yield a future for the first matching frame from `nwk`, which it consumes."""
        future: asyncio.Future[Frame] = asyncio.get_running_loop().create_future()
        remove = self._add(nwk, _FutureListener(predicate=predicate, future=future))

        try:
            yield future
        finally:
            remove()

    def dispatch(self, frame: Frame) -> bool:
        """Offer a frame to the listeners. Returns whether a future consumed it."""
        src = frame.packet.src
        assert src is not None

        # Copied, a callback may unsubscribe
        listeners: list[_Listener] = []

        if src.addr_mode == t.AddrMode.NWK and src.address in self._listeners:
            listeners.extend(self._listeners[typing.cast(t.NWK, src.address)])

        if None in self._listeners:
            listeners.extend(self._listeners[None])

        for listener in listeners:
            if not listener.predicate(frame):
                continue

            if isinstance(listener, _FutureListener):
                if listener.future.done():
                    continue

                listener.future.set_result(frame)
                return True

            assert isinstance(listener, _CallbackListener)

            try:
                result = listener.callback(frame)
            except Exception:
                LOGGER.exception("Frame callback %r failed", listener.callback)
                continue

            if asyncio.iscoroutine(result):
                self._create_task(result, f"frame_callback_{listener.callback!r}")

        return False


def zdo_command(
    command_type: type[zdo_c.ZDOPayload], *, tsn: int | None = None
) -> FramePredicate:
    """Match a ZDO frame by payload type and, optionally, TSN."""

    def predicate(frame: Frame) -> bool:
        return (
            isinstance(frame, ZDOFrame)
            and isinstance(frame.command.command, command_type)
            and (tsn is None or frame.command.tsn == tsn)
        )

    return predicate
