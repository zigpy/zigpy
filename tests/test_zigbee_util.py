import asyncio
import logging
import sys

import pytest

from zigpy import util
from zigpy.exceptions import ControllerException
from zigpy.types.named import KeyData

from .async_mock import AsyncMock, MagicMock, call, patch, sentinel


class Listenable(util.ListenableMixin):
    def __init__(self):
        self._listeners = {}


def test_listenable():
    listen = Listenable()

    # Python 3.7 guarantees dict ordering so this will be called first to test error
    # handling
    broken_listener = MagicMock()
    broken_listener.event.side_effect = Exception()
    listen.add_listener(broken_listener)

    listener = MagicMock(spec_set=["event"])
    listen.add_listener(listener)
    listen.add_listener(listener)

    context_listener = MagicMock(spec_set=["event"])
    listen.add_context_listener(context_listener)

    listen.listener_event("event", "test1")
    listener.event.assert_has_calls([call("test1"), call("test1")], any_order=True)
    context_listener.event.assert_has_calls([call(listen, "test1")], any_order=True)
    broken_listener.event.assert_has_calls([call("test1")], any_order=True)
    assert listener.event.call_count == 2
    assert context_listener.event.call_count == 1
    assert broken_listener.event.call_count == 1

    listen.listener_event("non_existing_event", "test2")
    listener.event.assert_has_calls([call("test1"), call("test1")], any_order=True)
    context_listener.event.assert_has_calls([call(listen, "test1")], any_order=True)
    broken_listener.event.assert_has_calls([call("test1")], any_order=True)
    assert listener.event.call_count == 2
    assert context_listener.event.call_count == 1
    assert broken_listener.event.call_count == 1


class Logger(util.LocalLogMixin):
    log = MagicMock()


def test_log():
    log = Logger()
    log.debug("Test debug")
    log.exception("Test exception")
    log.info("Test info")
    log.warning("Test warn")
    log.error("Test error")


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="logging stacklevel kwarg was introduced in 3.8"
)
def test_log_stacklevel():
    class MockHandler(logging.Handler):
        emit = MagicMock()

    handler = MockHandler()

    LOGGER = logging.getLogger("test_log_stacklevel")
    LOGGER.setLevel(logging.DEBUG)
    LOGGER.addHandler(handler)

    class TestClass(util.LocalLogMixin):
        def log(self, lvl, msg, *args, **kwargs):
            LOGGER.log(lvl, msg, *args, **kwargs)

        def test_method(self):
            self.info("Test1")
            LOGGER.info("Test2")

    TestClass().test_method()

    assert handler.emit.call_count == 2

    indirect_call, direct_call = handler.emit.mock_calls
    (indirect,) = indirect_call.args
    (direct,) = direct_call.args

    assert indirect.message == "Test1"
    assert direct.message == "Test2"
    assert direct.levelname == indirect.levelname

    assert direct.module == indirect.module
    assert direct.filename == indirect.filename
    assert direct.funcName == indirect.funcName
    assert direct.lineno == indirect.lineno + 1


async def _test_retry(exception, retry_exceptions, n):
    counter = 0

    async def count():
        nonlocal counter
        counter += 1
        if counter <= n:
            exc = exception()
            exc._counter = counter
            raise exc

    await util.retry(count, retry_exceptions)
    return counter


async def test_retry_no_retries():
    counter = await _test_retry(Exception, Exception, 0)
    assert counter == 1


async def test_retry_always():
    with pytest.raises(ValueError) as exc_info:
        await _test_retry(ValueError, (IndexError, ValueError), 999)
    assert exc_info.value._counter == 3


async def test_retry_once():
    counter = await _test_retry(ValueError, ValueError, 1)
    assert counter == 2


async def _test_retryable(exception, retry_exceptions, n, tries=3, delay=0.001):
    counter = 0

    @util.retryable(retry_exceptions)
    async def count(x, y, z):
        assert x == y == z == 9
        nonlocal counter
        counter += 1
        if counter <= n:
            exc = exception()
            exc._counter = counter
            raise exc

    await count(9, 9, 9, tries=tries, delay=delay)
    return counter


