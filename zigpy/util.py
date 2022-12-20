from __future__ import annotations

import abc
import asyncio
import collections
import functools
import inspect
import logging
import sys
import traceback
import typing
import warnings

from crccheck.crc import CrcX25
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.modes import ECB

from zigpy.exceptions import ControllerException, ZigbeeException
import zigpy.types as t

LOGGER = logging.getLogger(__name__)


class ListenableMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._listeners: dict[int, tuple[typing.Callable, bool]] = {}

    def _add_listener(self, listener, include_context):
        id_ = id(listener)
        while id_ in self._listeners:
            id_ += 1
        self._listeners[id_] = (listener, include_context)
        return id_

    def add_listener(self, listener):
        return self._add_listener(listener, include_context=False)

    def add_context_listener(self, listener):
        return self._add_listener(listener, include_context=True)

    def listener_event(self, method_name, *args):
        result = []
        for listener, include_context in self._listeners.values():
            method = getattr(listener, method_name, None)

            if not method:
                continue

            try:
                if include_context:
                    result.append(method(self, *args))
                else:
                    result.append(method(*args))
            except Exception as e:
                LOGGER.warning(
                    "Error calling listener %r with args %r: %r", method, args, e
                )
                LOGGER.debug(
                    "Error calling listener %r with args %r", method, args, exc_info=e
                )
        return result

    async def async_event(self, method_name, *args):
        tasks = []
        for listener, include_context in self._listeners.values():
            method = getattr(listener, method_name, None)

            if not method:
                continue

            if include_context:
                tasks.append(method(self, *args))
            else:
                tasks.append(method(*args))

        results = []
        for result in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(result, Exception):
                LOGGER.warning(
                    "Error calling listener %r with args %r: %r", method, args, result
                )
                LOGGER.debug(
                    "Error calling listener %r with args %r",
                    method,
                    args,
                    exc_info=result,
                )
            else:
                results.append(result)
        return results


