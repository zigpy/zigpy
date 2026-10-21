"""Timezone-aware values for the ZCL Time server."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, tzinfo
import functools

import zigpy.types as t

# Shorter than any gap between two tzdata transitions, so no interval is skipped.
PROBE_STEP = 6 * 60 * 60


def _offset(zone: tzinfo, seconds: int) -> tuple[int, bool]:
    """Return the UTC offset and DST flag, both stored exactly in tzdata."""
    local = t.UTCTime(seconds).to_datetime().astimezone(zone)
    return int((local.utcoffset() or timedelta(0)).total_seconds()), bool(local.dst())


def _first_change(
    zone: tzinfo, lower: int, upper: int, offset: tuple[int, bool]
) -> int:
    """Return the first second in (lower, upper] whose offset differs."""
    while upper - lower > 1:
        middle = (lower + upper) // 2
        if _offset(zone, middle) == offset:
            lower = middle
        else:
            upper = middle
    return upper


@functools.lru_cache(maxsize=1)
def utc_periods(zone: tzinfo, year: int) -> list[tuple[int, int, int, bool]]:
    """Return half-open (start, end, offset, is_dst) periods around a UTC year.

    The window spans the previous year through the next, so the active or next
    DST season and its neighbouring standard periods are always complete for
    any instant within `year`. Bounds are clamped to the representable range.
    """
    lower = int(
        t.UTCTime.from_datetime(
            max(t.UTCTime(0).to_datetime(), datetime(year - 1, 1, 1, tzinfo=UTC))
        )
    )
    upper = int(
        t.UTCTime.from_datetime(
            min(
                t.UTCTime(t.UTCTime.INVALID - 1).to_datetime(),
                datetime(year + 2, 1, 1, tzinfo=UTC),
            )
        )
    )
    periods = []
    start = probe = lower
    offset = _offset(zone, lower)

    while probe < upper:
        following = min(probe + PROBE_STEP, upper)
        following_offset = _offset(zone, following)
        if following_offset != offset:
            change = _first_change(zone, probe, following, offset)
            periods.append((start, change, *offset))
            start, offset = change, following_offset
        probe = following

    periods.append((start, upper, *offset))
    return periods


def _dst_interval(
    periods: list[tuple[int, int, int, bool]], time: int
) -> tuple[int, int, int] | None:
    """Return the active or next DST interval as (start, end, shift).

    The shift is relative to the standard period on the same side as the
    read, so Time + TimeZone + DstShift equals local time at that instant.

    ZCL has a single TimeZone, so it cannot describe a standard offset that
    changes at a DST boundary. Alberta moves to permanent UTC-6 when its 2026
    DST season ends: a read during that season sees the following period at
    the same offset and reports TimeZone -6 with no shift, while a read before
    March reports TimeZone -7 with a one-hour shift. Both are correct at the
    time of the read, and a device that re-reads after the change stays right.
    """
    for index, (start, end, offset, is_dst) in enumerate(periods):
        if not is_dst or end <= time:
            continue
        neighbour = index - 1 if time < start else index + 1
        if not 0 <= neighbour < len(periods):
            return None
        return start, end, offset - periods[neighbour][2]
    return None


@dataclass(frozen=True)
class TimeSnapshot:
    """Consistent values for one Read Attributes response."""

    time: t.UTCTime
    time_zone: t.int32s
    standard_time: t.StandardTime
    local_time: t.LocalTime
    dst_start: t.UTCTime = t.UTCTime(t.UTCTime.INVALID)
    dst_end: t.UTCTime = t.UTCTime(t.UTCTime.INVALID)
    dst_shift: t.int32s = t.int32s(0)
    authoritative: bool = False

    @classmethod
    def compute(cls, zone: tzinfo | None, now: datetime) -> TimeSnapshot:
        """Compute all Time cluster values for one instant.

        The DST attributes describe the active interval, or the next one when
        inactive. Without an explicit timezone, preserve system-local clock
        values but do not claim knowledge of DST rules.
        """
        time = t.UTCTime.from_datetime(now)
        offset = int((now.astimezone(zone).utcoffset() or timedelta(0)).total_seconds())
        interval = None
        if zone is not None and time != t.UTCTime.INVALID:
            periods = utc_periods(zone, now.astimezone(UTC).year)
            interval = _dst_interval(periods, int(time))
        # TimeZone excludes the DST shift while it applies.
        shift = interval[2] if interval is not None and interval[0] <= time else 0
        values = cls(
            time=time,
            time_zone=t.int32s(offset - shift),
            standard_time=t.StandardTime.from_datetime(
                now + timedelta(seconds=offset - shift)
            ),
            local_time=t.LocalTime.from_datetime(now + timedelta(seconds=offset)),
            authoritative=zone is not None and time != t.UTCTime.INVALID,
        )
        if interval is None:
            return values
        start, end, interval_shift = interval
        return replace(
            values,
            dst_start=t.UTCTime(start),
            # ZCL uses DstStart <= Time <= DstEnd, unlike half-open periods.
            dst_end=t.UTCTime(end - 1),
            dst_shift=t.int32s(interval_shift),
        )