async def test_retryable_no_retry():
    counter = await _test_retryable(Exception, Exception, 0, 0, 0)
    assert counter == 1


async def test_retryable_exception_no_retry():
    with pytest.raises(Exception) as exc_info:
        await _test_retryable(Exception, Exception, 1, 0, 0)
    assert exc_info.value._counter == 1


async def test_retryable_no_retries():
    counter = await _test_retryable(Exception, Exception, 0)
    assert counter == 1


async def test_retryable_always():
    with pytest.raises(ValueError) as exc_info:
        await _test_retryable(ValueError, (IndexError, ValueError), 999)
    assert exc_info.value._counter == 3


async def test_retryable_once():
    counter = await _test_retryable(ValueError, ValueError, 1)
    assert counter == 2


def test_zigbee_security_hash():
    message = bytes.fromhex("11223344556677884AF7")
    key = util.aes_mmo_hash(message)
    assert key == KeyData.convert("41618FC0C83B0E14A589954B16E31466")

    message = bytes.fromhex("7A939723A5C639B269161802819B")
    key = util.aes_mmo_hash(message)
    assert key == KeyData.convert("F93903721685FD329D26849B90F2959A")

    message = bytes.fromhex("83FED3407A939723A5C639B269161802AEBB")
    key = util.aes_mmo_hash(message)
    assert key == KeyData.convert("333C23686079468EB27BA24BD9C7E564")


@pytest.mark.parametrize(
    "message, expected_key",
    [
        (
            bytes.fromhex("11223344556677884AF7"),
            KeyData.convert("41618FC0C83B0E14A589954B16E31466"),
        ),
        (
            bytes.fromhex("83FED3407A939723A5C639B26916D505C3B5"),
            KeyData.convert("66B6900981E1EE3CA4206B6B861C02BB"),
        ),
    ],
)
def test_convert_install_code(message, expected_key):
    key = util.convert_install_code(message)
    assert key == expected_key


def test_fail_convert_install_code():
    key = util.convert_install_code(bytes([]))
    assert key is None

    message = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0xFF, 0xFF])
    key = util.convert_install_code(message)
    assert key is None


async def test_async_listener():
    listenable = Listenable()

    listener_1 = MagicMock(spec=["async_event"])
    listener_1.async_event.side_effect = AsyncMock(return_value=sentinel.result_1)

    listener_2 = MagicMock(spec=["async_event"])
    listener_2.async_event.side_effect = AsyncMock(return_value=sentinel.result_2)

    failed = MagicMock(spec=["async_event"])
    failed.async_event = AsyncMock(side_effect=RuntimeError("async listener exception"))

    listenable.add_listener(listener_1)
    listenable.add_context_listener(listener_2)
    listenable.add_listener(failed)

    r = await listenable.async_event("async_event", sentinel.data)
    assert len(r) == 2
    assert sentinel.result_1 in r
    assert sentinel.result_2 in r

    assert listener_1.async_event.call_count == 1
    assert listener_1.async_event.call_args[0][0] is sentinel.data

    # context listener
    assert listener_2.async_event.call_count == 1
    assert listener_2.async_event.call_args[0][0] is listenable
    assert listener_2.async_event.call_args[0][1] is sentinel.data

    # failed listener
    assert failed.async_event.call_count == 1
    assert failed.async_event.call_args[0][0] is sentinel.data

    r = await listenable.async_event("no_such_event", sentinel.no_data)
    assert r == []


def test_requests(monkeypatch):
    req_mock = MagicMock()
    monkeypatch.setattr(util, "Request", req_mock)
    r = util.Requests()
    r.new(sentinel.seq)
    assert req_mock.call_count == 1


