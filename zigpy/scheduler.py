"""Outgoing frame scheduler: explicit queueing, parking, and coalescing of sends."""

from __future__ import annotations

import asyncio
import collections
import dataclasses
import enum
import heapq
import itertools
import logging
import typing

import zigpy.datastructures
from zigpy.exceptions import (
    DeliveryError,
    FailureScope,
    PermanentSendError,
    RadioBusyError,
    SendCancelledError,
    SupersededError,
    TransactionExpiredError,
    TransientSendError,
)
import zigpy.types as t

LOGGER = logging.getLogger(__name__)

# Rough per-frame overhead on top of the ASDU: MAC, NWK, NWK security, and APS headers
FRAME_OVERHEAD = 44

# A frame to a sleepy destination occupies radio buffers for far longer (parent-side
# indirect buffering), so it weighs heavier against the byte budget
SLEEPY_SIZE_WEIGHT = 4

DEFAULT_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_GLOBAL_BACKOFF = 0.5
DEFAULT_DESTINATION_BACKOFF = 1.0
DEFAULT_REPLY_TIMEOUT = 10.0

# Queue status is logged at most this often, and only when the scheduler is busy
STATUS_LOG_INTERVAL = 30.0

# The destination address fields that identify a rate-limiting domain. NWK and IEEE
# addressing of the same device intentionally do not unify: IEEE-addressed sends form
# their own domain, as a known limitation.
DestKey: typing.TypeAlias = tuple[t.AddrMode, typing.Any]

_UNSET = object()


# The broadcast domain: a single scheduling lane for every broadcast and groupcast.
# Each Zigbee stack keeps every broadcast in a delivery table for ~9s to suppress
# relay loops, a hard firmware-wide limit shared by all broadcast traffic, so the
# whole class is paced and blocked together.
BROADCAST_DEST_KEY: DestKey = (t.AddrMode.Broadcast, None)


def packet_dest_key(packet: t.ZigbeePacket) -> DestKey:
    assert packet.dst is not None

    if packet.dst.addr_mode in (t.AddrMode.Broadcast, t.AddrMode.Group):
        return BROADCAST_DEST_KEY

    return (packet.dst.addr_mode, packet.dst.address)


def format_dest_key(key: DestKey) -> str:
    if key == BROADCAST_DEST_KEY:
        return "Broadcast"

    return f"{key[0].name}:{key[1]!r}"


def packet_size(packet: t.ZigbeePacket) -> int:
    size = FRAME_OVERHEAD + len(packet.data.serialize())

    if packet.extended_timeout:
        size *= SLEEPY_SIZE_WEIGHT

    return size


class SendStage(enum.IntEnum):
    """A send's observable stages, in resolution order."""

    # The radio accepted the frame
    SENT = 1
    # The delivery verdict: TX status, APS ack, or broadcast handoff
    CONFIRMED = 2
    # A matching ZDO/ZCL response was received (only for sends expecting a reply)
    REPLIED = 3


class SendState(enum.Enum):
    QUEUED = "queued"
    PARKED = "parked"
    IN_FLIGHT = "in_flight"
    # Confirmed by the radio, waiting for the matched reply (or its deadline)
    AWAITING_REPLY = "awaiting_reply"
    DONE = "done"


class ParkReason(enum.Enum):
    # A delivery failure with attempts remaining, waiting out the retry delay
    RETRY_BACKOFF = "retry_backoff"
    # The destination is temporarily unable to accept frames or its window is full
    DESTINATION_BLOCKED = "destination_blocked"
    # The sleepy destination did not poll: parked until it is heard from (opt-in)
    AWAITING_WAKE = "awaiting_wake"


class SendSlot:
    """Staged, write-once results of a single send.

    The write rules mirror Ziggurat's `SendSlot`: the first write to a stage wins, a
    successful resolution back-fills every earlier unset stage, and an error resolves
    every unset stage.
    """

    def __init__(self, final_stage: SendStage) -> None:
        self.final_stage = final_stage
        self._results: dict[SendStage, typing.Any] = {
            stage: _UNSET for stage in SendStage if stage <= final_stage
        }
        self._events: dict[SendStage, asyncio.Event] = {
            stage: asyncio.Event() for stage in self._results
        }

    def resolve(self, stage: SendStage, result: typing.Any = None) -> None:
        if isinstance(result, BaseException):
            stages = [s for s in self._results if self._results[s] is _UNSET]
        else:
            stages = [
                s for s in self._results if s <= stage and self._results[s] is _UNSET
            ]

        for s in stages:
            if isinstance(result, BaseException) or s == stage:
                self._results[s] = result
            else:
                self._results[s] = None

            self._events[s].set()

    def is_resolved(self, stage: SendStage) -> bool:
        return self._results[stage] is not _UNSET

    async def wait(self, stage: SendStage) -> typing.Any:
        await self._events[stage].wait()
        result = self._results[stage]

        if isinstance(result, BaseException):
            raise result

        return result


