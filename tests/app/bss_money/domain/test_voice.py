"""What a call costs: answered time, per second, rounded up to a kobo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.bss_money.domain.voice import answered_seconds, call_cost, national_msisdn

T0 = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def test_only_answered_time_counts_and_part_seconds_round_up() -> None:
    assert answered_seconds(None, T0 + timedelta(minutes=5)) == 0
    assert answered_seconds(T0, T0 + timedelta(seconds=61, milliseconds=200)) == 62
    assert answered_seconds(T0, T0) == 0


@pytest.mark.parametrize(
    ("seconds", "rate", "cost"),
    [
        (60, 1_000, 1_000),  # a minute at 10 naira
        (1, 1_000, 17),  # 16.67 kobo, rounded up
        (90, 2_000, 3_000),
        (0, 2_000, 0),
        (59, 0, 0),
    ],
)
def test_the_cost_is_per_second_and_never_loses_a_kobo(seconds: int, rate: int, cost: int) -> None:
    result = call_cost(seconds, rate, on_net=True)
    assert result.cost_kobo == cost
    assert result.on_net is True


def test_negative_values_are_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        call_cost(-1, 1_000, on_net=False)


@pytest.mark.parametrize(
    ("number", "national"),
    [
        ("2348000010010", "2348000010010"),
        ("+2348000010010", "2348000010010"),
        ("08000010010", "2348000010010"),
        ("*123#", None),
        ("647", None),
        ("447700900123", None),  # not Nigerian
        ("23480000100", None),  # too short
    ],
)
def test_numbers_are_read_in_the_234_form(number: str, national: str | None) -> None:
    assert national_msisdn(number) == national