async def test_request():
    pending = util.Requests()
    seq = 0x11

    req = pending.new(seq)
    assert seq not in pending
    assert req.result.done() is False
    with req:
        assert seq in pending
        assert req.result.done() is False
        assert req.sequence is seq
    assert req.result.done() is True
    assert req.result.cancelled() is True
    assert seq not in pending

    seq = sentinel.seq
    req = pending.new(seq)
    assert seq not in pending
    assert req.result.done() is False
    with req:
        assert seq in pending
        assert req.result.done() is False
        assert req.sequence is seq
        req.result.set_result(True)
    assert req.result.done() is True
    assert req.result.cancelled() is False
    assert seq not in pending


async def test_request_duplicate():
    pending = util.Requests()
    seq = 0x23
    with pending.new(seq):
        with pytest.raises(ControllerException):
            with pending.new(seq):
                pass


class _ClusterMock(util.CatchingTaskMixin):
    """Test class."""

    def __init__(self, logger):
        logger.setLevel(logging.DEBUG)
        self._logger = logger

    def log(self, lvl, msg, *args, **kwargs):
        return self._logger.log(lvl, msg, *args, **kwargs)

    async def a(self, exception=None):
        self.debug("test a")
        return await self._b(exception)

    async def _b(self, exception):
        self.warning("test b")
        if exception is None:
            return True
        raise exception()


@patch("zigpy.util.CatchingTaskMixin.catching_coro")
async def test_create_catching_task(catching_coro_mock):
    """Test catching task."""
    mock_cluster = _ClusterMock(logging.getLogger(__name__))
    coro = AsyncMock()
    mock_cluster.create_catching_task(coro)
    assert catching_coro_mock.call_count == 1
    assert catching_coro_mock.call_args[0][0] is coro


async def test_catching_coro(caplog):
    """Test catching_coro no exception."""
    caplog.set_level(level=logging.DEBUG)
    mock_cluster = _ClusterMock(logging.getLogger(__name__))
    await mock_cluster.catching_coro(mock_cluster.a())

    records = [r for r in caplog.records if r.name == __name__]
    assert records[0].levelno == logging.DEBUG
    assert records[0].message == "test a"
    assert records[1].levelno == logging.WARNING
    assert records[1].message == "test b"
    assert len(records) == 2


@pytest.mark.parametrize("exception", [None, asyncio.TimeoutError])
async def test_catching_task_expected_exception(exception, caplog):
    """Test CatchingTaskMixin allowed exceptions."""
    mock_cluster = _ClusterMock(logging.getLogger("expected_exceptions"))
    await mock_cluster.catching_coro(
        mock_cluster.a(asyncio.TimeoutError), exceptions=exception
    )

    records = [r for r in caplog.records if r.name == "expected_exceptions"]
    assert records[0].levelno == logging.DEBUG
    assert records[0].message == "test a"
    assert records[1].levelno == logging.WARNING
    assert records[1].message == "test b"
    assert len(records) == 2


@pytest.mark.parametrize(
    "to_raise, exception", [(RuntimeError, None), (asyncio.TimeoutError, RuntimeError)]
)
async def test_catching_task_unexpected_exception(to_raise, exception, caplog):
    """Test CatchingTaskMixin unexpected exceptions."""
    mock_cluster = _ClusterMock(logging.getLogger("unexpected_exceptions"))
    await mock_cluster.catching_coro(mock_cluster.a(to_raise), exceptions=exception)

    records = [r for r in caplog.records if r.name == "unexpected_exceptions"]
    assert records[0].levelno == logging.DEBUG
    assert records[0].message == "test a"
    assert records[1].levelno == logging.WARNING
    assert records[1].message == "test b"
    assert records[2].levelno == logging.ERROR
    assert records[2].message.startswith("Traceback (most recent call last)")
    assert len(records) == 3


