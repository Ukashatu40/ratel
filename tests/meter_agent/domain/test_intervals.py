"""Unit tests for W2-14: alignment, delta, reset, zero-skip.

No lab, no network, no database.
"""

from __future__ import annotations

import pytest

from services.meter_agent.domain.intervals import (
    INTERVAL_SECONDS,
    build_record,
    increase,
    interval_bounds,
)
from services.meter_agent.domain.records import Increase, Reading

# A known aligned boundary: 2026-10-13 00:00:00 UTC.
BOUNDARY = 1791820800


def _reading(up: int, down: int, at: int = BOUNDARY, ip: str = "10.45.0.5") -> Reading:
    return Reading(ue_ip=ip, bytes_up_total=up, bytes_down_total=down, read_at=at)


class TestAlignment:
    @pytest.mark.parametrize("offset", [0, 1, 299, 300, 301, 599, 600])
    def test_readings_land_in_the_right_interval(self, offset: int) -> None:
        start, end = interval_bounds(BOUNDARY + offset)
        assert start == BOUNDARY + (offset // INTERVAL_SECONDS) * INTERVAL_SECONDS
        assert end == start + INTERVAL_SECONDS

    def test_just_before_and_just_after_a_boundary(self) -> None:
        # 299, 300, 301 seconds past a boundary: 300 belongs to the next.
        assert interval_bounds(BOUNDARY + 299)[0] == BOUNDARY
        assert interval_bounds(BOUNDARY + 300)[0] == BOUNDARY + INTERVAL_SECONDS
        assert interval_bounds(BOUNDARY + 301)[0] == BOUNDARY + INTERVAL_SECONDS

    def test_period_is_300_seconds(self) -> None:
        start, end = interval_bounds(BOUNDARY + 7)
        assert end - start == INTERVAL_SECONDS


class TestIncrease:
    def test_normal_case(self) -> None:
        prev = _reading(up=1000, down=2000)
        curr = _reading(up=1500, down=2500)
        result = increase(prev, curr)
        assert result == Increase(bytes_up=500, bytes_down=500)

    def test_equal_readings_give_zero(self) -> None:
        prev = _reading(up=1000, down=2000)
        curr = _reading(up=1000, down=2000)
        assert increase(prev, curr) == Increase(bytes_up=0, bytes_down=0)

    def test_reset_counts_from_zero(self) -> None:
        # The UPF or host restarted: the total went backwards.
        prev = _reading(up=5000, down=9000)
        curr = _reading(up=100, down=200)
        assert increase(prev, curr) == Increase(bytes_up=100, bytes_down=200)

    def test_reset_on_one_direction_only(self) -> None:
        prev = _reading(up=5000, down=1000)
        curr = _reading(up=100, down=1500)
        # up reset, down did not.
        assert increase(prev, curr) == Increase(bytes_up=100, bytes_down=500)

    def test_first_reading_is_baseline_and_counts_zero(self) -> None:
        # The ticket's proposal, pending confirmation.
        assert increase(None, _reading(up=1000, down=2000)) == Increase(bytes_up=0, bytes_down=0)

    def test_increase_is_never_negative(self) -> None:
        # Property-style over many random pairs.
        import random

        rng = random.Random(0)  # noqa: S311 - not for security, just a test fixture
        for _ in range(1000):
            prev = _reading(up=rng.randint(0, 10**12), down=rng.randint(0, 10**12))
            curr = _reading(up=rng.randint(0, 10**12), down=rng.randint(0, 10**12))
            result = increase(prev, curr)
            assert result.bytes_up >= 0
            assert result.bytes_down >= 0


class TestBuildRecord:
    def test_zero_byte_interval_produces_no_record(self) -> None:
        assert build_record("621000000000001", BOUNDARY, Increase(0, 0)) is None

    def test_nonzero_interval_produces_a_record(self) -> None:
        record = build_record("621000000000001", BOUNDARY + 10, Increase(500, 700))
        assert record is not None
        assert record.imsi == "621000000000001"
        assert record.period_start == BOUNDARY
        assert record.period_end == BOUNDARY + INTERVAL_SECONDS
        assert record.bytes_up == 500
        assert record.bytes_down == 700

    def test_all_numbers_are_integers(self) -> None:
        record = build_record("621000000000001", BOUNDARY, Increase(1, 2))
        assert record is not None
        for value in (
            record.period_start,
            record.period_end,
            record.bytes_up,
            record.bytes_down,
        ):
            assert isinstance(value, int)


class TestReplayStability:
    def test_same_interval_produces_the_same_key_and_values(self) -> None:
        # A replayed interval must produce the same key and the same values.
        first = build_record("621000000000001", BOUNDARY + 10, Increase(500, 700))
        replay = build_record("621000000000001", BOUNDARY + 250, Increase(500, 700))
        assert first is not None and replay is not None
        assert first.key == replay.key
        assert first == replay
