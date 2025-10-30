from __future__ import annotations

import asyncio
import logging
import time
import typing

import pytest

from zigpy import util
from zigpy.types.named import EUI64, KeyData

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

    listen.remove_listener(object())
    listen.remove_listener(listener)
    listen.remove_listener(listener)
    listen.remove_listener(broken_listener)
    listen.remove_listener(context_listener)
    listen.listener_event("event", "test1")
    assert listener.event.call_count == 2
    assert context_listener.event.call_count == 1
    assert broken_listener.event.call_count == 1


def test_listenable_mutating():
    listen = Listenable()
    mutating_listener = MagicMock()
    mutating_listener.event.side_effect = lambda value: listen.remove_listener(
        mutating_listener
    )

    listen.add_listener(mutating_listener)
    listen.listener_event("event", "value")

    assert mutating_listener.event.mock_calls == [call("value")]
    assert listen._listeners == {}


class Logger(util.LocalLogMixin):
    log = MagicMock()


def test_log():
    log = Logger()
    log.debug("Test debug")
    log.exception("Test exception")
    log.info("Test info")
    log.warning("Test warn")
    log.error("Test error")


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

    @util.retryable(retry_exceptions, tries=tries, delay=delay)
    async def count(x, y, z):
        assert x == y == z == 9
        nonlocal counter
        counter += 1
        if counter <= n:
            exc = exception()
            exc._counter = counter
            raise exc

    await count(9, 9, 9)
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
    ("message", "expected_key"),
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
    with pytest.raises(ValueError, match="Invalid install code length"):
        util.convert_install_code(b"")

    with pytest.raises(ValueError, match="Invalid install code CRC"):
        util.convert_install_code(b"\x11\x22\x33\x44\x55\x66\x77\x88\xff\xff")


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
    ("to_raise", "exception"),
    [(RuntimeError, None), (asyncio.TimeoutError, RuntimeError)],
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


@pytest.mark.parametrize(
    "plot",
    [
        r"""
            11  #########
            12  #################################################################
            13  ##################################################################
            14  ################################################################
            15  ##############
            16  ######################################################
            17  #########################
            18  ##########
            19  ###########
            20  ################
            21  ###########
            22  ###########
            23  #
            24  ##
           [25] #################
            26  ##
        """,
        r"""
            11  ##################
            12
            13
            14  ########
            15  ##################
            16  ########
            17
            18
            19  ########
            20  ##################
            21  ########
            22
            23
            24  ########
           [25] ##################
            26
        """,
        r"""
            11  ##################
            12  #
            13  #
            14  ########
            15  ##################
            16  ########
            17
            18
            19  ########
           [20] ##################
            21  ########
            22
            23
            24  ########
            25  ##################
            26  ########
        """,
    ],
)
def test_picking_optimal_channel(plot):
    expected_channel = int(plot.split("[")[1].split("]")[0])
    plot = plot.replace("[", " ").replace("]", " ")
    channel_energy = {
        int(line.split()[0]): line.count("#") for line in plot.strip().splitlines()
    }

    assert util.pick_optimal_channel(channel_energy) == expected_channel


def test_singleton():
    singleton = util.Singleton("NAME")

    assert str(singleton) == repr(singleton) == "<Singleton 'NAME'>"
    assert singleton == singleton  # noqa: PLR0124

    obj = {}
    obj[singleton] = 5
    assert obj[singleton] == 5


@pytest.mark.parametrize(
    ("input_relays", "expected_relays"),
    [
        ([0x0000, 0x0000, 0x0001, 0x0001, 0x0002], [0x0001, 0x0002]),
        ([0x0001, 0x0002], [0x0001, 0x0002]),
        ([], []),
        ([0x0000], []),
    ],
)
def test_relay_filtering(input_relays: list[int], expected_relays: list[int]):
    assert util.filter_relays(input_relays) == expected_relays


