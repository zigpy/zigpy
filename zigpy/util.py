from __future__ import annotations

import abc
import asyncio
import functools
import inspect
import itertools
import logging
import traceback
import types
import typing
import warnings

from crccheck.crc import CrcX25
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.modes import ECB
from typing_extensions import Self

from zigpy.datastructures import DynamicBoundedSemaphore  # noqa: F401
from zigpy.exceptions import ControllerException, ZigbeeException
import zigpy.types as t

LOGGER = logging.getLogger(__name__)

_T = typing.TypeVar("_T")


class ListenableMixin:
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._listeners: dict[int, tuple[typing.Callable, bool]] = {}

    def _add_listener(self, listener: typing.Any, include_context: bool) -> int:
        id_ = id(listener)
        while id_ in self._listeners:
            id_ += 1
        self._listeners[id_] = (listener, include_context)
        return id_

    def add_listener(self, listener: typing.Any) -> int:
        return self._add_listener(listener, include_context=False)

    def add_context_listener(self, listener: CatchingTaskMixin) -> int:
        return self._add_listener(listener, include_context=True)

    def remove_listener(self, listener: typing.Any) -> None:
        for id_, (attached_listener, _) in self._listeners.items():
            if attached_listener is listener:
                del self._listeners[id_]
                break

    def listener_event(self, method_name: str, *args) -> list[typing.Any | None]:
        result = []
        for listener, include_context in tuple(self._listeners.values()):
            method = getattr(listener, method_name, None)

            if method is None:
                continue

            try:
                if include_context:
                    result.append(method(self, *args))
                else:
                    result.append(method(*args))
            except Exception as e:  # noqa: BLE001
                LOGGER.debug(
                    "Error calling listener %r with args %r", method, args, exc_info=e
                )
        return result

    async def async_event(self, method_name: str, *args) -> list[typing.Any]:
        tasks = []
        for listener, include_context in tuple(self._listeners.values()):
            method = getattr(listener, method_name, None)

            if method is None:
                continue

            if include_context:
                tasks.append(method(self, *args))
            else:
                tasks.append(method(*args))

        results = []
        for result in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(result, Exception):
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

    def _log(self, lvl: int, msg: str, *args, **kwargs) -> None:
        return self.log(lvl, msg, *args, stacklevel=4, **kwargs)

    def exception(self, msg, *args, **kwargs):
        return self._log(logging.ERROR, msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        return self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        return self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        return self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        return self._log(logging.ERROR, msg, *args, **kwargs)


async def retry(
    func: typing.Callable[[], typing.Awaitable[typing.Any]],
    retry_exceptions: typing.Iterable[BaseException],
    tries: int = 3,
    delay: float = 0.1,
) -> typing.Any:
    """Retry a function in case of exception

    Only exceptions in `retry_exceptions` will be retried.
    """
    while True:
        LOGGER.debug("Tries remaining: %s", tries)
        try:
            return await func()
        except retry_exceptions:
            if tries <= 1:
                raise
            tries -= 1
            await asyncio.sleep(delay)


def retryable(
    retry_exceptions: typing.Iterable[BaseException], tries: int = 1, delay: float = 0.1
) -> typing.Callable:
    """Return a decorator which makes a function able to be retried.
    Only exceptions in `retry_exceptions` will be retried.
    """

    def decorator(func: typing.Callable) -> typing.Callable:
        nonlocal tries, delay

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
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


retryable_request = functools.partial(
    retryable, (ZigbeeException, asyncio.TimeoutError)
)


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


T = typing.TypeVar("T")


class Request(typing.Generic[T]):
    """Request context manager."""

    def __init__(self, pending: dict, sequence: T) -> None:
        """Init context manager for requests."""
        self._pending = pending
        self._result: asyncio.Future = asyncio.Future()
        self._sequence = sequence

    @property
    def result(self) -> asyncio.Future:
        return self._result

    @property
    def sequence(self) -> T:
        """Request sequence."""
        return self._sequence

    def __enter__(self) -> Self:
        """Return context manager."""
        self._pending[self.sequence] = self
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: types.TracebackType | None,
    ) -> bool:
        """Clean up pending on exit."""
        if not self.result.done():
            self.result.cancel()
        self._pending.pop(self.sequence)

        return not exc_type


class Requests(dict, typing.Generic[T]):
    def new(self, sequence: T) -> Self[T]:
        """Wrap new request into a context manager."""
        if sequence in self:
            LOGGER.debug("Duplicate %s TSN: pending %s", sequence, self)
            raise ControllerException(f"Duplicate TSN: {sequence}")

        return Request(self, sequence)


class CatchingTaskMixin(LocalLogMixin):
    """Allow creating tasks suppressing exceptions."""

    _tasks: set[asyncio.Future[typing.Any]] = set()

    def create_catching_task(
        self,
        target: typing.Coroutine,
        exceptions: type[Exception] | tuple | None = None,
        name: str | None = None,
    ) -> None:
        """Create a task."""
        task = asyncio.get_running_loop().create_task(
            self.catching_coro(target, exceptions), name=name
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.remove)

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


