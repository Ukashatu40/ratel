"""The SQL repository's mechanics on SQLite: the wallet and the entry move together, a duplicate is
a duplicate and nothing else is, and the caller's transaction decides what is kept.

Triggers, BIGINT, concurrency and the migration are PostgreSQL-only and are proved in
test_sql_postgres_integration.py.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss_money.domain.entries import EntryKind, Posting, new_posting
from app.bss_money.models.ledger import LedgerEntry, Wallet
from app.bss_money.repositories.ports import DuplicateEntry
from app.bss_money.repositories.sql import SqlLedgerRepository
from app.bss_money.services.ledger import ReferenceConflict, post_entry
from app.bss_money.services.wallet_check import check_wallets
from tests.app.bss_money.sqlite_database import sqlite_engine


def _count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(LedgerEntry)).scalar_one()


def test_the_first_posting_creates_the_wallet_and_moves_it(session: Session) -> None:
    repo = SqlLedgerRepository(session)
    entry, balance = repo.append(new_posting(1, 50_000, "top_up", "pay-1"))
    assert balance == 50_000 and repo.balance(1) == 50_000
    assert entry.entry_id > 0 and entry.created_at is not None
    assert repo.find(1, "top_up", "pay-1") == entry


def test_a_line_without_a_wallet_has_no_balance(session: Session) -> None:
    assert SqlLedgerRepository(session).balance(404) is None


def test_a_duplicate_is_reported_as_a_duplicate_and_changes_nothing(session: Session) -> None:
    repo = SqlLedgerRepository(session)
    repo.append(new_posting(1, 50_000, "top_up", "pay-1"))
    with pytest.raises(DuplicateEntry):
        repo.append(new_posting(1, 50_000, "top_up", "pay-1"))
    assert repo.balance(1) == 50_000 and _count(session) == 1


def test_a_failure_that_is_not_a_duplicate_is_not_called_one(session: Session) -> None:
    # A zero amount breaks the table's CHECK. It must surface as it is, never as a replay.
    bypassed = Posting(line_id=1, amount_kobo=0, kind=EntryKind.TOP_UP, reference="r")
    with pytest.raises(IntegrityError) as refused:
        SqlLedgerRepository(session).append(bypassed)
    assert "amount_not_zero" in str(refused.value)


def test_a_refused_posting_leaves_the_transaction_usable(session: Session) -> None:
    repo = SqlLedgerRepository(session)
    repo.append(new_posting(1, 100, "top_up", "r1"))
    with pytest.raises(DuplicateEntry):
        repo.append(new_posting(1, 100, "top_up", "r1"))
    _, balance = repo.append(new_posting(1, 5, "top_up", "r2"))  # the same transaction carries on
    assert balance == 105


def test_nothing_is_kept_unless_the_caller_commits(session: Session) -> None:
    # A purchase and its VAT are posted together or not at all.
    repo = SqlLedgerRepository(session)
    repo.append(new_posting(1, -1_000, "purchase", "buy-1"))
    repo.append(new_posting(1, -75, "vat", "buy-1"))
    session.rollback()
    assert _count(session) == 0 and repo.balance(1) is None


def test_the_service_replays_and_refuses_a_changed_amount_through_the_real_sql(
    session: Session,
) -> None:
    repo = SqlLedgerRepository(session)
    first = post_entry(repo, new_posting(1, 50_000, "top_up", "pay-1"))
    again = post_entry(repo, new_posting(1, 50_000, "top_up", "pay-1"))
    assert again.replayed and again.entry_id == first.entry_id and again.balance_kobo == 50_000
    with pytest.raises(ReferenceConflict):
        post_entry(repo, new_posting(1, 60_000, "top_up", "pay-1"))
    assert repo.balance(1) == 50_000 and _count(session) == 1


def test_mismatches_finds_a_corrupted_balance(session: Session) -> None:
    repo = SqlLedgerRepository(session)
    repo.append(new_posting(1, 1_000, "top_up", "a"))
    repo.append(new_posting(2, 2_000, "top_up", "a"))
    session.execute(update(Wallet).where(Wallet.line_id == 2).values(balance_kobo=2_001))
    assert [(m.line_id, m.wallet_kobo, m.ledger_kobo) for m in repo.mismatches()] == [
        (2, 2_001, 2_000)
    ]


def test_mismatches_finds_a_wallet_with_money_and_no_entries(session: Session) -> None:
    session.add(Wallet(line_id=5, balance_kobo=10))
    session.flush()
    found = SqlLedgerRepository(session).mismatches()
    assert [(m.line_id, m.wallet_kobo, m.ledger_kobo) for m in found] == [(5, 10, 0)]


def test_an_empty_wallet_with_no_entries_is_fine(session: Session) -> None:
    session.add(Wallet(line_id=5, balance_kobo=0))
    session.flush()
    assert SqlLedgerRepository(session).mismatches() == []


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
        repo = SqlLedgerRepository(s)
        for index, (line, amount) in enumerate(movements):
            post_entry(repo, new_posting(line, amount, "correction", f"ref-{index}"))
        assert check_wallets(repo) == []
    engine.dispose()
