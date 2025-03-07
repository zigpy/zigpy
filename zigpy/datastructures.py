"""Primitive data structures."""

from __future__ import annotations

import asyncio
import bisect
from collections import OrderedDict
from collections.abc import MutableMapping
import contextlib
import functools
import logging
import types
import typing

_LOGGER = logging.getLogger(__name__)


class WrappedContextManager:
    def __init__(
        self,
        context_manager: contextlib.AbstractAsyncContextManager,
        on_enter: typing.Callable[[], typing.Awaitable[None]],
    ) -> None:
        self.on_enter = on_enter
        self.context_manager = context_manager

    async def __aenter__(self) -> None:
        await self.on_enter()
        return self.context_manager

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        await self.context_manager.__aexit__(exc_type, exc, traceback)


class PriorityDynamicBoundedSemaphore:
    """`asyncio.BoundedSemaphore` with public interface to change the max value."""

    def __init__(self, value: int = 0) -> None:
        self._value: int = value
        self._max_value: int = value
        self._comparison_counter: int = 0
        self._waiters: list[tuple[int, int, asyncio.Future]] = []
        self._loop: asyncio.BaseEventLoop | None = None

    def _get_loop(self) -> asyncio.BaseEventLoop:
        loop = asyncio.get_running_loop()

        if self._loop is None:
            self._loop = loop

        if loop is not self._loop:
            raise RuntimeError(f"{self!r} is bound to a different event loop")

        return loop

    def _wake_up_next(self) -> bool:
        """Wake up the first waiter that isn't done."""
        if not self._waiters:
            return False

        for _, _, fut in self._waiters:
            if not fut.done():
                self._value -= 1
                fut.set_result(True)
                # `fut` is now `done()` and not `cancelled()`.
                return True
        return False

    def cancel_waiting(self, exc: BaseException) -> None:
        """Cancel all waiters with the given exception."""
        for _, _, fut in self._waiters:
            if not fut.done():
                fut.set_exception(exc)

    @property
    def value(self) -> int:
        return self._value

    @property
    def max_value(self) -> int:
        return self._max_value

    @max_value.setter
    def max_value(self, new_value: int) -> None:
        """Update the semaphore's max value."""
        if new_value < 0:
            raise ValueError(f"Semaphore value must be >= 0: {new_value!r}")

        delta = new_value - self._max_value
        self._value += delta
        self._max_value += delta

        # Wake up any pending waiters
        for _ in range(max(0, delta)):
            if not self._wake_up_next():
                break

    @property
    def num_waiting(self) -> int:
        return len(self._waiters)

    def locked(self) -> bool:
        """Returns True if semaphore cannot be acquired immediately."""
        # Due to state, or FIFO rules (must allow others to run first).
        return self._value <= 0 or (any(not w.cancelled() for _, _, w in self._waiters))

    async def acquire(self, priority: int = 0) -> typing.Literal[True]:
        """Acquire a semaphore.

        If the internal counter is larger than zero on entry,
        decrement it by one and return True immediately.  If it is
        zero on entry, block, waiting until some other task has
        called release() to make it larger than 0, and then return
        True.
        """
        if not self.locked():
            # Maintain FIFO, wait for others to start even if _value > 0.
            self._value -= 1
            return True

        # To ensure that our objects don't have to be themselves comparable, we
        # maintain a global count and increment it on every insert. This way,
        # the tuple `(-priority, count, item)` will never have to compare `item`.
        self._comparison_counter += 1

        fut = self._get_loop().create_future()
        obj = (-priority, self._comparison_counter, fut)
        bisect.insort_right(self._waiters, obj)

        try:
            try:
                await fut
            finally:
                self._waiters.remove(obj)
        except asyncio.CancelledError:
            # Currently the only exception designed be able to occur here.
            if fut.done() and not fut.cancelled():
                # Our Future was successfully set to True via _wake_up_next(),
                # but we are not about to successfully acquire(). Therefore we
                # must undo the bookkeeping already done and attempt to wake
                # up someone else.
                self._value += 1
            raise

        finally:
            # New waiters may have arrived but had to wait due to FIFO.
            # Wake up as many as are allowed.
            while self._value > 0:
                if not self._wake_up_next():
                    break  # There was no-one to wake up.
        return True

    def release(self) -> None:
        """Release a semaphore, incrementing the internal counter by one.

        When it was zero on entry and another task is waiting for it to
        become larger than zero again, wake up that task.
        """
        if self._value >= self._max_value:
            raise ValueError("Semaphore released too many times")

        self._value += 1
        self._wake_up_next()

    def __call__(self, priority: int = 0) -> WrappedContextManager:
        """Allows specifying the priority by calling the context manager.

        This allows both `async with sem:` and `async with sem(priority=5):`.
        """
        return WrappedContextManager(
            context_manager=self,
            on_enter=lambda: self.acquire(priority),
        )

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        self.release()

    def __repr__(self) -> str:
        if self.locked():
            extra = f"locked, max value:{self._max_value}, waiters:{len(self._waiters)}"
        else:
            extra = f"unlocked, value:{self._value}, max value:{self._max_value}"

        return f"<{self.__class__.__name__} [{extra}]>"


class PriorityLock(PriorityDynamicBoundedSemaphore):
    def __init__(self):
        super().__init__(value=1)

    @PriorityDynamicBoundedSemaphore.max_value.setter
    def max_value(self, new_value: int) -> None:
        """Update the locks's max value."""
        raise ValueError("Max value of lock cannot be updated")