def deprecated(message: str) -> typing.Callable[[typing.Callable], typing.Callable]:
    """Decorator that emits a DeprecationWarning when the function or property is accessed."""

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
    mapping: dict[str, typing.Any],
) -> typing.Callable[[str], typing.Any]:
    """Create a module-level `__getattr__` function that remaps deprecated objects."""

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


def pick_optimal_channel(
    channel_energy: dict[int, float],
    channels: t.Channels = t.Channels.from_channel_list([11, 15, 20, 25]),
    *,
    kernel: list[float] = (0.1, 0.5, 1.0, 0.5, 0.1),
    channel_penalty: dict[int, float] = {
        11: 2.0,  # ZLL but WiFi interferes
        12: 3.0,
        13: 3.0,
        14: 3.0,
        15: 1.0,  # ZLL
        16: 3.0,
        17: 3.0,
        18: 3.0,
        19: 3.0,
        20: 1.0,  # ZLL
        21: 3.0,
        22: 3.0,
        23: 3.0,
        24: 3.0,
        25: 1.0,  # ZLL
        26: 2.0,  # Not ZLL but WiFi can interfere in some regions
    },
) -> int:
    """Scans all channels and picks the best one from the given mask."""
    assert len(kernel) % 2 == 1
    kernel_width = (len(kernel) - 1) // 2

    # Scan all channels even if we're restricted to picking among a few, since
    # nearby channels will affect our decision
    assert set(channel_energy.keys()) == set(t.Channels.ALL_CHANNELS)  # type: ignore[call-overload]

    # We don't know energies above channel 26 or below 11. Assume the scan results
    # just continue indefinitely with the last-seen value.
    ext_energies = (
        [channel_energy[11]] * kernel_width
        + [channel_energy[c] for c in t.Channels.ALL_CHANNELS]
        + [channel_energy[26]] * kernel_width
    )

    # Incorporate the energies of nearby channels into our calculation by performing
    # a discrete convolution with the provided kernel.
    convolution = ext_energies[:]

    for i in range(len(ext_energies)):
        for j in range(-kernel_width, kernel_width + 1):
            if 0 <= i + j < len(convolution):
                convolution[i + j] += ext_energies[i] * kernel[kernel_width + j]

    # Crop off the extended bounds, leaving us with an array of the original size
    convolution = convolution[kernel_width:-kernel_width]

    # Incorporate a penalty to avoid specific channels unless absolutely necessary.
    # Adding `1` ensures the score is positive and the channel penalty gets applied even
    # when the reported LQI is zero.
    scores = {
        c: (1 + convolution[c - 11]) * channel_penalty.get(c, 1.0)
        for c in t.Channels.ALL_CHANNELS
    }
    optimal_channel = min(channels, key=lambda c: scores[c])

    LOGGER.info("Optimal channel is %s", optimal_channel)
    LOGGER.debug("Channel scores: %s", scores)

    return optimal_channel


class Singleton:
    """Singleton class."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"<Singleton {self.name!r}>"

    def __hash__(self) -> int:
        return hash(self.name)


def filter_relays(relays: list[int]) -> list[int]:
    """Filter out invalid relays."""
    filtered_relays = []

    # BUG: relays sometimes include 0x0000 or duplicate entries
    for relay in relays:
        if relay != 0x0000 and relay not in filtered_relays:
            filtered_relays.append(relay)

    return filtered_relays


def combine_concurrent_calls(
    function: typing.Callable[
        ..., typing.Coroutine[typing.Any, typing.Any, typing.Any]
    ],
) -> typing.Callable[..., typing.Coroutine[typing.Any, typing.Any, typing.Any]]:
    """Decorator that allows concurrent calls to expensive coroutines to share a result."""

    tasks: dict[tuple, asyncio.Task] = {}
    signature = inspect.signature(function)

    @functools.wraps(function)
    async def replacement(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()

        # XXX: all args and kwargs are assumed to be hashable
        key = tuple(bound.arguments.items())

        if key in tasks:
            return await tasks[key]

        tasks[key] = asyncio.create_task(function(*args, **kwargs))

        try:
            return await tasks[key]
        finally:
            assert tasks[key].done()
            del tasks[key]

    return replacement


async def async_iterate_in_chunks(
    iterable: typing.Iterable[_T], chunk_size: int
) -> typing.AsyncGenerator[list[_T], None]:
    """Safely iterate over a synchronous iterable in chunks."""
    loop = asyncio.get_running_loop()
    iterator = iter(iterable)

    while True:
        chunk = await loop.run_in_executor(
            None, list, itertools.islice(iterator, chunk_size)
        )

        if not chunk:
            break

        yield chunk
