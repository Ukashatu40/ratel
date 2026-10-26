"""Card numbers, PINs with their Luhn digit, and the states a card moves through."""

from __future__ import annotations

import pytest

from app.bss_money.domain.vouchers import (
    InvalidVoucherTransition,
    VoucherState,
    check_transition,
    is_card_number,
    is_luhn_valid,
    is_pin,
    luhn_check_digit,
    new_card_number,
    new_pin,
)

S = VoucherState


# Published Luhn test numbers (Wikipedia's 7992739871 and the card networks' own test cards), not
# values worked out by the code under test.
@pytest.mark.parametrize(
    ("body", "digit"),
    [
        ("7992739871", "3"),
        ("4992739871", "6"),
        ("411111111111111", "1"),
        ("550000000000000", "4"),
        ("37828224631000", "5"),
    ],
)
def test_the_check_digit_of_known_numbers(body: str, digit: str) -> None:
    assert luhn_check_digit(body) == digit
    assert is_luhn_valid(body + digit)


@pytest.mark.parametrize(
    "number", ["79927398710", "79927398714", "12345678901231", "1", "", "abcd"]
)
def test_numbers_that_fail_the_check(number: str) -> None:
    assert not is_luhn_valid(number)


def test_every_wrong_check_digit_is_refused_and_every_single_typo_is_caught() -> None:
    body = "4539148803436467"
    right = luhn_check_digit(body)
    assert [d for d in "0123456789" if is_luhn_valid(body + d)] == [right]
    pin = new_pin()
    for position in range(len(pin)):
        for wrong in "0123456789":
            if wrong != pin[position]:
                assert not is_luhn_valid(pin[:position] + wrong + pin[position + 1 :])


def test_swapping_two_neighbouring_digits_is_caught_except_09_and_90() -> None:
    pin = "12345678901231"  # build a valid one
    pin = pin[:-1] + luhn_check_digit(pin[:-1])
    for i in range(len(pin) - 1):
        swapped = pin[:i] + pin[i + 1] + pin[i] + pin[i + 2 :]
        if {pin[i], pin[i + 1]} != {"0", "9"} and swapped != pin:
            assert not is_luhn_valid(swapped)


def test_a_new_pin_is_13_digits_and_a_check_digit_and_always_valid() -> None:
    for _ in range(200):
        pin = new_pin()
        assert len(pin) == 14
        assert pin.isdigit()
        assert is_pin(pin)


def test_new_card_numbers_are_20_digits_and_differ() -> None:
    numbers = {new_card_number() for _ in range(200)}
    assert len(numbers) == 200
    assert all(is_card_number(n) for n in numbers)


@pytest.mark.parametrize(
    "value", ["", "1" * 19, "1" * 21, "1" * 19 + "x", "\uff11" * 20, " " + "1" * 19]
)
def test_things_that_are_not_card_numbers(value: str) -> None:
    assert not is_card_number(value)


@pytest.mark.parametrize("value", ["", "1" * 13, "1" * 15, "abcdefghijklmn", "00000000000001"])
def test_things_that_are_not_pins(value: str) -> None:
    assert not is_pin(value)


MOVES = [
    (S.REQUESTED, S.APPROVED),
    (S.APPROVED, S.SENT_TO_PRINTER),
    (S.SENT_TO_PRINTER, S.IN_STOCK),
    (S.IN_STOCK, S.ON_SALE),
    (S.ON_SALE, S.USED),
    (S.ON_SALE, S.EXPIRED),
    (S.IN_STOCK, S.EXPIRED),
    *[
        (state, S.LOCKED)
        for state in (S.REQUESTED, S.APPROVED, S.SENT_TO_PRINTER, S.IN_STOCK, S.ON_SALE)
    ],
]


@pytest.mark.parametrize(("current", "target"), MOVES)
def test_the_moves_a_card_may_make(current: VoucherState, target: VoucherState) -> None:
    check_transition(current, target)


def test_every_other_move_is_refused() -> None:
    allowed = set(MOVES)
    for current in VoucherState:
        for target in VoucherState:
            if (current, target) not in allowed:
                with pytest.raises(InvalidVoucherTransition):
                    check_transition(current, target)


def test_a_used_expired_or_locked_card_goes_nowhere() -> None:
    for final in (S.USED, S.EXPIRED, S.LOCKED):
        for target in VoucherState:
            with pytest.raises(InvalidVoucherTransition):
                check_transition(final, target)


def test_a_card_cannot_skip_the_printer_or_be_sold_before_it_is_in_stock() -> None:
    for skipped in (S.SENT_TO_PRINTER, S.IN_STOCK, S.ON_SALE, S.USED):
        with pytest.raises(InvalidVoucherTransition):
            check_transition(S.REQUESTED, skipped)
    with pytest.raises(InvalidVoucherTransition):
        check_transition(S.SENT_TO_PRINTER, S.ON_SALE)
