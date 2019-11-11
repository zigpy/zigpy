import asyncio
import functools
import logging
from crccheck.crc import CrcX25
from Crypto.Cipher import AES

import zigpy.types as t
from zigpy.exceptions import DeliveryError

LOGGER = logging.getLogger(__name__)


class ListenableMixin:
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
                LOGGER.warning("Error calling listener.%s: %s", method_name, e)
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
                LOGGER.warning("Error calling listener: %s", result)
            else:
                results.append(result)
        return results


class LocalLogMixin:
    def debug(self, msg, *args):
        return self.log(logging.DEBUG, msg, *args)

    def info(self, msg, *args):
        return self.log(logging.INFO, msg, *args)

    def warn(self, msg, *args):
        return self.log(logging.WARNING, msg, *args)

    def error(self, msg, *args):
        return self.log(logging.ERROR, msg, *args)


async def retry(func, retry_exceptions, tries=3, delay=0.1):
    """Retry a function in case of exception

    Only exceptions in `retry_exceptions` will be retried.
    """
    while True:
        print("Tries remaining: %s" % (tries,))
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


retryable_request = retryable((DeliveryError, asyncio.TimeoutError))


def aes_mmo_hash_update(length, result, data):
    while len(data) >= AES.block_size:
        # Encrypt
        aes = AES.new(bytes(result), AES.MODE_ECB)
        result = bytearray(aes.encrypt(bytes(data[: AES.block_size])))

        # XOR
        for i in range(AES.block_size):
            result[i] ^= bytes(data[: AES.block_size])[i]

        data = data[AES.block_size :]
        length += AES.block_size

    return (length, result)


def aes_mmo_hash(data):
    result_len = 0
    remaining_length = 0
    length = len(data)
    result = bytearray([0] * AES.block_size)
    temp = bytearray([0] * AES.block_size)

    if data and length > 0:
        remaining_length = length & (AES.block_size - 1)
        if length >= AES.block_size:
            # Mask out the lower byte since hash update will hash
            # everything except the last piece, if the last piece
            # is less than 16 bytes.
            hashed_length = length & ~(AES.block_size - 1)
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
    if (AES.block_size - remaining_length) < 3:
        (result_len, result) = aes_mmo_hash_update(result_len, result, temp)

        # Since this extra data is due to the concatenation,
        # we remove that length. We want the length of data only
        # and not the padding.
        result_len -= AES.block_size
        temp = bytearray([0] * AES.block_size)

    bit_size = result_len * 8
    temp[AES.block_size - 2] = (bit_size >> 8) & 0xFF
    temp[AES.block_size - 1] = (bit_size) & 0xFF

    (result_len, result) = aes_mmo_hash_update(result_len, result, temp)

    return t.KeyData([t.uint8_t(c) for c in result])


def convert_install_code(code):
    if len(code) not in (8, 10, 14, 18):
        return None

    real_crc = bytes(code[-2:])
    crc = CrcX25()
    crc.process(code[:-2])
    if real_crc != crc.finalbytes(byteorder='little'):
        return None

    return aes_mmo_hash(code)


class Request:
    """Request context manager."""

    def __init__(self, pending: dict, sequence: t.uint8_t) -> None:
        """Init context manager for requests."""
        assert sequence not in pending
        self._pending = pending
        self._result = asyncio.Future()
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
        return Request(self, sequence)
