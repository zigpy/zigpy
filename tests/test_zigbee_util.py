import asyncio
import logging
import sys

import pytest

from zigpy import util
from zigpy.exceptions import ControllerException

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
    (indirect,) = indirect_call[1]
    (direct,) = direct_call[1]

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
    message = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x4A, 0xF7])
    key = util.aes_mmo_hash(message)
    assert key == [
        0x41,
        0x61,
        0x8F,
        0xC0,
        0xC8,
        0x3B,
        0x0E,
        0x14,
        0xA5,
        0x89,
        0x95,
        0x4B,
        0x16,
        0xE3,
        0x14,
        0x66,
    ]

    message = bytes(
        [
            0x7A,
            0x93,
            0x97,
            0x23,
            0xA5,
            0xC6,
            0x39,
            0xB2,
            0x69,
            0x16,
            0x18,
            0x02,
            0x81,
            0x9B,
        ]
    )
    key = util.aes_mmo_hash(message)
    assert key == [
        0xF9,
        0x39,
        0x03,
        0x72,
        0x16,
        0x85,
        0xFD,
        0x32,
        0x9D,
        0x26,
        0x84,
        0x9B,
        0x90,
        0xF2,
        0x95,
        0x9A,
    ]

    message = bytes(
        [
            0x83,
            0xFE,
            0xD3,
            0x40,
            0x7A,
            0x93,
            0x97,
            0x23,
            0xA5,
            0xC6,
            0x39,
            0xB2,
            0x69,
            0x16,
            0x18,
            0x02,
            0xAE,
            0xBB,
        ]
    )
    key = util.aes_mmo_hash(message)
    assert key == [
        0x33,
        0x3C,
        0x23,
        0x68,
        0x60,
        0x79,
        0x46,
        0x8E,
        0xB2,
        0x7B,
        0xA2,
        0x4B,
        0xD9,
        0xC7,
        0xE5,
        0x64,
    ]


@pytest.mark.parametrize(
    "message, expected_key",
    [
        (
            bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x4A, 0xF7]),
            [
                0x41,
                0x61,
                0x8F,
                0xC0,
                0xC8,
                0x3B,
                0x0E,
                0x14,
                0xA5,
                0x89,
                0x95,
                0x4B,
                0x16,
                0xE3,
                0x14,
                0x66,
            ],
        ),
        (
            bytes(
                [
                    0x83,
                    0xFE,
                    0xD3,
                    0x40,
                    0x7A,
                    0x93,
                    0x97,
                    0x23,
                    0xA5,
                    0xC6,
                    0x39,
                    0xB2,
                    0x69,
                    0x16,
                    0xD5,
                    0x05,
                    0xC3,
                    0xB5,
                ]
            ),
            [
                0x66,
                0xB6,
                0x90,
                0x09,
                0x81,
                0xE1,
                0xEE,
                0x3C,
                0xA4,
                0x20,
                0x6B,
                0x6B,
                0x86,
                0x1C,
                0x02,
                0xBB,
            ],
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
    assert caplog.records[0].levelno == logging.DEBUG
    assert caplog.records[0].message == "test a"
    assert caplog.records[1].levelno == logging.WARNING
    assert caplog.records[1].message == "test b"
    assert len(caplog.records) == 2


@pytest.mark.parametrize("exception", [None, asyncio.TimeoutError])
async def test_catching_task_expected_exception(exception, caplog):
    """Test CatchingTaskMixin allowed exceptions."""
    mock_cluster = _ClusterMock(logging.getLogger("expected_exceptions"))
    await mock_cluster.catching_coro(
        mock_cluster.a(asyncio.TimeoutError), exceptions=exception
    )
    assert caplog.records[0].levelno == logging.DEBUG
    assert caplog.records[0].message == "test a"
    assert caplog.records[1].levelno == logging.WARNING
    assert caplog.records[1].message == "test b"
    assert len(caplog.records) == 2


@pytest.mark.parametrize(
    "to_raise, exception", [(RuntimeError, None), (asyncio.TimeoutError, RuntimeError)]
)
async def test_catching_task_unexpected_exception(to_raise, exception, caplog):
    """Test CatchingTaskMixin unexpected exceptions."""
    mock_cluster = _ClusterMock(logging.getLogger("unexpected_exceptions"))
    await mock_cluster.catching_coro(mock_cluster.a(to_raise), exceptions=exception)
    assert caplog.records[0].levelno == logging.DEBUG
    assert caplog.records[0].message == "test a"
    assert caplog.records[1].levelno == logging.WARNING
    assert caplog.records[1].message == "test b"
    assert caplog.records[2].levelno == logging.ERROR
    assert caplog.records[2].message.startswith("Traceback (most recent call last)")
    assert len(caplog.records) == 3