async def test_combine_concurrent_calls():
    class TestFuncs:
        def __init__(self):
            self.slow_calls = 0
            self.slow_error_calls = 0

        async def slow(self, n=None):
            await asyncio.sleep(0.1)
            self.slow_calls += 1
            return (self.slow_calls, n)

        async def slow_error(self, n=None):
            await asyncio.sleep(0.1)
            self.slow_error_calls += 1
            raise RuntimeError

        combined_slow = util.combine_concurrent_calls(slow)
        combined_slow_error = util.combine_concurrent_calls(slow_error)

    f = TestFuncs()

    assert f.slow_calls == 0

    await f.slow()
    assert f.slow_calls == 1

    await f.combined_slow()
    assert f.slow_calls == 2

    results = await asyncio.gather(*[f.combined_slow() for _ in range(5)])
    assert results == [(3, None)] * 5
    assert f.slow_calls == 3

    results = await asyncio.gather(*[f.combined_slow() for _ in range(5)])
    assert results == [(4, None)] * 5
    assert f.slow_calls == 4

    # Unique keyword arguments
    results = await asyncio.gather(*[f.combined_slow(n=i) for i in range(5)])
    assert results == [(5 + i, 0 + i) for i in range(5)]
    assert f.slow_calls == 9

    # Non-unique keyword arguments
    results = await asyncio.gather(*[f.combined_slow(i // 2) for i in range(5)])
    assert results == [(10, 0), (10, 0), (11, 1), (11, 1), (12, 2)]
    assert f.slow_calls == 12

    # Mixed keyword and non-keyword
    results = await asyncio.gather(
        f.combined_slow(0),
        f.combined_slow(n=0),
        f.combined_slow(1),
        f.combined_slow(n=1),
        f.combined_slow(n=1),
    )
    assert results == [(13, 0), (13, 0), (14, 1), (14, 1), (14, 1)]
    assert f.slow_calls == 14

    assert f.slow_error_calls == 0

    with pytest.raises(RuntimeError):
        await f.slow_error()

    assert f.slow_error_calls == 1

    for coro in asyncio.as_completed([f.combined_slow_error() for _ in range(5)]):
        with pytest.raises(RuntimeError):
            await coro

    assert f.slow_error_calls == 2


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_deprecated():
    @util.deprecated("This function is deprecated")
    def foo():
        return 1

    with pytest.deprecated_call():
        foo()

    class Bar:
        pass

    obj = util.deprecated_attrs({"foo": Bar})

    assert obj("foo") == Bar

    with pytest.raises(AttributeError):
        obj("baz")


async def test_async_iterate_in_chunks() -> None:
    def iterator(n: int) -> typing.Generator[int, None, None]:
        for i in range(n):
            time.sleep(0.1)
            yield i

    chunks = [c async for c in util.async_iterate_in_chunks(iterator(10), chunk_size=3)]
    assert chunks == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]


@pytest.mark.parametrize(
    ("code", "ieee", "link_key"),
    [
        # Atlantic Galapagos electric heater (core#155014)
        (
            "Z:22B78EFEFF16A720$I:B1817AFD64D8BB3A8F275C2117327AEC684B",
            EUI64.convert("20:A7:16:FF:FE:8E:B7:22"),  # reversed!
            util.convert_install_code(
                bytes.fromhex("B1817AFD64D8BB3A8F275C2117327AEC684B")
            ),
        ),
        # Inovelli, others
        (
            "Z:943469FFFE05CE55$I:FC5ECD1E8DFD3E0603E3689F8D0226BBF80B",
            EUI64.convert("94:34:69:FF:FE:05:CE:55"),
            util.convert_install_code(
                bytes.fromhex("FC5ECD1E8DFD3E0603E3689F8D0226BBF80B")
            ),
        ),
        # Muller-Light, Schneider, others
        (
            "000D6FFFFE63CCA0|58A4DD6123F38ECF22B17FDA0D95A43DED19",
            EUI64.convert("00:0D:6F:FF:FE:63:CC:A0"),
            util.convert_install_code(
                bytes.fromhex("58A4DD6123F38ECF22B17FDA0D95A43DED19")
            ),
        ),
        # Aqara
        (
            "G$M:69775$S:680S00003915$D:0000000017B2335C%Z$A:54EF44100006E7DF$I:3313A005E177A647FC7925620AB207C4BEF5",
            EUI64.convert("54:EF:44:10:00:06:E7:DF"),
            util.convert_install_code(
                bytes.fromhex("3313A005E177A647FC7925620AB207C4BEF5")
            ),
        ),
        # Somfy?
        (
            "Z:4CC206FFFE805E7A$I:560BCC1FF50E704B9BA93A5CA817C35E799F$D:202%B:4CC206805E7A$P:613727%M:1220$F:0024",
            EUI64.convert("4C:C2:06:FF:FE:80:5E:7A"),
            util.convert_install_code(
                bytes.fromhex("560BCC1FF50E704B9BA93A5CA817C35E799F")
            ),
        ),
        # Hue
        (
            "HUE:Z:2E5D2E5F401B82F1A45621A50B551F726101 M:001788010CE5C843 D:H2504 A:2266",
            EUI64.convert("00:17:88:01:0C:E5:C8:43"),
            util.convert_install_code(
                bytes.fromhex("2E5D2E5F401B82F1A45621A50B551F726101")
            ),
        ),
        # Bosch (install code)
        (
            "RB01SG0D8310182648007000000000000000000094DEB8FFFE41F6D6DLKA87710C3E5C332E5327EE532C3C310E5DFE0",
            EUI64.convert("94:DE:B8:FF:FE:41:F6:D6"),
            util.convert_install_code(
                bytes.fromhex("A87710C3E5C332E5327EE532C3C310E5DFE0")
            ),
        ),
        # Bosch (link key)
        (
            "RB01SG0D836591B3CC0010000000000000000000000D6F0017E0870CDLK999F98A7DFBCA6DD3955823AD9089631",
            EUI64.convert("00:0D:6F:00:17:E0:87:0C"),
            KeyData.convert("999F98A7DFBCA6DD3955823AD9089631"),
        ),
    ],
)
def test_qr_code_parsing(code: str, ieee: EUI64, link_key: KeyData) -> None:
    """Test install code QR parsing."""
    parsed_ieee, parsed_link_key = util.parse_install_code_qr(code)
    assert parsed_ieee == ieee
    assert parsed_link_key == link_key


def test_qr_code_parsing_failure() -> None:
    """Test install code QR parsing failure."""
    with pytest.raises(ValueError, match="Unknown QR code format: "):
        util.parse_install_code_qr("some invalid QR code")
