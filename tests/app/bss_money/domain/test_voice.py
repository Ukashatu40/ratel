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


def test_the_call_summary_fits_one_plain_sms() -> None:
    from app.bss_money.domain.voice import call_summary_text

    text = call_summary_text(
        dialled="2348031234567", seconds=135, cost_kobo=2_250, uncovered_kobo=0, balance_kobo=47_750
    )
    assert (
        text == "Last call to 08031234567: 2m 15s, cost N22.50. Balance N477.50. Text MENU to 647."
    )
    worst = call_summary_text(
        dialled="+44 20 7946 0000 1234",
        seconds=10 * 3600 + 59 * 60 + 59,
        cost_kobo=999_999_999,
        uncovered_kobo=999_999_999,
        balance_kobo=0,
    )
    assert worst.endswith("unpaid. Balance N0.00. Text BUY 500 to 647 to top up.")
    assert len(worst) <= 160 and worst.isascii()


def test_money_and_time_read_as_customers_expect() -> None:
    from app.bss_money.domain.voice import dialled_text, duration_text, naira_text

    assert [naira_text(k) for k in (0, 5, 2_000, 123_456_789)] == [
        "N0.00",
        "N0.05",
        "N20.00",
        "N1,234,567.89",
    ]
    assert [duration_text(s) for s in (0, 45, 60, 135, 3_723)] == [
        "0s",
        "45s",
        "1m 00s",
        "2m 15s",
        "1h 02m 03s",
    ]
    assert dialled_text("08031234567") == "08031234567"
    assert dialled_text("2348031234567") == "08031234567"
    assert dialled_text("") == "unknown"
