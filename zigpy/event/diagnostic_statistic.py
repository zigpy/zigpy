"""Diagnostics statistics and counters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from .event_base import EventBase

T = TypeVar("T", int, float)


@dataclass(frozen=True, kw_only=True)
class DiagnosticStatisticChangeEvent:
    event_type: str = "diagnostic_statistics_change"

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

        self.emit(
            DiagnosticStatisticChangeEvent.event_type,
            DiagnosticStatisticChangeEvent(
                name=self.name,
                old_value=old_value,
                new_value=self.value,
            ),
        )

    def increment(self, amount: T = 1) -> None:
        """Increment the counter by a given amount, useful mostly for integers."""
        self.update(self.value + amount)
