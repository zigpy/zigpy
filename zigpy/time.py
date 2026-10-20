"""Timezone-aware values for the ZCL Time server."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, tzinfo

ZIGBEE_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
# ZCL reserves the all-ones value for unknown or invalid time attributes.
INVALID_TIME = 0xFFFFFFFF
MAX_TIME = INVALID_TIME - 1
# Shorter than any gap between two tzdata transitions, so no interval is skipped.
PROBE_STEP = 6 * 60 * 60


def zigbee_time(value: datetime) -> int:
    """Encode an instant without wrapping unrepresentable timestamps."""
    seconds = (value - ZIGBEE_EPOCH).total_seconds()
    return int(seconds) if 0 <= seconds <= MAX_TIME else INVALID_TIME


def _dst_shift(zone: tzinfo, seconds: int) -> int:
    local = (ZIGBEE_EPOCH + timedelta(seconds=seconds)).astimezone(zone)
    return int((local.dst() or timedelta(0)).total_seconds())


def _first_change(zone: tzinfo, lower: int, upper: int, shift: int) -> int:
    """Return the first second in (lower, upper] whose DST shift differs."""
    while upper - lower > 1:
        middle = (lower + upper) // 2
        if _dst_shift(zone, middle) == shift:
            lower = middle
        else:
            upper = middle
    return upper


def dst_intervals(zone: tzinfo, year: int) -> list[tuple[int, int, int]]:
    """Return half-open (start, end, shift) DST intervals around a UTC year.

    The window spans the previous year through the next, so the active or next
    DST season is always complete for any instant within `year`.
    """
    lower = zigbee_time(max(ZIGBEE_EPOCH, datetime(year - 1, 1, 1, tzinfo=UTC)))
    upper = zigbee_time(
        min(
            ZIGBEE_EPOCH + timedelta(seconds=MAX_TIME),
            datetime(year + 2, 1, 1, tzinfo=UTC),
        )
    )
    intervals = []
    start = probe = lower
    shift = _dst_shift(zone, lower)

    while probe < upper:
        following = min(probe + PROBE_STEP, upper)
        following_shift = _dst_shift(zone, following)
        if following_shift != shift:
            change = _first_change(zone, probe, following, shift)
            if shift:
                intervals.append((start, change, shift))
            start, shift = change, following_shift
        probe = following

    if shift:
        intervals.append((start, upper, shift))

    return intervals


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
    """Share timezone rules and DST intervals across all devices."""

    def __init__(self, zone: tzinfo | None = None) -> None:
        self.timezone = zone
        self._cache: tuple[tzinfo, int, list[tuple[int, int, int]]] | None = None

    def snapshot(self, now: datetime) -> TimeSnapshot:
        """Return the active DST interval, or the next one when inactive.

        Without an explicit timezone, preserve system-local clock values but
        do not claim knowledge of DST rules.
        """
        zone = self.timezone
        local = now.astimezone(zone)
        offset = int((local.utcoffset() or timedelta(0)).total_seconds())
        shift = int((local.dst() or timedelta(0)).total_seconds())
        time = zigbee_time(now)
        snapshot = TimeSnapshot(
            time=time,
            # TimeZone excludes DST; signed shifts also cover negative DST rules.
            time_zone=offset - shift,
            standard_time=zigbee_time(now + timedelta(seconds=offset - shift)),
            local_time=zigbee_time(now + timedelta(seconds=offset)),
        )
        if zone is None or time == INVALID_TIME:
            return snapshot

        year = now.astimezone(UTC).year
        cache = self._cache
        if cache is None or cache[0] is not zone or cache[1] != year:
            cache = self._cache = (zone, year, dst_intervals(zone, year))

        for start, end, interval_shift in cache[2]:
            if end > time:
                return replace(
                    snapshot,
                    dst_start=start,
                    # ZCL uses DstStart <= Time <= DstEnd, unlike half-open intervals.
                    dst_end=end - 1,
                    dst_shift=interval_shift,
                    authoritative=True,
                )

        return replace(snapshot, authoritative=True)
