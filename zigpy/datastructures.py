"""Primitive data structures."""
from __future__ import annotations

import asyncio
import contextlib
import functools
import heapq
import types
import typing


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


class PriorityDynamicBoundedSemaphore(asyncio.Semaphore):
    """`asyncio.BoundedSemaphore` with public interface to change the max value."""

    def __init__(self, value: int = 0) -> None:
        self._value: int = value
        self._max_value: int = value
        self._comparison_counter: int = 0

        self._waiters: list[tuple[int, int, asyncio.Future]] = []
        self._wakeup_scheduled: bool = False

    @property
    @functools.lru_cache(maxsize=None)
    def _loop(self) -> asyncio.BaseEventLoop:
        return asyncio.get_running_loop()

    def _wake_up_next(self) -> None:
        while self._waiters:
            _, _, waiter = heapq.heappop(self._waiters)

            if not waiter.done():
                waiter.set_result(None)
                self._wakeup_scheduled = True
                return

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
        for _ in range(min(len(self._waiters), max(0, delta))):
            self._wake_up_next()

    @property
    def num_waiting(self) -> int:
        return len(self._waiters)

    def locked(self) -> bool:
        """Returns True if semaphore cannot be acquired immediately."""
        return self._value <= 0

    async def acquire(self, priority: int = 0) -> typing.Literal[True]:
        """Acquire a semaphore.

        If the internal counter is larger than zero on entry, decrement it by one and
        return True immediately.  If it is zero on entry, block, waiting until some
        other coroutine has called release() to make it larger than 0, and then return
        True.
        """

        # _wakeup_scheduled is set if *another* task is scheduled to wakeup
        # but its acquire() is not resumed yet
        while self._wakeup_scheduled or self._value <= 0:
            # To ensure that our objects don't have to be themselves comparable, we
            # maintain a global count and increment it on every insert. This way,
            # the tuple `(-priority, count, item)` will never have to compare `item`.
            self._comparison_counter += 1

            fut = self._loop.create_future()
            obj = (-priority, self._comparison_counter, fut)
            heapq.heappush(self._waiters, obj)

            try:
                await fut
                # reset _wakeup_scheduled *after* waiting for a future
                self._wakeup_scheduled = False
            except asyncio.CancelledError:
                self._wake_up_next()
                raise

        assert self._value > 0
        self._value -= 1
        return True

    def release(self) -> None:
        """Release a semaphore, incrementing the internal counter by one.

        When it was zero on entry and another coroutine is waiting for it to become
        larger than zero again, wake up that coroutine.
        """
        if self._value >= self._max_value:
            raise ValueError("Semaphore released too many times")

        self._value += 1
        self._wake_up_next()

    def __call__(self, priority: int = 0):
        """Allows specifying the priority by calling the context manager.

        This allows both `async with sem:` and `async with sem(priority=5):`.
        """
        return WrappedContextManager(
            context_manager=self,
            on_enter=lambda: self.acquire(priority),
        )

    async def __aenter__(self) -> None:
        await self.acquire()
        return None

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
