"""Event tests."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from zigpy.event import EventBase, suppress_events
from zigpy.event.event_base import EventListener


class EventGenerator(EventBase):
    """Event generator for testing."""


class Event:
    """Event class for testing."""

    event = "test"
    event_type = "testing"


def test_event_base_unsubs():
    """Test event base class."""
    event = EventGenerator()
    assert not event._event_listeners
    assert not event._global_listeners

    callback = MagicMock()

    unsub = event.on_event("test", callback)
    assert event._event_listeners == {
        "test": [EventListener(callback=callback, with_context=False)]
    }
    unsub()
    assert event._event_listeners == {"test": []}

    unsub = event.on_all_events(callback)
    assert event._global_listeners == [
        EventListener(callback=callback, with_context=False)
    ]
    unsub()
    assert not event._global_listeners

    unsub = event.once("test", callback)
    assert "test" in event._event_listeners
    assert len(event._event_listeners["test"]) == 1
    unsub()
    assert event._event_listeners == {"test": []}


def test_event_base_emit():
    """Test event base class."""
    event = EventGenerator()
    assert not event._event_listeners
    assert not event._global_listeners

    callback = MagicMock()

    event.once("test", callback)
    event.emit("test")
    assert callback.called

    callback.reset_mock()
    event.emit("test")
    assert not callback.called

    unsub = event.on_event("test", callback)
    event.emit("test")
    assert callback.called
    unsub()

    callback.reset_mock()
    unsub = event.on_all_events(callback)
    event.emit("test")
    assert callback.called
    unsub()

    assert "test" in event._event_listeners
    assert event._event_listeners == {"test": []}
    assert not event._global_listeners


def test_event_base_emit_data():
    """Test event base class."""
    event = EventGenerator()
    assert not event._event_listeners
    assert not event._global_listeners

    callback = MagicMock()

    event.once("test", callback)
    event.emit("test", "data")
    assert callback.called
    assert callback.call_args[0] == ("data",)

    callback.reset_mock()
    event.emit("test", "data")
    assert not callback.called

    unsub = event.on_event("test", callback)
    event.emit("test", "data")
    assert callback.called
    assert callback.call_args[0] == ("data",)
    unsub()

    callback.reset_mock()
    unsub = event.on_all_events(callback)
    event.emit("test", "data")
    assert callback.called
    assert callback.call_args[0] == ("data",)
    unsub()

    assert "test" in event._event_listeners
    assert event._event_listeners == {"test": []}
    assert not event._global_listeners


async def test_event_base_emit_coro():
    """Test event base class."""
    event = EventGenerator()
    assert not event._event_listeners
    assert not event._global_listeners

    callback = AsyncMock()

    event.once("test", callback)
    event.emit("test", "data")

    await asyncio.gather(*event._event_tasks)

    assert callback.await_count == 1
    assert callback.mock_calls == [call("data")]
    assert not event._event_tasks

    callback.reset_mock()

    unsub = event.on_event("test", callback)
    event.emit("test", "data")

    await asyncio.gather(*event._event_tasks)

    assert callback.await_count == 1
    assert callback.mock_calls == [call("data")]
    unsub()
    assert not event._event_tasks

    callback.reset_mock()

    unsub = event.on_all_events(callback)
    event.emit("test", "data")

    await asyncio.gather(*event._event_tasks)

    assert callback.await_count == 1
    assert callback.mock_calls == [call("data")]
    unsub()
    assert not event._event_tasks

    test_event = Event()
    event.on_event(test_event.event, event._handle_event_protocol)
    event.handle_test = AsyncMock()

    event.emit(test_event.event, test_event)

    await asyncio.gather(*event._event_tasks)

    assert event.handle_test.await_count == 1
    assert event.handle_test.mock_calls == [call(test_event)]
    assert not event._event_tasks


async def test_event_emit_with_context():
    """Test event emitting with context."""

    event = EventGenerator()
    async_callback = AsyncMock()
    sync_callback = MagicMock()

    event.once("test", sync_callback, with_context=True)
    event.once("test", async_callback, with_context=True)
    event.emit("test", "data")

    await asyncio.gather(*event._event_tasks)

    sync_callback.assert_called_once_with("test", "data")
    async_callback.assert_awaited_once_with("test", "data")


def test_handle_event_protocol():
    """Test event base class."""

    event_handler = EventGenerator()
    event_handler.handle_test = MagicMock()
    event_handler.on_event("test", event_handler._handle_event_protocol)

    event = Event()
    event_handler.emit(event.event, event)

    assert event_handler.handle_test.called
    assert event_handler.handle_test.call_args[0] == (event,)


def test_suppress_events() -> None:
    """Test suppress_events context manager."""
    emitter = EventGenerator()
    received = []

    emitter.on_event("test", lambda data: received.append(data))

    emitter.emit("test", "before")

    with suppress_events():
        emitter.emit("test", "during")

        with pytest.raises(RuntimeError):  # noqa: PT012
            with suppress_events():
                emitter.emit("test", "during (nested)")
                raise RuntimeError()

        emitter.emit("test", "during (nested, after)")

    emitter.emit("test", "after")

    assert received == ["before", "after"]


def test_handle_event_protocol_no_event(caplog: pytest.LogCaptureFixture):
    """Test event base class."""

    event_handler = EventGenerator()
    event_handler.on_event("not_test", event_handler._handle_event_protocol)
    event = Event()
    event_handler.emit("not_test", event)

    assert "Received unknown event:" in caplog.text


def test_emit_sync_listener_error_does_not_stop_others(
    caplog: pytest.LogCaptureFixture,
):
    """A raising sync listener is contained instead of aborting the emit."""
    event = EventGenerator()
    raising_callback = MagicMock(side_effect=RuntimeError("boom"))
    later_callback = MagicMock()
    global_callback = MagicMock()

    event.on_event("test", raising_callback)
    event.on_event("test", later_callback)
    event.on_all_events(global_callback)

    event.emit("test", "data")

    assert raising_callback.mock_calls == [call("data")]
    # The listeners registered after the raising one still run, and the error
    # does not propagate back to the caller of `emit()`.
    assert later_callback.mock_calls == [call("data")]
    assert global_callback.mock_calls == [call("data")]
    assert "Error handling event test in listener" in caplog.text
    assert "RuntimeError: boom" in caplog.text


async def test_emit_async_listener_error_is_logged(caplog: pytest.LogCaptureFixture):
    """A raising async listener is logged rather than lost with its task."""
    event = EventGenerator()
    raising_callback = AsyncMock(side_effect=RuntimeError("boom"))
    later_callback = AsyncMock()

    event.on_event("test", raising_callback)
    event.on_event("test", later_callback)

    event.emit("test", "data")
    await asyncio.gather(*list(event._event_tasks), return_exceptions=True)

    assert raising_callback.await_count == 1
    assert later_callback.await_count == 1
    assert not event._event_tasks
    assert "Error handling event test in listener" in caplog.text
    assert "RuntimeError: boom" in caplog.text


async def test_handle_event_protocol_async_handler_error_is_logged(
    caplog: pytest.LogCaptureFixture,
):
    """An async event-protocol handler that raises is logged, not swallowed."""
    event_handler = EventGenerator()
    event_handler.handle_test = AsyncMock(side_effect=RuntimeError("boom"))
    event_handler.on_event("test", event_handler._handle_event_protocol)

    event = Event()
    event_handler.emit(event.event, event)
    await asyncio.gather(*list(event_handler._event_tasks), return_exceptions=True)

    assert event_handler.handle_test.await_count == 1
    assert not event_handler._event_tasks
    assert "Error handling event test in listener" in caplog.text
    assert "RuntimeError: boom" in caplog.text


async def test_emit_async_listener_cancelled_is_not_logged(
    caplog: pytest.LogCaptureFixture,
):
    """A cancelled listener task is dropped quietly, not reported as an error."""
    started = asyncio.Event()

    async def never_finishes(data):
        started.set()
        await asyncio.sleep(3600)

    event = EventGenerator()
    event.on_event("test", never_finishes)

    event.emit("test", "data")
    await started.wait()

    (task,) = event._event_tasks
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert task.cancelled()
    assert not event._event_tasks
    # Nothing at all should be reported: neither our own error log, nor asyncio
    # complaining that the done callback itself blew up on `task.exception()`.
    assert [
        record for record in caplog.records if record.levelno >= logging.ERROR
    ] == []
