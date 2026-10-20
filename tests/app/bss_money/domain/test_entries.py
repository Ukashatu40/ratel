"""The ledger rules: whole kobo only, no zero, a closed list of kinds, and no overflow."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.bss_money.domain.entries import (
    BIGINT_MAX,
    REFERENCE_MAX_LENGTH,
    EntryKind,
    InvalidPosting,
    apply_to_balance,
    new_posting,
)


def test_a_valid_credit_and_a_valid_debit() -> None:
    credit = new_posting(7, 50_000, "top_up", "pay-001")
    debit = new_posting(7, -20_000, "purchase", "buy-001")
    assert (credit.amount_kobo, credit.kind) == (50_000, EntryKind.TOP_UP)
    assert (debit.amount_kobo, debit.kind) == (-20_000, EntryKind.PURCHASE)


@pytest.mark.parametrize("amount", [10.0, 10.5, "100", None, True, False])
def test_money_must_be_a_whole_number_of_kobo(amount: object) -> None:
    with pytest.raises(InvalidPosting, match="whole number"):
        new_posting(1, amount, "top_up", "r")  # type: ignore[arg-type]


def test_a_zero_movement_is_refused() -> None:
    with pytest.raises(InvalidPosting, match="zero"):
        new_posting(1, 0, "top_up", "r")


@pytest.mark.parametrize("amount", [BIGINT_MAX + 1, -(BIGINT_MAX + 1), 10**30])
def test_an_amount_outside_bigint_is_refused(amount: int) -> None:
    with pytest.raises(InvalidPosting, match="range"):
        new_posting(1, amount, "top_up", "r")


def test_the_largest_amounts_are_accepted() -> None:
    assert new_posting(1, BIGINT_MAX, "top_up", "r").amount_kobo == BIGINT_MAX
    assert new_posting(1, -BIGINT_MAX, "purchase", "r").amount_kobo == -BIGINT_MAX


@pytest.mark.parametrize("line_id", [0, -1, 1.5, "1", None, True])
def test_the_line_must_be_a_positive_whole_number(line_id: object) -> None:
    with pytest.raises(InvalidPosting, match="line_id"):
        new_posting(line_id, 100, "top_up", "r")  # type: ignore[arg-type]


@pytest.mark.parametrize("kind", ["", "TOP_UP", "refund", "gift", None])
def test_an_unknown_kind_is_refused(kind: object) -> None:
    with pytest.raises(InvalidPosting, match="kind"):
        new_posting(1, 100, kind, "r")  # type: ignore[arg-type]


@pytest.mark.parametrize("reference", ["", "   ", None, 12345])
def test_a_missing_reference_is_refused(reference: object) -> None:
    with pytest.raises(InvalidPosting, match="reference"):
        new_posting(1, 100, "top_up", reference)  # type: ignore[arg-type]


def test_an_overlong_reference_is_refused() -> None:
    assert new_posting(1, 100, "top_up", "x" * REFERENCE_MAX_LENGTH)
    with pytest.raises(InvalidPosting, match="at most"):
        new_posting(1, 100, "top_up", "x" * (REFERENCE_MAX_LENGTH + 1))


def test_the_error_never_repeats_the_reference_back() -> None:
    # A reference could be mistaken for something sensitive; a refusal must not echo it.
    with pytest.raises(InvalidPosting) as caught:
        new_posting(1, 100, "not-a-kind", "ref-should-not-appear")
    assert "ref-should-not-appear" not in str(caught.value)


def test_the_balance_cannot_leave_the_database_range() -> None:
    assert apply_to_balance(BIGINT_MAX - 5, 5) == BIGINT_MAX
    with pytest.raises(InvalidPosting, match="range"):
        apply_to_balance(BIGINT_MAX, 1)
    with pytest.raises(InvalidPosting, match="range"):
        apply_to_balance(-BIGINT_MAX, -1)


@given(st.lists(st.integers(min_value=-(10**12), max_value=10**12).filter(bool), max_size=60))
def test_folding_postings_gives_their_sum(amounts: list[int]) -> None:
    balance = 0
    for amount in amounts:
        balance = apply_to_balance(balance, new_posting(1, amount, "correction", "r").amount_kobo)
    assert balance == sum(amounts)
