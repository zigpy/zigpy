"""Timezone-aware values for the ZCL Time server."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, tzinfo
import functools

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


def _offset(zone: tzinfo, seconds: int) -> tuple[int, bool]:
    """Return the UTC offset and DST flag, both stored exactly in tzdata."""
    local = (ZIGBEE_EPOCH + timedelta(seconds=seconds)).astimezone(zone)
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
    any instant within `year`.
    """
    lower = zigbee_time(max(ZIGBEE_EPOCH, datetime(year - 1, 1, 1, tzinfo=UTC)))
    upper = zigbee_time(
        min(
            ZIGBEE_EPOCH + timedelta(seconds=MAX_TIME),
            datetime(year + 2, 1, 1, tzinfo=UTC),
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

    time: int
    time_zone: int
    standard_time: int
    local_time: int
    dst_start: int = INVALID_TIME
    dst_end: int = INVALID_TIME
    dst_shift: int = 0
    authoritative: bool = False

    @classmethod
    def compute(cls, zone: tzinfo | None, now: datetime) -> TimeSnapshot:
        """Compute all Time cluster values for one instant.

        The DST attributes describe the active interval, or the next one when
        inactive. Without an explicit timezone, preserve system-local clock
        values but do not claim knowledge of DST rules.
        """
        time = zigbee_time(now)
        offset = int((now.astimezone(zone).utcoffset() or timedelta(0)).total_seconds())
        interval = None
        if zone is not None and time != INVALID_TIME:
            interval = _dst_interval(utc_periods(zone, now.astimezone(UTC).year), time)
        # TimeZone excludes the DST shift while it applies.
        shift = interval[2] if interval is not None and interval[0] <= time else 0
        values = cls(
            time=time,
            time_zone=offset - shift,
            standard_time=zigbee_time(now + timedelta(seconds=offset - shift)),
            local_time=zigbee_time(now + timedelta(seconds=offset)),
            authoritative=zone is not None and time != INVALID_TIME,
        )
        if interval is None:
            return values
        start, end, interval_shift = interval
        return replace(
            values,
            dst_start=start,
            # ZCL uses DstStart <= Time <= DstEnd, unlike half-open periods.
            dst_end=end - 1,
            dst_shift=interval_shift,
        )
