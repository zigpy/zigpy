"""Timezone-aware values for the ZCL Time server."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, timezone, tzinfo

ZIGBEE_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
# ZCL reserves the all-ones value for unknown or invalid time attributes.
INVALID_TIME = 0xFFFFFFFF
MAX_TIME = INVALID_TIME - 1


def zigbee_time(value: datetime) -> int:
    """Encode an instant without wrapping unrepresentable timestamps."""
    seconds = (value - ZIGBEE_EPOCH).total_seconds()
    return int(seconds) if 0 <= seconds <= MAX_TIME else INVALID_TIME


@dataclass(frozen=True)
class TimeSnapshot:
    """Consistent values for one Read Attributes response."""

    time: int
    time_zone: int
    standard_time: int
    local_time: int
    dst_start: int = INVALID_TIME
    dst_end: int = INVALID_TIME
    dst_shift: int = 0
    authoritative: bool = False


class TimeService:
    """Share timezone rules and transition discovery across all devices."""

    def __init__(self, zone: tzinfo | None = None) -> None:
        self._timezone = zone
        # Cache entries contain (timezone object, UTC year, offset periods).
        # Each period is (inclusive start, exclusive end, UTC offset, DST shift).
        self._cache: (
            tuple[tzinfo, int, list[tuple[datetime, datetime, int, int]]] | None
        ) = None
        self._generation = 0
        # Readers with the same timezone, year, and generation share discovery.
        self._pending: dict[
            tuple[int, int, int],
            asyncio.Future[list[tuple[datetime, datetime, int, int]]],
        ] = {}

    @property
    def timezone(self) -> tzinfo | None:
        return self._timezone

    @timezone.setter
    def timezone(self, zone: tzinfo | None) -> None:
        self._timezone = zone
        self.clear_cache()

    def clear_cache(self) -> None:
        """Invalidate rules after replacing the configured timezone."""
        self._cache = None
        # In-flight readers may finish, but must not repopulate this cache.
        self._generation += 1

    @staticmethod
    def _offsets(instant: datetime, zone: tzinfo) -> tuple[int, int]:
        local = instant.astimezone(zone)
        return (
            int((local.utcoffset() or timedelta(0)).total_seconds()),
            int((local.dst() or timedelta(0)).total_seconds()),
        )

    @classmethod
    def _scan_periods(
        cls, zone: tzinfo, year: int, span: int = 1
    ) -> list[tuple[datetime, datetime, int, int]]:
        """Find constant-offset periods using UTC probes and integer bisection.

        Six-hour probes cover IANA timezone transitions, including midnight
        changes. Bisection finds the first changed second, not a fractional
        approximation of it. Both the UTC offset and signed DST shift matter.
        """
        # Search in UTC to avoid ambiguous or nonexistent local clock times.
        # The upper bound is exclusive, so MAX_TIME remains representable.
        lower = datetime(max(ZIGBEE_EPOCH.year, year - span), 1, 1, tzinfo=UTC)
        upper = min(
            ZIGBEE_EPOCH + timedelta(seconds=INVALID_TIME),
            datetime(year + span + 1, 1, 1, tzinfo=UTC),
        )
        period_start = probe = lower
        offset, shift = cls._offsets(probe, zone)
        periods = []

        while probe < upper:
            following = min(probe + timedelta(hours=6), upper)
            following_offsets = cls._offsets(following, zone)
            if following_offsets != (offset, shift):
                left, right = probe, following
                # Keep integer-second bounds so rounding cannot move a transition.
                while (right - left).total_seconds() > 1:
                    middle = left + timedelta(
                        seconds=int((right - left).total_seconds()) // 2
                    )
                    if cls._offsets(middle, zone) == (offset, shift):
                        left = middle
                    else:
                        right = middle
                periods.append((period_start, right, offset, shift))
                period_start = right
                offset, shift = following_offsets
            probe = following

        periods.append((period_start, upper, offset, shift))
        return periods

    def snapshot(self, now: datetime) -> TimeSnapshot:
        """Return the active DST interval, or the next one when inactive.

        Without an explicit timezone, preserve system-local clock values but
        do not claim knowledge of future DST rules.
        """
        zone = self.timezone
        now = now.astimezone(UTC)
        if not self._needs_rules(now, zone):
            return self._snapshot(now, zone, [])
        assert zone is not None
        periods = self._cached_periods(now, zone)
        if periods is None:
            periods = self._discover_periods(zone, now)
            self._cache = (zone, now.year, periods)
        return self._snapshot(now, zone, periods)

    async def async_snapshot(self, now: datetime) -> TimeSnapshot:
        """Offload only uncached rule discovery, keeping cache writes on-loop."""
        zone = self.timezone
        now = now.astimezone(UTC)
        # Fixed-offset zones and cached rules need no executor round trip.
        if not self._needs_rules(now, zone):
            return self._snapshot(now, zone, [])
        assert zone is not None
        generation = self._generation
        key = (id(zone), now.year, generation)
        periods = self._cached_periods(now, zone)
        while periods is None:
            future = self._pending.get(key)
            if future is None:
                # The worker only returns periods; all shared state stays on-loop.
                future = asyncio.get_running_loop().run_in_executor(
                    None, self._discover_periods, zone, now
                )
                self._pending[key] = future

                def remove_pending(done):
                    # Do not remove a newer discovery registered under this key.
                    if self._pending.get(key) is done:
                        del self._pending[key]

                future.add_done_callback(remove_pending)
            # Cancelling one device's read must not cancel other readers' work.
            discovered = await asyncio.shield(future)
            # Another reader may need a different interval within the same year.
            if self._periods_complete(discovered, zone, now):
                periods = discovered
                # A timezone assignment during discovery invalidates publication.
                if generation == self._generation:
                    self._cache = (zone, now.year, periods)
        return self._snapshot(now, zone, periods)

    @staticmethod
    def _needs_rules(now: datetime, zone: tzinfo | None) -> bool:
        return (
            zone is not None
            and not isinstance(zone, timezone)
            and zigbee_time(now) != INVALID_TIME
        )

    def _cached_periods(
        self, now: datetime, zone: tzinfo
    ) -> list[tuple[datetime, datetime, int, int]] | None:
        cache = self._cache
        if (
            cache is not None
            # A replacement ZoneInfo can carry updated rules under the same name.
            and cache[0] is zone
            and cache[1] == now.year
            and self._periods_complete(cache[2], zone, now)
        ):
            return cache[2]
        return None

    @classmethod
    def _select_period(
        cls,
        periods: list[tuple[datetime, datetime, int, int]],
        zone: tzinfo,
        now: datetime,
    ) -> tuple[datetime, datetime, int, int] | None:
        offset, shift = cls._offsets(now, zone)
        # Periods are chronological: choose the active DST interval or the next.
        # Match standard offsets so political timezone changes are not DST shifts.
        for start, end, period_offset, period_shift in periods:
            if (
                end > now
                and period_shift != 0
                and period_offset - period_shift == offset - shift
            ):
                return start, end, period_offset, period_shift
        return None

    @classmethod
    def _periods_complete(
        cls,
        periods: list[tuple[datetime, datetime, int, int]],
        zone: tzinfo,
        now: datetime,
    ) -> bool:
        period = cls._select_period(periods, zone, now)
        if period is None:
            return True
        start, end, _, _ = period
        # A scan-window edge is not a discovered transition. Only protocol limits
        # can truncate an advertised interval without requiring a wider search.
        return (start != periods[0][0] or start == ZIGBEE_EPOCH) and (
            end != periods[-1][1]
            or end == ZIGBEE_EPOCH + timedelta(seconds=INVALID_TIME)
        )

    @classmethod
    def _discover_periods(
        cls, zone: tzinfo, now: datetime
    ) -> list[tuple[datetime, datetime, int, int]]:
        span = 1
        periods = cls._scan_periods(zone, now.year, span)
        # Expand for cross-year or long-lived DST until both boundaries are known.
        while not cls._periods_complete(periods, zone, now):
            span *= 2
            periods = cls._scan_periods(zone, now.year, span)
        return periods

    def _snapshot(
        self,
        now: datetime,
        zone: tzinfo | None,
        periods: list[tuple[datetime, datetime, int, int]],
    ) -> TimeSnapshot:
        now = now.astimezone(UTC)
        local = now.astimezone(zone)
        offset = int((local.utcoffset() or timedelta(0)).total_seconds())
        shift = int((local.dst() or timedelta(0)).total_seconds())
        # TimeZone excludes DST; signed shifts also cover negative DST rules.
        standard_offset = offset - shift
        values = TimeSnapshot(
            time=zigbee_time(now),
            time_zone=standard_offset,
            standard_time=zigbee_time(now + timedelta(seconds=standard_offset)),
            local_time=zigbee_time(now + timedelta(seconds=offset)),
        )
        if zone is None or values.time == INVALID_TIME:
            # System-local time alone cannot establish authoritative DST rules.
            return values

        if isinstance(zone, timezone):
            return replace(values, authoritative=True)

        period = self._select_period(periods, zone, now)
        if period is None:
            return replace(values, authoritative=shift == 0)
        start, end, _, period_shift = period
        return replace(
            values,
            dst_start=zigbee_time(start),
            # ZCL uses DstStart <= Time <= DstEnd, unlike our half-open periods.
            dst_end=min(MAX_TIME, int((end - ZIGBEE_EPOCH).total_seconds()) - 1),
            dst_shift=period_shift,
            authoritative=True,
        )
