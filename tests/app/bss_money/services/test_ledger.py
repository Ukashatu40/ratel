"""Posting money: the service rules, against an in-memory ledger. No database."""

from __future__ import annotations

import logging

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.bss_money.domain.entries import BIGINT_MAX, InvalidPosting, new_posting
from app.bss_money.services.ledger import PostingResult, ReferenceConflict, post_entry
from app.bss_money.services.wallet_check import check_wallets
from tests.app.bss_money.fakes import InMemoryLedgerRepository


def _post(
    ledger: InMemoryLedgerRepository, line: int, amount: int, kind: str, ref: str
) -> PostingResult:
    return post_entry(ledger, new_posting(line, amount, kind, ref))


def test_the_first_posting_moves_the_wallet() -> None:
    ledger = InMemoryLedgerRepository()
    result = _post(ledger, 1, 50_000, "top_up", "pay-1")
    assert (result.balance_kobo, result.replayed) == (50_000, False)
    assert ledger.balance(1) == 50_000 and result.entry_id > 0


def test_credits_and_debits_add_up() -> None:
    ledger = InMemoryLedgerRepository()
    _post(ledger, 1, 100_000, "top_up", "pay-1")
    _post(ledger, 1, -30_000, "purchase", "buy-1")
    last = _post(ledger, 1, -2_250, "vat", "buy-1")
    assert last.balance_kobo == 67_750


def test_each_line_has_its_own_wallet() -> None:
    ledger = InMemoryLedgerRepository()
    _post(ledger, 1, 100, "top_up", "a")
    _post(ledger, 2, 900, "top_up", "a")
    assert (ledger.balance(1), ledger.balance(2)) == (100, 900)


def test_posting_the_same_event_again_changes_nothing() -> None:
    ledger = InMemoryLedgerRepository()
    first = _post(ledger, 1, 50_000, "top_up", "pay-1")
    again = _post(ledger, 1, 50_000, "top_up", "pay-1")
    assert again.replayed is True
    assert again.entry_id == first.entry_id
    assert again.balance_kobo == 50_000
    assert len(ledger.entries) == 1


def test_the_same_reference_with_another_amount_is_refused_and_changes_nothing() -> None:
    ledger = InMemoryLedgerRepository()
    _post(ledger, 1, 50_000, "top_up", "pay-1")
    with pytest.raises(ReferenceConflict):
        _post(ledger, 1, 60_000, "top_up", "pay-1")
    assert ledger.balance(1) == 50_000 and len(ledger.entries) == 1


def test_a_refused_posting_does_not_stop_the_next_one() -> None:
    ledger = InMemoryLedgerRepository()
    _post(ledger, 1, 100, "top_up", "r1")
    with pytest.raises(ReferenceConflict):
        _post(ledger, 1, 999, "top_up", "r1")
    assert _post(ledger, 1, 5, "top_up", "r2").balance_kobo == 105


def test_a_balance_that_would_overflow_is_refused_and_changes_nothing() -> None:
    ledger = InMemoryLedgerRepository()
    _post(ledger, 1, BIGINT_MAX, "top_up", "huge")
    with pytest.raises(InvalidPosting, match="range"):
        _post(ledger, 1, 1, "top_up", "one-more")
    assert ledger.balance(1) == BIGINT_MAX and len(ledger.entries) == 1


def test_the_log_records_the_entry_without_its_reference(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    _post(InMemoryLedgerRepository(), 3, 700, "top_up", "secret-looking-reference")
    events = [
        r.__dict__ for r in caplog.records if r.__dict__.get("event") == "ledger.entry.posted"
    ]
    assert len(events) == 1 and events[0]["line_id"] == 3 and events[0]["amount_kobo"] == 700
    assert "secret-looking-reference" not in caplog.text


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=3),
            st.integers(min_value=-(10**9), max_value=10**9).filter(bool),
        ),
        max_size=40,
    )
)
def test_every_wallet_equals_the_sum_of_its_entries_after_any_sequence(
    movements: list[tuple[int, int]],
) -> None:
    ledger = InMemoryLedgerRepository()
    for index, (line, amount) in enumerate(movements):
        _post(ledger, line, amount, "correction", f"ref-{index}")
    assert check_wallets(ledger) == []
    for line, _ in movements:
        assert ledger.balance(line) == sum(
            e.amount_kobo for e in ledger.entries if e.line_id == line
        )
