"""Event tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from zigpy.event import EventBase
from zigpy.event.diagnostic_statistic import (
    DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE,
    DiagnosticStatistic,
    DiagnosticStatisticChangeEvent,
)
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
    assert not event._listeners
    assert not event._global_listeners

    callback = MagicMock()

    unsub = event.on_event("test", callback)
    assert event._listeners == {
        "test": [EventListener(callback=callback, with_context=False)]
    }
    unsub()
    assert event._listeners == {"test": []}

    unsub = event.on_all_events(callback)
    assert event._global_listeners == [
        EventListener(callback=callback, with_context=False)
    ]
    unsub()
    assert not event._global_listeners

    unsub = event.once("test", callback)
    assert "test" in event._listeners
    assert len(event._listeners["test"]) == 1
    unsub()
    assert event._listeners == {"test": []}


def test_event_base_emit():
    """Test event base class."""
    event = EventGenerator()
    assert not event._listeners
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

    assert "test" in event._listeners
    assert event._listeners == {"test": []}
    assert not event._global_listeners


def test_event_base_emit_data():
    """Test event base class."""
    event = EventGenerator()
    assert not event._listeners
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

    assert "test" in event._listeners
    assert event._listeners == {"test": []}
    assert not event._global_listeners


async def test_event_base_emit_coro():
    """Test event base class."""
    event = EventGenerator()
    assert not event._listeners
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


def test_handle_event_protocol_no_event(caplog: pytest.LogCaptureFixture):
    """Test event base class."""

    event_handler = EventGenerator()
    event_handler.on_event("not_test", event_handler._handle_event_protocol)
    event = Event()
    event_handler.emit("not_test", event)

    assert "Received unknown event:" in caplog.text


@pytest.mark.parametrize("initial_value", [0, 10, 0.0, 3.14])
def test_diagnostic_statistic_init(initial_value: float) -> None:
    """Test DiagnosticStatistic initialization."""
    stat = DiagnosticStatistic("test_stat", initial_value)
    assert stat.name == "test_stat"
    assert stat.value == initial_value


@pytest.mark.parametrize(
    ("initial_value", "new_value"),
    [
        (0, 5),
        (10, 15),
        (0.0, 1.5),
        (3.14, 2.71),
        (-5, 10),
        (100, 0),
    ],
)
def test_diagnostic_statistic_update(initial_value: float, new_value: float) -> None:
    """Test DiagnosticStatistic update method."""
    stat = DiagnosticStatistic("test_stat", initial_value)
    callback = MagicMock()

    stat.on_event(DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE, callback)
    stat.update(new_value)

    assert stat.value == new_value
    assert callback.mock_calls == [
        call(
            DiagnosticStatisticChangeEvent(
                event_type=DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE,
                name="test_stat",
                old_value=initial_value,
                new_value=new_value,
            )
        )
    ]


@pytest.mark.parametrize(
    ("initial_value", "increment_amount", "expected_value"),
    [
        (0, 1, 1),
        (10, 5, 15),
        (-5, 10, 5),
        (100, -20, 80),
        (3.5, 1.5, 5.0),
        (0.0, 2.71, 2.71),
    ],
)
def test_diagnostic_statistic_increment(
    initial_value: float,
    increment_amount: float,
    expected_value: float,
) -> None:
    """Test DiagnosticStatistic increment method."""
    stat = DiagnosticStatistic("test_stat", initial_value)
    callback = MagicMock()

    stat.on_event(DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE, callback)

    if increment_amount == 1:
        stat.increment()
    else:
        stat.increment(increment_amount)

    assert stat.value == expected_value
    assert callback.mock_calls == [
        call(
            DiagnosticStatisticChangeEvent(
                event_type=DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE,
                name="test_stat",
                old_value=initial_value,
                new_value=expected_value,
            )
        )
    ]


def test_diagnostic_statistic_increment_no_change() -> None:
    """Test DiagnosticStatistic increment with zero amount."""
    stat = DiagnosticStatistic("test_stat", 5)
    callback = MagicMock()

    stat.on_event(DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE, callback)
    stat.increment(0)

    assert stat.value == 5
    assert callback.mock_calls == []


def test_diagnostic_statistic_increment_default() -> None:
    """Test DiagnosticStatistic increment with default amount."""
    stat = DiagnosticStatistic("test_stat", 5)
    callback = MagicMock()

    stat.on_event(DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE, callback)
    stat.increment()

    assert stat.value == 6
    assert callback.mock_calls == [
        call(
            DiagnosticStatisticChangeEvent(
                event_type=DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE,
                name="test_stat",
                old_value=5,
                new_value=6,
            )
        )
    ]


def test_diagnostic_statistic_multiple_updates() -> None:
    """Test multiple updates to DiagnosticStatistic."""
    stat = DiagnosticStatistic("test_stat", 0)
    callback = MagicMock()

    stat.on_event(DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE, callback)

    stat.update(10)
    assert stat.value == 10

    stat.increment(5)
    assert stat.value == 15

    stat.update(0)
    assert stat.value == 0

    assert callback.mock_calls == [
        call(
            DiagnosticStatisticChangeEvent(
                event_type=DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE,
                name="test_stat",
                old_value=0,
                new_value=10,
            )
        ),
        call(
            DiagnosticStatisticChangeEvent(
                event_type=DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE,
                name="test_stat",
                old_value=10,
                new_value=15,
            )
        ),
        call(
            DiagnosticStatisticChangeEvent(
                event_type=DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE,
                name="test_stat",
                old_value=15,
                new_value=0,
            )
        ),
    ]


def test_diagnostic_statistic_no_change() -> None:
    """Test that DiagnosticStatistic when value doesn't change."""
    stat = DiagnosticStatistic("test_stat", 42)
    callback = MagicMock()

    stat.on_event(DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE, callback)
    stat.update(42)

    assert stat.value == 42
    assert callback.mock_calls == []
