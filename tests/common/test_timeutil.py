from datetime import UTC, datetime, timedelta, timezone

import pytest

from common.timeutil import from_epoch, interval_start, to_epoch, utc_now


def test_interval_start_aligns_to_clock() -> None:
    base = to_epoch(datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC))
    assert interval_start(base) == base
    assert interval_start(base + 299) == base
    assert interval_start(base + 300) == base + 300


def test_replayed_interval_gets_same_key() -> None:
    t = 1_790_424_123
    assert interval_start(t) == interval_start(t + 1) == 1_790_424_000


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError):
        to_epoch(datetime(2026, 10, 6, 12, 0, 0))  # noqa: DTZ001 (the point of the test)


def test_non_utc_offset_converted() -> None:
    wat = timezone(timedelta(hours=1))
    assert to_epoch(datetime(2026, 10, 6, 13, 0, tzinfo=wat)) == to_epoch(
        datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    )


def test_from_epoch_requires_int() -> None:
    assert from_epoch(0).tzinfo is UTC
    with pytest.raises(TypeError):
        from_epoch(1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        from_epoch(True)


def test_utc_now_is_aware_utc_and_whole_seconds() -> None:
    now = utc_now()
    assert now.utcoffset() == timedelta(0)
    assert now.microsecond == 0