async def test_dynamic_bounded_semaphore_simple_locking():
    """Test simple, serial locking/unlocking."""
    sem = util.DynamicBoundedSemaphore()

    assert "unlocked" not in repr(sem) and "locked" in repr(sem)

    assert sem.value == 0
    assert sem.max_value == 0
    assert sem.locked()

    # Invalid max value
    with pytest.raises(ValueError):
        sem.max_value = -1

    assert sem.value == 0
    assert sem.max_value == 0
    assert sem.locked()

    # Max value is now specified
    sem.max_value = 1
    assert not sem.locked()
    assert sem.max_value == 1
    assert sem.value == 1

    assert "unlocked" in repr(sem)

    # Semaphore can now be acquired
    async with sem:
        assert sem.value == 0
        assert sem.locked()

    assert not sem.locked()
    assert sem.max_value == 1
    assert sem.value == 1

    await sem.acquire()
    assert sem.value == 0
    assert sem.locked()
    sem.release()

    assert not sem.locked()
    assert sem.max_value == 1
    assert sem.value == 1

    with pytest.raises(ValueError):
        sem.release()


async def test_dynamic_bounded_semaphore_multiple_locking():
    """Test multiple locking/unlocking."""
    sem = util.DynamicBoundedSemaphore(5)

    assert sem.value == 5
    assert not sem.locked()

    async with sem:
        assert sem.value == 4
        assert not sem.locked()

        async with sem, sem, sem:
            assert sem.value == 1
            assert not sem.locked()

            with pytest.raises(RuntimeError):
                async with sem:
                    assert sem.locked()
                    assert sem.value == 0

                    raise RuntimeError()

            assert not sem.locked()
            assert sem.value == 1

        assert sem.value == 4
        assert not sem.locked()

    assert sem.value == 5
    assert not sem.locked()


async def test_dynamic_bounded_semaphore_runtime_limit_increase(event_loop):
    """Test changing the max_value at runtime."""

    sem = util.DynamicBoundedSemaphore(2)

    def set_limit(n):
        sem.max_value = n

    event_loop.call_later(0.1, set_limit, 3)

    async with sem:
        # Play with the value, testing edge cases
        sem.max_value = 100
        assert sem.value == 99
        assert not sem.locked()

        sem.max_value = 2
        assert sem.value == 1
        assert not sem.locked()

        sem.max_value = 1
        assert sem.value == 0
        assert sem.locked()

        # Setting it to `0` seems undefined but we keep track of locks so it works
        sem.max_value = 0
        assert sem.value == -1
        assert sem.locked()

        sem.max_value = 2
        assert sem.value == 1
        assert not sem.locked()

        async with sem:
            assert sem.locked()
            assert sem.value == 0
            assert sem.max_value == 2

            async with sem:
                # We're now locked until the limit is increased
                pass

            assert not sem.locked()
            assert sem.value == 1
            assert sem.max_value == 3

        assert sem.value == 2
        assert sem.max_value == 3

    assert sem.value == 3
    assert sem.max_value == 3


async def test_dynamic_bounded_semaphore_errors(event_loop):
    """Test semaphore handling errors and cancellation."""

    sem = util.DynamicBoundedSemaphore(1)

    def set_limit(n):
        sem.max_value = n

    async def acquire():
        async with sem:
            await asyncio.sleep(60)

    # The first acquire call will succeed
    acquire1 = asyncio.create_task(acquire())

    # The remaining two will stall
    acquire2 = asyncio.create_task(acquire())
    acquire3 = asyncio.create_task(acquire())
    await asyncio.sleep(0.1)

    # Cancel the first one, which holds the lock
    acquire1.cancel()

    # But also cancel the second one, which was waiting
    acquire2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await acquire1

    with pytest.raises(asyncio.CancelledError):
        await acquire2

    await asyncio.sleep(0.1)

    # The third one will have succeeded
    assert sem.locked()
    assert sem.value == 0
    assert sem.max_value == 1

    acquire3.cancel()
    with pytest.raises(asyncio.CancelledError):
        await acquire3

    assert not sem.locked()
    assert sem.value == 1
    assert sem.max_value == 1
