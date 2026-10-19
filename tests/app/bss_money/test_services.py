"""Posting money and checking the books, on SQLite. The PostgreSQL guarantees are in the
integration test next to this file."""

from __future__ import annotations

import logging

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.bss_money import repositories as repo
from app.bss_money.domain import new_posting
from app.bss_money.models import LedgerEntry, Wallet
from app.bss_money.services import ReferenceConflict, check_wallets, post_entry
from tests.app.bss_money.conftest import sqlite_engine


def _post(session: Session, line: int, amount: int, kind: str, ref: str):  # type: ignore[no-untyped-def]
    return post_entry(session, new_posting(line, amount, kind, ref))


def _ledger_sum(session: Session, line: int) -> int:
    total = session.execute(
        select(func.coalesce(func.sum(LedgerEntry.amount_kobo), 0)).where(
            LedgerEntry.line_id == line
        )
    ).scalar_one()
    return int(total)


def test_the_first_posting_creates_the_wallet_and_moves_it(session: Session) -> None:
    result = _post(session, 1, 50_000, "top_up", "pay-1")
    assert (result.balance_kobo, result.replayed) == (50_000, False)
    assert repo.wallet_balance(session, 1) == 50_000
    assert result.entry_id > 0 and result.created_at is not None


def test_credits_and_debits_add_up(session: Session) -> None:
    _post(session, 1, 100_000, "top_up", "pay-1")
    _post(session, 1, -30_000, "purchase", "buy-1")
    last = _post(session, 1, -2_250, "vat", "buy-1")
    assert last.balance_kobo == 67_750
    assert _ledger_sum(session, 1) == 67_750


def test_each_line_has_its_own_wallet(session: Session) -> None:
    _post(session, 1, 100, "top_up", "a")
    _post(session, 2, 900, "top_up", "a")
    assert (repo.wallet_balance(session, 1), repo.wallet_balance(session, 2)) == (100, 900)


def test_posting_the_same_event_again_changes_nothing(session: Session) -> None:
    first = _post(session, 1, 50_000, "top_up", "pay-1")
    again = _post(session, 1, 50_000, "top_up", "pay-1")
    assert again.replayed is True
    assert again.entry_id == first.entry_id
    assert again.balance_kobo == 50_000
    assert session.execute(select(func.count()).select_from(LedgerEntry)).scalar_one() == 1


def test_the_same_reference_with_another_amount_is_refused_and_changes_nothing(
    session: Session,
) -> None:
    _post(session, 1, 50_000, "top_up", "pay-1")
    with pytest.raises(ReferenceConflict):
        _post(session, 1, 60_000, "top_up", "pay-1")
    assert repo.wallet_balance(session, 1) == 50_000
    assert _ledger_sum(session, 1) == 50_000


def test_a_refused_posting_leaves_the_transaction_usable(session: Session) -> None:
    _post(session, 1, 100, "top_up", "r1")
    with pytest.raises(ReferenceConflict):
        _post(session, 1, 999, "top_up", "r1")
    later = _post(session, 1, 5, "top_up", "r2")  # the same transaction carries on
    assert later.balance_kobo == 105


def test_nothing_is_kept_unless_the_caller_commits(session: Session) -> None:
    # A purchase and its VAT are posted together or not at all.
    _post(session, 1, -1_000, "purchase", "buy-1")
    _post(session, 1, -75, "vat", "buy-1")
    session.rollback()
    assert session.execute(select(func.count()).select_from(LedgerEntry)).scalar_one() == 0
    assert repo.wallet_balance(session, 1) is None


def test_the_log_records_the_entry_without_a_reference(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    engine = sqlite_engine()
    with Session(engine) as s:
        _post(s, 3, 700, "top_up", "secret-looking-reference")
    posted = [
        r.__dict__ for r in caplog.records if r.__dict__.get("event") == "ledger.entry.posted"
    ]
    assert len(posted) == 1 and posted[0]["line_id"] == 3 and posted[0]["amount_kobo"] == 700
    assert "secret-looking-reference" not in caplog.text


@settings(max_examples=40, deadline=None)
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
    engine = sqlite_engine()
    with Session(engine) as s:
        for index, (line, amount) in enumerate(movements):
            _post(s, line, amount, "correction", f"ref-{index}")
        for line in {line for line, _ in movements}:
            assert repo.wallet_balance(s, line) == _ledger_sum(s, line)
        assert check_wallets(s) == []
    engine.dispose()


# --- the nightly check can fail ----------------------------------------------------------------


def test_the_check_is_quiet_when_the_books_balance(session: Session) -> None:
    _post(session, 1, 100, "top_up", "a")
    _post(session, 2, 200, "top_up", "a")
    assert check_wallets(session) == []


def test_the_check_reports_a_deliberately_corrupted_balance(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    _post(session, 1, 1_000, "top_up", "a")
    _post(session, 2, 2_000, "top_up", "a")
    session.execute(update(Wallet).where(Wallet.line_id == 2).values(balance_kobo=2_001))
    caplog.set_level(logging.ERROR)
    mismatches = check_wallets(session)
    assert [(m.line_id, m.wallet_kobo, m.ledger_kobo) for m in mismatches] == [(2, 2_001, 2_000)]
    events = [
        r.__dict__ for r in caplog.records if r.__dict__.get("event") == "ledger.wallet_mismatch"
    ]
    assert len(events) == 1 and events[0]["line_id"] == 2


def test_the_check_reports_a_wallet_with_money_but_no_entries(session: Session) -> None:
    session.add(Wallet(line_id=5, balance_kobo=10))
    session.flush()
    assert [(m.line_id, m.wallet_kobo, m.ledger_kobo) for m in check_wallets(session)] == [
        (5, 10, 0)
    ]


def test_an_empty_wallet_with_no_entries_is_fine(session: Session) -> None:
    session.add(Wallet(line_id=5, balance_kobo=0))
    session.flush()
    assert check_wallets(session) == []
