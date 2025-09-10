"""Primitive data structures."""

from __future__ import annotations

import asyncio
import bisect
import collections
import contextlib
from fractions import Fraction
import functools
import heapq
import logging
import math
import types
import typing
import warnings

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


class Debouncer:
    """Generic debouncer supporting per-invocation expiration."""

    def __init__(self):
        self._times: dict[typing.Any, float] = {}
        self._queue: list[tuple[float, int, typing.Any]] = []

        self._last_time: int = 0
        self._dedup_counter: int = 0

    @functools.cached_property
    def _loop(self) -> asyncio.BaseEventLoop:
        return asyncio.get_running_loop()

    def clean(self, now: float | None = None) -> None:
        """Clean up stale timers."""
        if now is None:
            now = self._loop.time()

        # We store the negative expiration time to ensure we can pop expiring objects
        while self._queue and -self._queue[-1][0] < now:
            _, _, obj = self._queue.pop()
            self._times.pop(obj)

    def is_filtered(self, obj: typing.Any, now: float | None = None) -> bool:
        """Check if an object will be filtered."""
        if now is None:
            now = self._loop.time()

        # Clean up stale timers
        self.clean(now)

        # If an object still exists after cleaning, it won't be expired
        return obj in self._times

    def filter(self, obj: typing.Any, expire_in: float) -> bool:
        """Check if an object should be filtered. If not, store it."""
        now = self._loop.time()

        # For platforms with low-resolution clocks, we need to make sure that `obj` will
        # never be compared by `heapq`!
        if now > self._last_time:
            self._last_time = now
            self._dedup_counter = 0

        self._dedup_counter += 1

        # If the object is filtered, do nothing
        if self.is_filtered(obj, now=now):
            return True

        # Otherwise, queue it
        self._times[obj] = now + expire_in
        bisect.insort_right(self._queue, (-(now + expire_in), self._dedup_counter, obj))

        return False

    def __repr__(self) -> str:
        """String representation of the debouncer."""
        return f"<{self.__class__.__name__} [tracked:{len(self._queue)}]>"


class _LimiterContext:
    """Helper class to manage the async context for the RequestLimiter."""

    def __init__(self, limiter: RequestLimiter, priority: int) -> None:
        self._limiter = limiter
        self._priority = priority

    async def __aenter__(self) -> None:
        """Acquire a slot from the limiter."""
        await self._limiter._acquire(self._priority)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        """Release the slot back to the limiter."""
        self._limiter._release(self._priority)


