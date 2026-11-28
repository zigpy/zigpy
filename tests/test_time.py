from datetime import UTC, datetime, timedelta, timezone
import time
from zoneinfo import ZoneInfo

import pytest

from zigpy.time import _offset, utc_periods
import zigpy.types as t


@pytest.mark.parametrize(
    "seconds",
    [0, 1, t.UTCTime.INVALID - 1, t.UTCTime.INVALID, True, 1.5, "123", t.UTCTime(123)],
)
@pytest.mark.parametrize("zone", [UTC, ZoneInfo("Europe/Berlin"), None])
def test_offset_input_conversion(zone, seconds):
    local = t.UTCTime(seconds).to_datetime().astimezone(zone)
    assert _offset(zone, seconds) == (
        int((local.utcoffset() or timedelta(0)).total_seconds()),
        bool(local.dst()),
    )


@pytest.mark.parametrize("seconds", [-1, t.UTCTime.INVALID + 1, "invalid"])
def test_offset_invalid_input(seconds):
    with pytest.raises(ValueError):
        _offset(UTC, seconds)


@pytest.mark.parametrize(
    ("seconds", "expected"), [(1.5, 1), (-1.5, -1), (0.5, 0), (-0.5, 0)]
)
def test_offset_fractional_timezone(seconds, expected):
    assert _offset(timezone(timedelta(seconds=seconds)), 0) == (expected, False)


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="Requires time.tzset")
def test_utc_periods_leap_second_timezone(monkeypatch):
    zone = ZoneInfo("Europe/Berlin")
    transition = int(t.UTCTime.from_datetime(datetime(2026, 3, 29, 1, tzinfo=UTC)))

    try:
        with monkeypatch.context() as context:
            context.setenv("TZ", "right/UTC")
            time.tzset()
            if time.gmtime(946684800).tm_sec == 0:
                pytest.skip("Requires leap-second-aware system tzdata")

            utc_periods.cache_clear()
            assert _offset(zone, transition - 1) == (3600, False)
            assert _offset(zone, transition) == (7200, True)
            assert _offset(zone, transition + 1) == (7200, True)
            periods = utc_periods(zone, 2026)
            assert any(
                start == transition and offset == 7200 and is_dst
                for start, end, offset, is_dst in periods
            )
    finally:
        time.tzset()
        utc_periods.cache_clear()