@dataclasses.dataclass(eq=False)
class QueuedSend:
    """A reified outgoing frame, owned by the scheduler from submission to resolution."""

    packet: t.ZigbeePacket
    slot: SendSlot
    seq: int
    dest_key: DestKey
    coalesce_key: typing.Hashable
    priority: int
    size: int
    attempts_remaining: int
    expires_at: float | None
    retry_delay: float
    reply_timeout: float
    submitted_at: float = 0.0
    # Park until the destination is heard from when it does not poll, instead of
    # consuming a retry attempt (opt-in: only safe for callers that bound the wait)
    park_on_wake: bool = False
    state: SendState = SendState.QUEUED
    park_reason: ParkReason | None = None
    not_before: float = 0.0
    # Holding a slot in the destination's interaction window (from dispatch until the
    # send is terminal or parked, including the reply wait)
    holds_dest_slot: bool = False
    # The current attempt's task, for best-effort in-flight cancellation
    attempt_task: asyncio.Task | None = None


class SendHandle:
    """An awaitable, staged view over one submitted send.

    Awaiting the handle awaits its terminal stage. A superseded handle keeps its own
    (already resolved) slot; the entry lives on under the replacement's slot.
    """

    def __init__(
        self, scheduler: SendScheduler, entry: QueuedSend, slot: SendSlot
    ) -> None:
        self._scheduler = scheduler
        self._entry = entry
        self._slot = slot

    async def sent(self) -> None:
        await self._slot.wait(SendStage.SENT)

    async def confirmed(self) -> None:
        await self._slot.wait(SendStage.CONFIRMED)

    async def replied(self) -> typing.Any:
        return await self._slot.wait(SendStage.REPLIED)

    def __await__(self) -> typing.Generator[typing.Any, None, typing.Any]:
        return self._slot.wait(self._slot.final_stage).__await__()

    def resolve_reply(self, result: typing.Any) -> bool:
        """Resolve the reply stage, called by the response-matching layer."""
        return self._scheduler.resolve_reply(self._entry, self._slot, result)

    @property
    def state(self) -> SendState:
        if self._slot is not self._entry.slot:
            return SendState.DONE

        return self._entry.state

    @property
    def park_reason(self) -> ParkReason | None:
        if self._slot is not self._entry.slot:
            return None

        return self._entry.park_reason

    def cancel(self) -> bool:
        """Cancel the send. Guaranteed for a queued or parked send, no-op otherwise."""
        return self._scheduler.cancel(self._entry, self._slot)


@dataclasses.dataclass
class DestinationState:
    """Ephemeral per-destination scheduling state, evicted as soon as it is idle."""

    # Open interactions: dispatched sends up to and including their reply wait
    in_flight: int = 0
    blocked_until: float = 0.0
    deferred: list[QueuedSend] = dataclasses.field(default_factory=list)

    def is_idle(self, now: float) -> bool:
        return not self.in_flight and not self.deferred and now >= self.blocked_until