# Backwards compatibility
DynamicBoundedSemaphore = PriorityDynamicBoundedSemaphore


class ReschedulableTimeout:
    """Timeout object made to be efficiently rescheduled continuously."""

    def __init__(self, callback: typing.Callable[[], None]) -> None:
        self._timer: asyncio.TimerHandle | None = None
        self._callback = callback

        self._when: float = 0

    @functools.cached_property
    def _loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    def _timeout_trigger(self) -> None:
        now = self._loop.time()

        # If we triggered early, reschedule
        if self._when > now:
            self._reschedule()
            return

        self._timer = None
        self._callback()

    def _reschedule(self) -> None:
        if self._timer is not None:
            self._timer.cancel()

        self._timer = self._loop.call_at(self._when, self._timeout_trigger)

    def reschedule(self, delay: float) -> None:
        self._when = self._loop.time() + delay

        # If the current timer will expire too late (or isn't running), reschedule
        if self._timer is None or self._timer.when() > self._when:
            self._reschedule()

    def cancel(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


class LimitedSizeDict(MutableMapping):
    def __init__(self, other=(), *, maxlen: int) -> None:
        self._dict = OrderedDict(other)
        self.maxlen = maxlen

        self.update(other)

    def __getitem__(self, key):
        return self._dict[key]

    def __setitem__(self, key, value):
        if key in self._dict:
            self._dict.move_to_end(key)
        elif len(self._dict) == self.maxlen:
            self._dict.popitem(last=False)

        self._dict[key] = value

    def __delitem__(self, key) -> None:
        del self._dict[key]

    def __iter__(self):
        return self._dict.__iter__()

    def __len__(self) -> int:
        return len(self._dict)


class PacketReorder:
    """Packet reorderer."""

    def __init__(
        self,
        window: int,
        reordering_timeout: float,
        packet_callback,
        packet_comparison_func,
    ) -> None:
        assert 0 <= window < 256

        self.reordering_timeout = reordering_timeout
        self.reordering_timer = None

        self.window = window
        self.packet_callback = packet_callback
        self.packet_comparison_func = packet_comparison_func

        self.expected_tsn: int | None = None
        self.packets = LimitedSizeDict(maxlen=window)
        self.missing_tsns: list[int] = []

    @functools.cached_property
    def _loop(self) -> asyncio.BaseEventLoop:
        return asyncio.get_running_loop()

    @staticmethod
    def _range_mod(start: int, end: int):
        if start <= end:
            yield from range(start, end)
        else:
            yield from range(start, 256)
            yield from range(end)

    def maybe_emit_packets(self) -> None:
        while self.expected_tsn in self.packets:
            sent, packet = self.packets[self.expected_tsn]

            if sent:
                continue

            self.packet_callback(packet)
            self.packets[self.expected_tsn] = (True, packet)

            if self.reordering_timer is not None:
                with contextlib.suppress(ValueError):
                    self.missing_tsns.remove(self.expected_tsn)

            self.expected_tsn = (self.expected_tsn + 1) % 256

        # Cancel the unnecessary reordering timer if we've emitted everything
        if self.reordering_timer is not None and not self.missing_tsns:
            self.reordering_timer.cancel()
            self.reordering_timer = None

    def on_reordering_timeout(self) -> None:
        assert self.missing_tsns

        start = self.missing_tsns[0]
        end = self.missing_tsns[-1]

        for tsn in self._range_mod(start, (end + 1) % 256):
            if tsn not in self.packets:
                continue

            sent, packet = self.packets[tsn]
            if not sent:
                self.packet_callback(packet)
                self.packets[tsn] = (True, packet)

        self.expected_tsn = (end + 1) % 256

    def handle_packet(self, tsn: int, packet: typing.Any) -> None:
        # If we haven't seen a packet yet, we have no context and must accept the first
        # one as-is
        if self.expected_tsn is None:
            self.expected_tsn = tsn

        # Ignore duplicates
        if tsn in self.packets:
            if self.packet_comparison_func(self.packets[tsn][1], packet):
                return

            # For colliding TSNs with different contents, we should accept the packet
            _LOGGER.warning(
                "Device sent two packets with the same TSN=%d but different contents: %r != %r",
                tsn,
                packet,
                self.packets[tsn],
            )
            self.packets[tsn] = (True, packet)
            self.packet_callback(packet)
            return

        # Track our packet
        self.packets[tsn] = (False, packet)

        if tsn == self.expected_tsn:
            # If everything is good, accept the packet
            pass
        elif 0 < (tsn - self.expected_tsn) % 256 < self.window:
            # The TSN has rolled forward: we seemingly have missed a packet
            if self.reordering_timer is None:
                self.reordering_timer = self._loop.call_later(
                    self.reordering_timeout,
                    self.on_reordering_timeout,
                )

                # Keep track of the TSNs we are missing
                self.missing_tsns.clear()
                self.missing_tsns.extend(self._range_mod(self.expected_tsn, tsn + 1))
        else:
            # The TSN has rolled "back" BUT this isn't a duplicate packet (or is so old
            # that we cannot identify it as a duplicate): we must accept it
            self.expected_tsn = tsn

        self.maybe_emit_packets()