class LocalLogMixin:
    @abc.abstractmethod
    def log(self, lvl: int, msg: str, *args, **kwargs):  # pragma: no cover
        pass

    def _log(self, lvl: int, msg: str, *args, **kwargs):
        if sys.version_info >= (3, 8):
            # We have to exclude log, _log, and info
            return self.log(lvl, msg, *args, stacklevel=4, **kwargs)

        return self.log(lvl, msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        return self._log(logging.ERROR, msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        return self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        return self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        return self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        return self._log(logging.ERROR, msg, *args, **kwargs)


async def retry(func, retry_exceptions, tries=3, delay=0.1):
    """Retry a function in case of exception

    Only exceptions in `retry_exceptions` will be retried.
    """
    while True:
        LOGGER.debug("Tries remaining: %s", tries)
        try:
            r = await func()
            return r
        except retry_exceptions:
            if tries <= 1:
                raise
            tries -= 1
            await asyncio.sleep(delay)


def retryable(retry_exceptions, tries=1, delay=0.1):
    """Return a decorator which makes a function able to be retried

    This adds "tries" and "delay" keyword arguments to the function. Only
    exceptions in `retry_exceptions` will be retried.
    """

    def decorator(func):
        nonlocal tries, delay

        @functools.wraps(func)
        def wrapper(*args, tries=tries, delay=delay, **kwargs):
            if tries <= 1:
                return func(*args, **kwargs)
            return retry(
                functools.partial(func, *args, **kwargs),
                retry_exceptions,
                tries=tries,
                delay=delay,
            )

        return wrapper

    return decorator


retryable_request = retryable((ZigbeeException, asyncio.TimeoutError))


def aes_mmo_hash_update(length: int, result: bytes, data: bytes) -> tuple[int, bytes]:
    block_size = AES.block_size // 8

    while len(data) >= block_size:
        block = bytes(data[:block_size])

        # Encrypt
        aes = Cipher(AES(bytes(result)), ECB()).encryptor()
        result = bytearray(aes.update(block) + aes.finalize())

        # XOR plaintext into ciphertext
        for i in range(block_size):
            result[i] ^= block[i]

        data = data[block_size:]
        length += block_size

    return (length, result)


def aes_mmo_hash(data: bytes) -> t.KeyData:
    block_size = AES.block_size // 8

    result_len = 0
    remaining_length = 0
    length = len(data)
    result = bytearray([0] * block_size)
    temp = bytearray([0] * block_size)

    if data and length > 0:
        remaining_length = length & (block_size - 1)
        if length >= block_size:
            # Mask out the lower byte since hash update will hash
            # everything except the last piece, if the last piece
            # is less than 16 bytes.
            hashed_length = length & ~(block_size - 1)
            (result_len, result) = aes_mmo_hash_update(result_len, result, data)
            data = data[hashed_length:]

    for i in range(remaining_length):
        temp[i] = data[i]

    # Per the spec, Concatenate a 1 bit followed by all zero bits
    # (previous memset() on temp[] set the rest of the bits to zero)
    temp[remaining_length] = 0x80
    result_len += remaining_length

    # If appending the bit string will push us beyond the 16-byte boundary
    # we must hash that block and append another 16-byte block.
    if (block_size - remaining_length) < 3:
        (result_len, result) = aes_mmo_hash_update(result_len, result, temp)

        # Since this extra data is due to the concatenation,
        # we remove that length. We want the length of data only
        # and not the padding.
        result_len -= block_size
        temp = bytearray([0] * block_size)

    bit_size = result_len * 8
    temp[block_size - 2] = (bit_size >> 8) & 0xFF
    temp[block_size - 1] = (bit_size) & 0xFF

    (result_len, result) = aes_mmo_hash_update(result_len, result, temp)

    return t.KeyData(result)


def convert_install_code(code: bytes) -> t.KeyData:
    if len(code) not in (8, 10, 14, 18):
        return None

    real_crc = bytes(code[-2:])
    crc = CrcX25()
    crc.process(code[:-2])
    if real_crc != crc.finalbytes(byteorder="little"):
        return None

    return aes_mmo_hash(code)


class Request:
    """Request context manager."""

    def __init__(self, pending: dict, sequence: t.uint8_t) -> None:
        """Init context manager for requests."""
        assert sequence not in pending
        self._pending = pending
        self._result: asyncio.Future = asyncio.Future()
        self._sequence = sequence

    @property
    def result(self) -> asyncio.Future:
        return self._result

    @property
    def sequence(self) -> t.uint8_t:
        """Send Future."""
        return self._sequence

    def __enter__(self):
        """Return context manager."""
        self._pending[self.sequence] = self
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """Clean up pending on exit."""
        if not self.result.done():
            self.result.cancel()
        self._pending.pop(self.sequence)

        return not exc_type


class Requests(dict):
    def new(self, sequence: t.uint8_t) -> Request:
        """Wrap new request into a context manager."""
        try:
            return Request(self, sequence)
        except AssertionError:
            LOGGER.debug("Duplicate %s TSN", sequence)
            raise ControllerException(f"duplicate {sequence} TSN") from AssertionError


class CatchingTaskMixin(LocalLogMixin):
    """Allow creating tasks suppressing exceptions."""

    def create_catching_task(
        self,
        target: typing.Coroutine,
        exceptions: type[Exception] | tuple | None = None,
    ) -> None:
        """Create a task."""
        asyncio.create_task(self.catching_coro(target, exceptions))

    async def catching_coro(
        self,
        target: typing.Coroutine,
        exceptions: type[Exception] | tuple | None = None,
    ) -> typing.Any:
        """Wrap a target coro and catch specified exceptions."""
        if exceptions is None:
            exceptions = (asyncio.TimeoutError, ZigbeeException)

        try:
            return await target
        except exceptions:
            pass
        except (Exception, asyncio.CancelledError):  # pylint: disable=broad-except
            # Do not print the wrapper in the traceback
            frames = len(inspect.trace()) - 1
            exc_msg = traceback.format_exc(-frames)
            self.exception("%s", exc_msg)

        return None


class DynamicBoundedSemaphore(asyncio.Semaphore):
    """
    `asyncio.BoundedSemaphore` with public interface to access and change the max value.
    """

    def __init__(self, value: int = 0) -> None:
        self._value: int = value
        self._max_value: int = value

        self._waiters: collections.deque = collections.deque()
        self._wakeup_scheduled: bool = False

    @property
    @functools.lru_cache(maxsize=None)
    def _loop(self) -> asyncio.BaseEventLoop:
        return asyncio.get_running_loop()

    def _wake_up_next(self) -> None:
        while self._waiters:
            waiter = self._waiters.popleft()

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
        """
        Update the semaphore's max value.
        """
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

    async def acquire(self):
        """
        Acquire a semaphore.

        If the internal counter is larger than zero on entry, decrement it by one and
        return True immediately.  If it is zero on entry, block, waiting until some
        other coroutine has called release() to make it larger than 0, and then return
        True.
        """

        # _wakeup_scheduled is set if *another* task is scheduled to wakeup
        # but its acquire() is not resumed yet
        while self._wakeup_scheduled or self._value <= 0:
            fut = self._loop.create_future()
            self._waiters.append(fut)

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
        """
        Release a semaphore, incrementing the internal counter by one.

        When it was zero on entry and another coroutine is waiting for it to become
        larger than zero again, wake up that coroutine.
        """
        if self._value >= self._max_value:
            raise ValueError("Semaphore released too many times")

        self._value += 1
        self._wake_up_next()

    async def __aenter__(self) -> None:
        await self.acquire()
        return None

    async def __aexit__(self, exc_type, exc, tb):
        self.release()

    def __repr__(self) -> str:
        if self.locked():
            extra = f"locked, max value:{self._max_value}, waiters:{len(self._waiters)}"
        else:
            extra = f"unlocked, value:{self._value}, max value:{self._max_value}"

        return f"<{self.__class__.__name__} [{extra}]>"


def deprecated(message: str) -> typing.Callable[[typing.Callable], typing.Callable]:
    """
    Decorator that emits a DeprecationWarning when the function or property is accessed.
    """

    def decorator(function: typing.Callable) -> typing.Callable:
        @functools.wraps(function)
        def replacement(*args, **kwargs):
            warnings.warn(
                f"{function.__name__} is deprecated: {message}", DeprecationWarning
            )

            return function(*args, **kwargs)

        return replacement

    return decorator


def deprecated_attrs(
    mapping: dict[str, typing.Any]
) -> typing.Callable[[str], typing.Any]:
    """
    Create a module-level `__getattr__` function that remaps deprecated objects.
    """

    def __getattr__(name: str) -> typing.Any:
        if name not in mapping:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

        replacement = mapping[name]

        warnings.warn(
            (
                f"`{__name__}.{name}` has been renamed to"
                f" `{__name__}.{replacement.__name__}`"
            ),
            DeprecationWarning,
        )
        return replacement

    return __getattr__
