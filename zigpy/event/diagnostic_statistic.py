"""Diagnostics statistics and counters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeVar

from .event_base import EventBase

T = TypeVar("T", int, float)


# TODO: once we drop 3.9, this can be moved into the dataclass with `kw_only=True`
DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE: str = "diagnostic_statistics_change"


@dataclass(frozen=True)
class DiagnosticStatisticChangeEvent:
    event_type: Literal[DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE]

    name: str
    old_value: T
    new_value: T


class DiagnosticStatistic(EventBase):
    """Object representing a numerical statistic that changes."""

    def __init__(self, name: str, value: T) -> None:
        """Initialize a diagnostic statistic."""
        super().__init__()
        self.name = name
        self.value: T = value

    def update(self, new_value: T) -> None:
        """Update with a new value."""
        old_value = self.value
        self.value = new_value

        if old_value == new_value:
            return

        self.emit(
            DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE,
            DiagnosticStatisticChangeEvent(
                event_type=DIAGNOSTICS_STATISTIC_CHANGE_EVENT_TYPE,
                name=self.name,
                old_value=old_value,
                new_value=self.value,
            ),
        )

    def increment(self, amount: T = 1) -> None:
        """Increment the counter by a given amount, useful mostly for integers."""
        self.update(self.value + amount)
