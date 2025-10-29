"""Provide Event base classes for zigpy."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import dataclasses
from inspect import iscoroutinefunction
import logging
import sys
from typing import Any

_LOGGER = logging.getLogger(__package__)


@dataclasses.dataclass(
    frozen=True, **({"slots": True} if sys.version_info >= (3, 10) else {})
)
class EventListener:
    """Listener for an event."""

    callback: Callable
    with_context: bool


class EventBase:
    """Base class for event handling and emitting objects."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize event base."""
        super().__init__(*args, **kwargs)
        self._listeners: dict[str, list[EventListener]] = {}
        self._event_tasks: list[asyncio.Task] = []
        self._global_listeners: list[EventListener] = []

    def on_event(  # pylint: disable=invalid-name
        self, event_name: str, callback: Callable, with_context: bool = False
    ) -> Callable:
        """Register an event callback."""
        listener = EventListener(callback=callback, with_context=with_context)

        listeners: list = self._listeners.setdefault(event_name, [])
        listeners.append(listener)

        def unsubscribe() -> None:
            """Unsubscribe listeners."""
            if listener in listeners:
                listeners.remove(listener)

        return unsubscribe

    def on_all_events(  # pylint: disable=invalid-name
        self, callback: Callable, with_context: bool = False
    ) -> Callable:
        """Register a callback for all events."""
        listener = EventListener(callback=callback, with_context=with_context)
        self._global_listeners.append(listener)

        def unsubscribe() -> None:
            """Unsubscribe listeners."""
            if listener in self._global_listeners:
                self._global_listeners.remove(listener)

        return unsubscribe

    def once(
        self, event_name: str, callback: Callable, with_context: bool = False
    ) -> Callable:
        """Listen for an event exactly once."""
        if iscoroutinefunction(callback):

            async def async_event_listener(*args, **kwargs) -> None:
                unsub()
                task = asyncio.create_task(callback(*args, **kwargs))
                self._event_tasks.append(task)
                task.add_done_callback(self._event_tasks.remove)

            unsub = self.on_event(
                event_name, async_event_listener, with_context=with_context
            )
            return unsub  # noqa: RET504

        def event_listener(*args, **kwargs) -> None:
            unsub()
            callback(*args, **kwargs)

        unsub = self.on_event(event_name, event_listener, with_context=with_context)
        return unsub  # noqa: RET504

    def emit(self, event_name: str, data=None) -> None:
        """Run all callbacks for an event."""
        listeners = [*self._listeners.get(event_name, []), *self._global_listeners]
        _LOGGER.debug(
            "Emitting event %s with data %r (%d listeners)",
            event_name,
            data,
            len(listeners),
        )

        for listener in listeners:
            if listener.with_context:
                call = listener.callback(event_name, data)
            else:
                call = listener.callback(data)

            if iscoroutinefunction(listener.callback):
                task = asyncio.create_task(call)
                self._event_tasks.append(task)
                task.add_done_callback(self._event_tasks.remove)

    def _handle_event_protocol(self, event) -> None:
        """Process an event based on event protocol."""
        _LOGGER.debug(
            "(%s) handling event protocol for event: %s", self.__class__.__name__, event
        )
        handler = getattr(self, f"handle_{event.event.replace(' ', '_')}", None)
        if handler is None:
            _LOGGER.warning("Received unknown event: %s", event)
            return
        if iscoroutinefunction(handler):
            task = asyncio.create_task(handler(event))
            self._event_tasks.append(task)
            task.add_done_callback(self._event_tasks.remove)
        else:
            handler(event)