class RequestLimiter:
    """Limits concurrent requests with cascading capacity for multiple priority levels."""

    def __init__(self, max_concurrency: int, capacities: dict[int, float]) -> None:
        """Initializes the RequestLimiter."""
        if max_concurrency < 0:
            raise ValueError(f"max_concurrency must be >= 0: {max_concurrency}")

        self._lock = asyncio.Lock()
        self._capacity_fractions = capacities
        self._sorted_priorities = sorted(capacities.keys())

        self._cumulative_capacity: dict[int, int] = {}
        self._max_concurrency = max_concurrency
        self._recalculate_capacity()

        self._active_requests_by_tier: typing.Counter[int] = collections.Counter()
        self._waiters: list[tuple[int, int, asyncio.Future]] = []
        self._comparison_counter = 0

    @property
    def active_requests(self) -> int:
        """Returns the total number of currently running requests."""
        return sum(self._active_requests_by_tier.values())

    @property
    def waiting_requests(self) -> int:
        """Returns the number of requests waiting for a slot."""
        return len(self._waiters)

    @property
    def max_concurrency(self) -> int:
        """Returns the maximum concurrency of the limiter."""
        return self._max_concurrency

    @max_concurrency.setter
    def max_concurrency(self, new_value: int) -> None:
        """Updates the maximum concurrency of the limiter."""
        self._max_concurrency = new_value
        self._recalculate_capacity()
        self._wake_waiters()

    @property
    def max_value(self) -> None:
        """Deprecated alias for `max_concurrency`."""
        warnings.warn(
            "`max_value` is deprecated, use `max_concurrency` instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.max_concurrency

    @max_value.setter
    def max_value(self, new_value: int) -> None:
        """Deprecated setter alias for `max_concurrency`."""
        warnings.warn(
            "`max_value` is deprecated, use `max_concurrency` instead",
            DeprecationWarning,
            stacklevel=2,
        )
        self.max_concurrency = new_value

    def _recalculate_capacity(self) -> None:
        # Assume that all of the fractions are simple
        divisors = [
            Fraction.from_float(f).limit_denominator(10).denominator
            for f in self._capacity_fractions.values()
        ]

        lcm = math.lcm(*divisors)

        if self._max_concurrency % lcm != 0:
            next_best = lcm - self._max_concurrency % lcm
            assert next_best > 0

            _LOGGER.warning(
                "Requested adapter concurrency %d is not compatible with priority fractions %r. Increasing concurrency to %d.",
                self._max_concurrency,
                self._capacity_fractions,
                self._max_concurrency + next_best,
            )
            self._max_concurrency += next_best

        cumulative_capacity = 0

        for priority in self._sorted_priorities:
            portion = self._capacity_fractions[priority] * self._max_concurrency
            cumulative_capacity += round(portion)

            self._cumulative_capacity[priority] = cumulative_capacity

    def __call__(self, priority: int = 0) -> _LimiterContext:
        """Returns an async context manager to safely acquire and release a slot."""
        return _LimiterContext(self, priority)

    def _get_effective_priority_tier(self, priority: int) -> int:
        """Finds the capacity tier that the given priority falls into."""
        if priority < self._sorted_priorities[0]:
            raise ValueError(
                f"Priority {priority} is lower than the lowest known priority "
                f"{self._sorted_priorities[0]} and has no allocated capacity"
            )

        idx = bisect.bisect_right(self._sorted_priorities, priority)
        return self._sorted_priorities[idx - 1]

    def locked(self, priority: int) -> bool:
        """Checks if a request with a given priority can run."""
        effective_tier = self._get_effective_priority_tier(priority)
        limit = self._cumulative_capacity[effective_tier]
        waiting_requests = 0

        if limit == 0:
            return True

        for tier, count in self._active_requests_by_tier.items():
            if tier > effective_tier:
                continue

            waiting_requests += count
            if waiting_requests >= limit:
                return True

        return False

    def _wake_waiters(self) -> None:
        """Wakes up any waiting tasks that can now run."""
        while self._waiters:
            waiter_priority, _, fut = self._waiters[0]
            priority = -waiter_priority  # We flip the sign when storing, for comparison

            if not self.locked(priority):
                heapq.heappop(self._waiters)
                if not fut.done():
                    effective_tier = self._get_effective_priority_tier(priority)
                    self._active_requests_by_tier[effective_tier] += 1
                    fut.set_result(None)
            else:
                break

    async def _acquire(self, priority: int = 0) -> bool:
        """Acquires a slot in the limiter, waiting if necessary."""
        effective_tier = self._get_effective_priority_tier(priority)

        # A task can run immediately if it has capacity AND it has a higher
        # priority than any task already waiting. This allows high-priority
        # tasks to jump the queue, while maintaining FIFO for tasks of the
        # same priority.
        highest_waiter_priority = (
            -self._waiters[0][0] if self._waiters else -float("inf")
        )

        if not self.locked(priority) and priority > highest_waiter_priority:
            self._active_requests_by_tier[effective_tier] += 1
            return True

        # To ensure that our objects don't have to be themselves comparable, we
        # maintain a global count and increment it on every insert. This way,
        # the tuple `(-priority, count, item)` will never have to compare `item`.
        self._comparison_counter += 1
        fut = asyncio.get_running_loop().create_future()
        waiter_obj = (-priority, self._comparison_counter, fut)
        heapq.heappush(self._waiters, waiter_obj)

        try:
            try:
                await fut
                return True
            finally:
                if waiter_obj in self._waiters:
                    self._waiters.remove(waiter_obj)
                    heapq.heapify(self._waiters)
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self._active_requests_by_tier[effective_tier] -= 1

            raise
        finally:
            self._wake_waiters()

    def _release(self, priority: int = 0) -> None:
        """Releases an acquired slot back to the limiter."""
        effective_tier = self._get_effective_priority_tier(priority)
        assert self._active_requests_by_tier[effective_tier] > 0
        self._active_requests_by_tier[effective_tier] -= 1
        self._wake_waiters()

    def cancel_waiting(self, exc: BaseException) -> None:
        """Cancel all waiters with the given exception."""
        for _, _, fut in self._waiters:
            if not fut.done():
                fut.set_exception(exc)

    def __repr__(self) -> str:
        """Provides a string representation of the limiter's state."""
        return (
            f"<{self.__class__.__name__}("
            f"max_concurrency={self._max_concurrency}"
            f", active={self.active_requests}"
            f", waiting={self.waiting_requests}"
            f")>"
        )
