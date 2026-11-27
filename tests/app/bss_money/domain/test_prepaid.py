"""The prepaid rules for calls and texts (ADR 0013): pure, no database."""

from __future__ import annotations

import pytest

from app.bss_money.domain.prepaid import (
    MAX_CALL_SECONDS,
    MIN_CALL_SECONDS,
    CallReason,
    SmsOutcome,
    affordable_seconds,
    cost_of,
    digits,
    in_own_range,
    is_free_number,
    limited_call,
    parse_free_numbers,
    parse_number_prefixes,
)


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("tel:+2348000010010", "2348000010010"),
        ("sip:+2348000010010@ims.mnc001.mcc621.3gppnetwork.org;user=phone", "2348000010010"),
        ("SIP:112@ims.example", "112"),
        ("080 0001 0010", "08000010010"),
        ("555", "555"),
        ("", ""),
    ],
)
def test_digits_reads_a_dialled_number_or_a_uri(number: str, expected: str) -> None:
    assert digits(number) == expected


def test_free_numbers_are_matched_on_their_digits() -> None:
    free = parse_free_numbers(" 112, 199 ,, tel:0700123")
    assert free == frozenset({"112", "199", "0700123"})
    assert is_free_number("sip:112@ims.example", free)
    assert not is_free_number("1120", free)
    assert parse_free_numbers("") == frozenset()


@pytest.mark.parametrize(
    ("available", "rate", "seconds"),
    [
        (1_000, 1_000, 60),  # N10 at N10 a minute: one minute
        (1_016, 1_000, 60),  # part of a second is not given
        (1_017, 1_000, 61),
        (0, 1_000, 0),
        (-500, 1_000, 0),  # a negative balance buys nothing
        (10_000_000, 0, MAX_CALL_SECONDS),  # a free rate is still capped
        (10**12, 1_000, MAX_CALL_SECONDS),
    ],
)
def test_affordable_seconds(available: int, rate: int, seconds: int) -> None:
    assert affordable_seconds(available, rate) == seconds


def test_what_is_held_for_a_call_never_exceeds_what_is_available() -> None:
    for available in range(0, 5_000, 7):
        for rate in (1, 333, 1_000, 2_150):
            seconds = affordable_seconds(available, rate)
            assert cost_of(seconds, rate) <= available


def test_cost_rounds_up_to_a_kobo_like_the_call_charge() -> None:
    assert cost_of(1, 1_000) == 17
    assert cost_of(60, 1_000) == 1_000
    assert cost_of(0, 1_000) == 0
    assert cost_of(30, 0) == 0


def test_too_little_airtime_refuses_the_call() -> None:
    rate = 1_200  # 20 kobo a second
    decision, reserve = limited_call(20 * (MIN_CALL_SECONDS - 1), rate)
    assert not decision.allowed
    assert decision.reason is CallReason.INSUFFICIENT_BALANCE
    assert reserve == 0


def test_enough_airtime_limits_the_call_and_holds_its_cost() -> None:
    decision, reserve = limited_call(5_000, 1_000)  # N50 at N10 a minute
    assert decision.allowed
    assert decision.reason is CallReason.LIMITED
    assert decision.max_seconds == 300
    assert reserve == 5_000


@pytest.mark.parametrize(
    ("outcome", "send"),
    [
        (SmsOutcome.CHARGED, True),
        (SmsOutcome.FREE_SELF_CARE, True),
        (SmsOutcome.FREE_CHARGING_OFF, True),
        (SmsOutcome.NOT_BILLED, True),
        (SmsOutcome.REFUSED_BALANCE, False),
        (SmsOutcome.REFUSED_OFF_NET, False),
        (SmsOutcome.REFUSED_NOT_IN_SERVICE, False),
    ],
)
def test_only_refused_texts_are_not_sent(outcome: SmsOutcome, send: bool) -> None:
    assert outcome.send is send


def test_own_ranges_are_digit_prefixes() -> None:
    own = parse_number_prefixes(" 2342064730, +23491 ,, ")
    assert own == ("2342064730", "23491")
    assert in_own_range("2342064730433", own)
    assert in_own_range("2349100000000", own)
    assert not in_own_range("2348031234567", own)
    assert not in_own_range("2342064730433", ())