class SendScheduler:
    """Owns every outgoing frame between submission and the radio.

    Dispatches queued sends to `send_packet` in priority order, paced by an adaptive
    in-flight window (frames and weighted bytes). Transient radio backpressure parks
    frames instead of failing them and never consumes a retry attempt. Queued and
    parked sends sharing a coalesce key supersede one another.
    """

    def __init__(
        self,
        send_packet: typing.Callable[[t.ZigbeePacket], typing.Awaitable[None]],
        *,
        max_in_flight: int = 8,
        max_in_flight_bytes: int | None = None,
        destination_window: int | None = None,
        retry_delay: float = DEFAULT_RETRY_DELAY,
    ) -> None:
        self._send_packet = send_packet
        self._max_in_flight = max_in_flight
        self._max_in_flight_bytes = max_in_flight_bytes
        self._destination_window = destination_window
        self._retry_delay = retry_delay

        self._seq = itertools.count()
        self._ready: list[tuple[int, int, QueuedSend]] = []
        self._parked: list[tuple[float, int, QueuedSend]] = []
        self._awaiting_reply: list[tuple[float, int, QueuedSend]] = []
        self._destinations: dict[DestKey, DestinationState] = {}
        self._coalesce: dict[typing.Hashable, QueuedSend] = {}
        self._in_flight: set[QueuedSend] = set()
        self._in_flight_by_packet: dict[int, QueuedSend] = {}
        self._attempt_tasks: set[asyncio.Task] = set()

        # AIMD window: clamped on transient backpressure, grown on success
        self._window = max_in_flight
        self._bytes_in_flight = 0
        self._blocked_until = 0.0
        self._unblock_on_completion = False

        self._wake = asyncio.Event()
        self._timer = zigpy.datastructures.ReschedulableTimeout(self._wake.set)
        self._task: asyncio.Task | None = None
        self._last_status_log = 0.0

    def __repr__(self) -> str:
        # The heaps hold onto stale entries until they are lazily popped, so the
        # live states are counted instead, deduplicated by identity
        entries = set(self._all_entries())
        states = collections.Counter(e.state for e in entries)
        reasons = collections.Counter(
            e.park_reason for e in entries if e.state is SendState.PARKED
        )

        return (
            f"<{type(self).__name__}"
            f" queued={states[SendState.QUEUED]}"
            f" in_flight={len(self._in_flight)}"
            f" awaiting_reply={states[SendState.AWAITING_REPLY]}"
            f" retry_backoff={reasons[ParkReason.RETRY_BACKOFF]}"
            f" destination_blocked={reasons[ParkReason.DESTINATION_BLOCKED]}"
            f" awaiting_wake={reasons[ParkReason.AWAITING_WAKE]}"
            f" window={self._window}/{self._max_in_flight}"
            f" bytes_in_flight={self._bytes_in_flight}"
            f" destinations={len(self._destinations)}"
            f">"
        )

    @property
    def max_in_flight(self) -> int:
        return self._max_in_flight

    @max_in_flight.setter
    def max_in_flight(self, value: int) -> None:
        """Update the in-flight ceiling, resetting the adaptive window."""
        self._max_in_flight = value
        self._window = value
        self._wake.set()

    @property
    def destination_window(self) -> int | None:
        return self._destination_window

    @destination_window.setter
    def destination_window(self, value: int | None) -> None:
        """Update the per-destination interaction window."""
        self._destination_window = value
        self._wake.set()

    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._dispatch_loop())

    def stop(self) -> None:
        """Stop dispatching and fail every unresolved send."""
        LOGGER.debug("Stopping scheduler: %r", self)
        if self._task is not None:
            self._task.cancel()
            self._task = None

        for task in self._attempt_tasks:
            task.cancel()

        self._timer.cancel()

        for entry in list(self._all_entries()):
            if entry.state is not SendState.DONE:
                self._finalize(entry, SendCancelledError("Scheduler was stopped"))

        self._ready.clear()
        self._parked.clear()
        self._awaiting_reply.clear()

        # Cancelled in-flight attempt tasks still run their cleanup, which needs the
        # destination states: only the parked entries are dropped here
        for dest in self._destinations.values():
            dest.deferred.clear()

    def submit(
        self,
        packet: t.ZigbeePacket,
        *,
        expect_reply: bool = False,
        retries: int = DEFAULT_ATTEMPTS - 1,
        retry_delay: float | None = None,
        reply_timeout: float | None = None,
        expires_at: float | None = None,
        park_on_wake: bool = False,
    ) -> SendHandle:
        """Admit a packet for sending and return a staged handle over it.

        If the packet carries a `coalesce_key` matching a queued or parked send, that
        send is superseded in place: it keeps its queue position, its payload and
        handle are replaced, and the old handle resolves with `SupersededError`.
        """
        if self._task is None:
            self.start()

        key = packet.coalesce_key
        final_stage = SendStage.REPLIED if expect_reply else SendStage.CONFIRMED

        if retry_delay is None:
            retry_delay = self._retry_delay

        if reply_timeout is None:
            reply_timeout = DEFAULT_REPLY_TIMEOUT

        if key is not None and key in self._coalesce:
            entry = self._coalesce[key]
            assert entry.state in (SendState.QUEUED, SendState.PARKED)
            assert entry.dest_key == packet_dest_key(packet)

            old_slot = entry.slot
            entry.packet = packet
            entry.slot = SendSlot(final_stage)
            entry.size = packet_size(packet)
            entry.attempts_remaining = retries + 1
            entry.expires_at = expires_at
            entry.retry_delay = retry_delay
            entry.reply_timeout = reply_timeout
            entry.park_on_wake = park_on_wake
            old_slot.resolve(SendStage.SENT, SupersededError("Send was superseded"))
            LOGGER.debug(
                "Superseded queued send %r to %s",
                key,
                format_dest_key(entry.dest_key),
            )

            return SendHandle(self, entry, entry.slot)

        entry = QueuedSend(
            packet=packet,
            slot=SendSlot(final_stage),
            seq=next(self._seq),
            dest_key=packet_dest_key(packet),
            coalesce_key=key,
            priority=packet.priority if packet.priority is not None else 0,
            size=packet_size(packet),
            attempts_remaining=retries + 1,
            expires_at=expires_at,
            retry_delay=retry_delay,
            reply_timeout=reply_timeout,
            park_on_wake=park_on_wake,
        )

        if key is not None:
            self._coalesce[key] = entry

        # Fast path: dispatch synchronously when nothing is ahead in the queue and
        # every gate is open, avoiding the dispatch loop's added latency
        now = asyncio.get_running_loop().time()
        entry.submitted_at = now

        if entry.expires_at is not None and now >= entry.expires_at:
            self._finalize(entry, SendCancelledError("Send expired before dispatch"))
            return SendHandle(self, entry, entry.slot)

        dest = self._destination(entry.dest_key)

        if (
            not self._ready
            and not dest.deferred
            and self._can_dispatch(now)
            and self._dest_can_dispatch(dest, now)
        ):
            self._dispatch(entry, dest)
        else:
            self._maybe_evict(entry.dest_key, now)
            self._push_ready(entry)
            LOGGER.debug(
                "Queueing send to %s: %r", format_dest_key(entry.dest_key), self
            )

        return SendHandle(self, entry, entry.slot)

    def cancel(self, entry: QueuedSend, slot: SendSlot) -> bool:
        if slot is not entry.slot:
            # The handle was superseded, its own slot is already resolved
            return False

        if entry.state is SendState.DONE:
            return False

        if entry.state is SendState.IN_FLIGHT:
            # Cancelling the attempt triggers the radio's own cleanup (e.g. a
            # wire-level send cancellation); the frame may already be on the air
            assert entry.attempt_task is not None
            entry.attempt_task.cancel()
            return True

        self._finalize(entry, SendCancelledError("Send was cancelled"))
        return True

    def resolve_sent(self, packet: t.ZigbeePacket) -> None:
        """Resolve an in-flight packet's sent stage, called by a staged radio."""
        if id(packet) in self._in_flight_by_packet:
            self._in_flight_by_packet[id(packet)].slot.resolve(SendStage.SENT, None)

    def resolve_reply(
        self, entry: QueuedSend, slot: SendSlot, result: typing.Any
    ) -> bool:
        """Terminally resolve a send with its matched reply (or reply parsing error).

        A late reply is honored even if the entry is already parked for a retry; a
        reply for a superseded or finished send is ignored.
        """
        if slot is not entry.slot or entry.state is SendState.DONE:
            return False

        self._finalize(entry, result, stage=SendStage.REPLIED)
        return True

    def destination_seen(self, dst: t.AddrModeAddress) -> None:
        """Feed a liveness indicator: release sends parked awaiting this destination."""
        key = (dst.addr_mode, dst.address)

        if key not in self._destinations:
            return

        dest = self._destinations[key]
        woken = [e for e in dest.deferred if e.park_reason is ParkReason.AWAITING_WAKE]

        if not woken:
            return

        LOGGER.debug(
            "Destination %s is awake, releasing %d parked sends",
            format_dest_key(key),
            len(woken),
        )
        dest.deferred = [e for e in dest.deferred if e not in woken]

        for entry in woken:
            self._push_ready(entry)

    # -- internal state transitions --------------------------------------------------

    def _push_ready(self, entry: QueuedSend) -> None:
        entry.state = SendState.QUEUED
        entry.park_reason = None
        entry.submitted_at = asyncio.get_running_loop().time()
        heapq.heappush(self._ready, (-entry.priority, entry.seq, entry))
        self._wake.set()

    def _release_dest_slot(self, entry: QueuedSend) -> None:
        if not entry.holds_dest_slot:
            return

        entry.holds_dest_slot = False
        dest = self._destinations[entry.dest_key]
        dest.in_flight -= 1
        self._maybe_evict(entry.dest_key, asyncio.get_running_loop().time())
        # A freed interaction slot may unblock sends deferred on the window
        self._wake.set()

    def _finalize(
        self,
        entry: QueuedSend,
        result: typing.Any = None,
        *,
        stage: SendStage = SendStage.CONFIRMED,
    ) -> None:
        self._release_dest_slot(entry)

        if entry.dest_key in self._destinations:
            dest = self._destinations[entry.dest_key]
            if entry in dest.deferred:
                dest.deferred.remove(entry)

        entry.state = SendState.DONE
        entry.park_reason = None
        entry.slot.resolve(stage, result)

        key = entry.coalesce_key
        if key is not None and key in self._coalesce and self._coalesce[key] is entry:
            del self._coalesce[key]

    def _restore_coalesce(self, entry: QueuedSend) -> bool:
        """Re-register a formerly in-flight entry; a newer same-key send wins instead."""
        if entry.coalesce_key is None:
            return True

        if entry.coalesce_key in self._coalesce:
            self._finalize(entry, SupersededError("Send was superseded during a retry"))
            return False

        self._coalesce[entry.coalesce_key] = entry
        return True

    def _park_retry(self, entry: QueuedSend, now: float) -> None:
        self._release_dest_slot(entry)

        if not self._restore_coalesce(entry):
            return

        entry.state = SendState.PARKED
        entry.park_reason = ParkReason.RETRY_BACKOFF
        entry.not_before = now + entry.retry_delay
        heapq.heappush(self._parked, (entry.not_before, entry.seq, entry))
        self._timer.reschedule(entry.retry_delay)

    def _retry_or_fail(self, entry: QueuedSend, exc: BaseException, now: float) -> None:
        entry.attempts_remaining -= 1

        if entry.attempts_remaining > 0:
            LOGGER.debug(
                "Send to %s failed (%r), retrying in %.1fs (%d attempts left)",
                format_dest_key(entry.dest_key),
                exc,
                entry.retry_delay,
                entry.attempts_remaining,
            )
            # Replaced, not mutated: the already-dispatched packet stays untouched
            entry.packet = entry.packet.replace(
                tx_options=(
                    entry.packet.tx_options | t.TransmitOptions.FORCE_ROUTE_DISCOVERY
                )
            )
            self._park_retry(entry, now)
        else:
            self._finalize(entry, exc)

    def _await_reply(self, entry: QueuedSend, now: float) -> None:
        entry.state = SendState.AWAITING_REPLY
        entry.park_reason = None
        deadline = now + entry.reply_timeout
        heapq.heappush(self._awaiting_reply, (deadline, entry.seq, entry))
        self._timer.reschedule(entry.reply_timeout)

    def _park_deferred(self, entry: QueuedSend, reason: ParkReason) -> None:
        if not self._restore_coalesce(entry):
            return

        entry.state = SendState.PARKED
        entry.park_reason = reason
        self._destination(entry.dest_key).deferred.append(entry)

    def _grow_window(self) -> None:
        # The radio accepted the frame, so the window was not the constraint. A
        # delivery failure says nothing about radio capacity: only a transient
        # enqueue rejection shrinks the window.
        self._window = min(self._window + 1, self._max_in_flight)

    def _destination(self, key: DestKey) -> DestinationState:
        if key not in self._destinations:
            self._destinations[key] = DestinationState()

        return self._destinations[key]

    def _maybe_evict(self, key: DestKey, now: float) -> None:
        if key in self._destinations and self._destinations[key].is_idle(now):
            del self._destinations[key]

    def _all_entries(self) -> typing.Iterator[QueuedSend]:
        for _, _, entry in self._ready:
            yield entry
        for _, _, entry in self._parked:
            yield entry
        for _, _, entry in self._awaiting_reply:
            yield entry
        for dest in self._destinations.values():
            yield from dest.deferred
        yield from self._in_flight

    # -- dispatch ---------------------------------------------------------------------

    async def _dispatch_loop(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()

            now = asyncio.get_running_loop().time()
            self._expire_entries(now)
            self._release_reply_timeouts(now)
            self._release_parked(now)
            self._release_destinations(now)

            while self._ready and self._can_dispatch(now):
                _, _, entry = heapq.heappop(self._ready)

                if entry.state is not SendState.QUEUED:
                    continue

                if entry.expires_at is not None and now >= entry.expires_at:
                    self._finalize(
                        entry, SendCancelledError("Send expired before dispatch")
                    )
                    continue

                dest = self._destination(entry.dest_key)

                if not self._dest_can_dispatch(dest, now):
                    entry.state = SendState.PARKED
                    entry.park_reason = ParkReason.DESTINATION_BLOCKED
                    dest.deferred.append(entry)
                    continue

                LOGGER.debug(
                    "Dispatching queued send to %s after %.2fs",
                    format_dest_key(entry.dest_key),
                    now - entry.submitted_at,
                )
                self._dispatch(entry, dest)

            if now - self._last_status_log > STATUS_LOG_INTERVAL and (
                self._in_flight or set(self._all_entries())
            ):
                self._last_status_log = now
                LOGGER.debug("Send queue status: %r", self)

            self._rearm_timer(now)

    def _dest_can_dispatch(self, dest: DestinationState, now: float) -> bool:
        return now >= dest.blocked_until and (
            self._destination_window is None
            or dest.in_flight < self._destination_window
        )

    def _can_dispatch(self, now: float) -> bool:
        if now < self._blocked_until:
            return False

        if len(self._in_flight) >= self._window:
            return False

        return (
            self._max_in_flight_bytes is None
            or self._bytes_in_flight < self._max_in_flight_bytes
        )

    def _dispatch(self, entry: QueuedSend, dest: DestinationState) -> None:
        entry.state = SendState.IN_FLIGHT
        entry.park_reason = None

        # An in-flight send can no longer be superseded
        key = entry.coalesce_key
        if key is not None and key in self._coalesce and self._coalesce[key] is entry:
            del self._coalesce[key]

        dest.in_flight += 1
        entry.holds_dest_slot = True
        self._in_flight.add(entry)
        self._in_flight_by_packet[id(entry.packet)] = entry
        self._bytes_in_flight += entry.size

        task = asyncio.get_running_loop().create_task(self._attempt(entry))
        entry.attempt_task = task
        self._attempt_tasks.add(task)
        task.add_done_callback(self._attempt_tasks.remove)

    async def _attempt(self, entry: QueuedSend) -> None:
        loop = asyncio.get_running_loop()
        transient = False
        # A retry replaces `entry.packet` before this attempt's cleanup runs
        packet = entry.packet

        try:
            await self._send_packet(packet)
        except asyncio.CancelledError:
            self._finalize(entry, SendCancelledError("Send was cancelled"))
            raise
        except TransientSendError as exc:
            # The frame never left the radio: no attempt is consumed
            transient = True
            now = loop.time()

            if entry.state is SendState.DONE:
                # Resolved while in flight (late reply or cancellation)
                pass
            elif (
                exc.scope is FailureScope.DESTINATION
                or entry.dest_key == BROADCAST_DEST_KEY
            ):
                # Backpressure limited to this entry's lane: a destination's own
                # congestion, or the firmware-wide broadcast budget. Rejections here
                # say nothing about unicast radio capacity, so the window is left
                # alone. Broadcast-domain rejections block the whole class even when
                # the radio can only report a generic global status.
                dest = self._destination(entry.dest_key)
                dest.blocked_until = now + (
                    exc.retry_in
                    if exc.retry_in is not None
                    else DEFAULT_DESTINATION_BACKOFF
                )
                LOGGER.debug(
                    "Backpressure on %s (%r), blocked for %.2fs: %r",
                    format_dest_key(entry.dest_key),
                    exc,
                    dest.blocked_until - now,
                    self,
                )
                self._park_deferred(entry, ParkReason.DESTINATION_BLOCKED)
                self._timer.reschedule(dest.blocked_until - now)
            else:
                self._window = max(1, len(self._in_flight) - 1)
                self._blocked_until = now + (
                    exc.retry_in if exc.retry_in is not None else DEFAULT_GLOBAL_BACKOFF
                )
                # Slot/buffer exhaustion also clears as soon as an in-flight frame
                # completes; channel congestion only clears on the timer
                self._unblock_on_completion = isinstance(exc, RadioBusyError)
                LOGGER.debug(
                    "Radio backpressure (%r), window clamped to %d: %r",
                    exc,
                    self._window,
                    self,
                )
                if self._restore_coalesce(entry):
                    self._push_ready(entry)

                self._timer.reschedule(self._blocked_until - now)
        except (PermanentSendError, SendCancelledError) as exc:
            # Retrying cannot help: fail immediately
            self._grow_window()
            self._finalize(entry, exc)
        except TransactionExpiredError as exc:
            self._grow_window()

            if entry.state is SendState.DONE:
                pass
            elif entry.park_on_wake:
                # The sleepy destination did not poll: park until it is heard from
                LOGGER.debug(
                    "Destination %s did not poll, parking send until it wakes",
                    format_dest_key(entry.dest_key),
                )
                self._park_deferred(entry, ParkReason.AWAITING_WAKE)
            else:
                self._retry_or_fail(entry, exc, loop.time())
        except (DeliveryError, TimeoutError) as exc:
            self._grow_window()

            if entry.state is not SendState.DONE:
                self._retry_or_fail(entry, exc, loop.time())
        except Exception as exc:  # noqa: BLE001
            # Anything else is a terminal verdict for this send
            self._grow_window()
            self._finalize(entry, exc)
        else:
            self._grow_window()

            if entry.state is SendState.DONE:
                # Resolved while in flight (late reply or cancellation)
                pass
            elif entry.slot.final_stage is SendStage.REPLIED:
                entry.slot.resolve(SendStage.CONFIRMED, None)
                self._await_reply(entry, loop.time())
            else:
                self._finalize(entry)
        finally:
            self._in_flight.discard(entry)

            if (
                id(packet) in self._in_flight_by_packet
                and self._in_flight_by_packet[id(packet)] is entry
            ):
                del self._in_flight_by_packet[id(packet)]

            entry.attempt_task = None
            self._bytes_in_flight -= entry.size

            # An interaction awaiting its reply keeps its destination slot
            if entry.state is not SendState.AWAITING_REPLY:
                self._release_dest_slot(entry)

            # A completed frame frees a radio slot: lift a slot-exhaustion block
            # early instead of waiting out its backoff
            if not transient and self._unblock_on_completion:
                self._unblock_on_completion = False
                self._blocked_until = 0.0

            self._wake.set()

    def _expire_entries(self, now: float) -> None:
        for entry in set(self._all_entries()):
            if (
                entry.expires_at is not None
                and now >= entry.expires_at
                and entry.state in (SendState.QUEUED, SendState.PARKED)
            ):
                self._finalize(entry, SendCancelledError("Send expired"))

    def _release_reply_timeouts(self, now: float) -> None:
        while self._awaiting_reply and self._awaiting_reply[0][0] <= now:
            _, _, entry = heapq.heappop(self._awaiting_reply)

            if entry.state is SendState.AWAITING_REPLY:
                self._retry_or_fail(entry, TimeoutError("No response received"), now)

    def _release_parked(self, now: float) -> None:
        while self._parked and self._parked[0][0] <= now:
            _, _, entry = heapq.heappop(self._parked)

            if (
                entry.state is SendState.PARKED
                and entry.park_reason is ParkReason.RETRY_BACKOFF
            ):
                self._push_ready(entry)

    def _release_destinations(self, now: float) -> None:
        for key in list(self._destinations):
            dest = self._destinations[key]

            if not self._dest_can_dispatch(dest, now):
                continue

            released = [
                e
                for e in dest.deferred
                if e.park_reason is ParkReason.DESTINATION_BLOCKED
            ]
            dest.deferred = [e for e in dest.deferred if e not in released]

            for entry in released:
                self._push_ready(entry)

            self._maybe_evict(key, now)

    def _rearm_timer(self, now: float) -> None:
        deadlines = []

        if self._parked:
            deadlines.append(self._parked[0][0])

        if self._awaiting_reply:
            deadlines.append(self._awaiting_reply[0][0])

        if self._ready and now < self._blocked_until:
            deadlines.append(self._blocked_until)

        for dest in self._destinations.values():
            if dest.deferred and now < dest.blocked_until:
                deadlines.append(dest.blocked_until)  # noqa: PERF401

        for entry in set(self._all_entries()):
            if entry.expires_at is not None and entry.state in (
                SendState.QUEUED,
                SendState.PARKED,
            ):
                deadlines.append(entry.expires_at)  # noqa: PERF401

        if deadlines:
            self._timer.reschedule(max(0.0, min(deadlines) - now))
