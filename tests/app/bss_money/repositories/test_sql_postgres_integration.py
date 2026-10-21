"""The ledger's guarantees on a real PostgreSQL: the migration, the append-only triggers, BIGINT,
concurrent postings and overflow.

SQLite cannot show any of these. Run with RATEL_TEST_POSTGRES_URI set (see
tests/app/bss_money/postgres.py). Each test gets its own database, built by the real migration.
"""

from __future__ import annotations

import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss_money.domain.entries import BIGINT_MAX, InvalidPosting, new_posting
from app.bss_money.models.allowance import AllowanceBucket
from app.bss_money.models.ledger import LedgerEntry
from app.bss_money.repositories.sql import SqlLedgerRepository
from app.bss_money.services.ledger import post_entry
from app.bss_money.services.wallet_check import check_wallets
from app.db import Base
from tests.app.bss_money.postgres import Database

pytestmark = pytest.mark.integration

LEDGER_TABLES = {"wallet", "ledger_entry", "allowance_bucket"}


# --- the migration ------------------------------------------------------------------------------


def test_the_migration_applies_rolls_back_and_applies_again(db: Database) -> None:
    def tables() -> set[str]:
        with db.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
            return set(rows)

    assert LEDGER_TABLES <= tables()
    db.alembic("downgrade", "base")
    assert not LEDGER_TABLES & tables()
    assert (
        db.scalar("SELECT count(*) FROM pg_proc WHERE proname = 'ledger_entry_refuse_change'") == 0
    )
    db.alembic("upgrade", "head")
    assert LEDGER_TABLES <= tables()


def test_a_rollback_is_refused_while_the_ledger_holds_entries(db: Database) -> None:
    db.post(1, 5_000, "top_up", "pay-1")
    with pytest.raises(RuntimeError, match="refusing to drop a ledger"):
        db.alembic("downgrade", "base")
    assert db.scalar("SELECT count(*) FROM ledger_entry") == 1  # the money is still there


def test_the_migrated_schema_is_exactly_what_the_models_describe(db: Database) -> None:
    with db.engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_every_kobo_column_is_bigint_in_the_real_database(db: Database) -> None:
    with db.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name LIKE '%\\_kobo'"
            )
        ).all()
    assert {(r[0], r[1]) for r in rows} == {
        ("wallet", "balance_kobo"),
        ("ledger_entry", "amount_kobo"),
    }
    assert {r[2] for r in rows} == {"bigint"}


# --- append-only, enforced by the database ------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledger_entry SET amount_kobo = amount_kobo + 1",
        "UPDATE ledger_entry SET reference = 'edited'",
        "DELETE FROM ledger_entry",
        "TRUNCATE ledger_entry",
        "TRUNCATE ledger_entry, wallet CASCADE",
    ],
)
def test_the_database_refuses_to_change_or_remove_a_ledger_entry(
    db: Database, statement: str
) -> None:
    db.post(1, 5_000, "top_up", "pay-1")
    db.post(1, -1_200, "purchase", "buy-1")
    # Connected as the database's own administrator: the refusal holds even for the owner.
    with pytest.raises(IntegrityError, match="append-only"), db.engine.begin() as conn:
        conn.execute(text(statement))
    with db.engine.connect() as conn:
        rows = (
            conn.execute(select(LedgerEntry.amount_kobo).order_by(LedgerEntry.entry_id))
            .scalars()
            .all()
        )
    assert rows == [5_000, -1_200]  # every entry is exactly as it was


def test_a_correction_is_a_new_entry_and_the_old_one_stays(db: Database) -> None:
    db.post(1, 5_000, "top_up", "pay-1")
    fix = db.post(1, -5_000, "correction", "fix-pay-1")
    assert fix.balance_kobo == 0
    assert db.scalar("SELECT count(*) FROM ledger_entry") == 2


def test_a_wallet_with_entries_cannot_be_deleted(db: Database) -> None:
    db.post(1, 5_000, "top_up", "pay-1")
    with pytest.raises(IntegrityError), db.engine.begin() as conn:
        conn.execute(text("DELETE FROM wallet WHERE line_id = 1"))


def test_the_bucket_rules_hold_on_postgresql_too(db: Database) -> None:
    now = datetime(2026, 10, 19, tzinfo=UTC)
    bucket = AllowanceBucket(
        line_id=1,
        source_kind="plan",
        source_id=1,
        data_bytes_total=10,
        data_bytes_used=11,
        valid_from=now,
        valid_to=now + timedelta(days=1),
    )
    with (
        pytest.raises(IntegrityError, match="used_within_total"),
        Session(db.engine) as s,
        s.begin(),
    ):
        s.add(bucket)


# --- the balance, under load --------------------------------------------------------------------


def test_balance_equals_the_sum_of_entries_after_concurrent_postings(db: Database) -> None:
    workers, per_worker = 8, 25
    rng = random.Random(20261019)  # noqa: S311  (repeatable test data, not security)
    plan = [
        [
            (rng.randint(1, 3), rng.choice([-1, 1]) * rng.randint(1, 100_000))
            for _ in range(per_worker)
        ]
        for _ in range(workers)
    ]

    def run(worker: int) -> int:
        for i, (line, amount) in enumerate(plan[worker]):
            db.post(line, amount, "correction", f"w{worker}-{i}")
        return worker

    with ThreadPoolExecutor(max_workers=workers) as pool:
        done = [f.result() for f in [pool.submit(run, w) for w in range(workers)]]
    assert sorted(done) == list(range(workers))

    with Session(db.engine) as s:
        repo = SqlLedgerRepository(s)
        count = s.execute(select(func.count()).select_from(LedgerEntry)).scalar_one()
        assert count == workers * per_worker
        assert check_wallets(repo) == []
        expected: dict[int, int] = {}
        for worker_plan in plan:
            for line, amount in worker_plan:
                expected[line] = expected.get(line, 0) + amount
        for line, total in expected.items():
            assert repo.balance(line) == total


def test_the_same_event_posted_at_once_is_recorded_exactly_once(db: Database) -> None:
    racers = 8
    barrier = threading.Barrier(racers)

    def post_together(_: int) -> bool:
        barrier.wait()
        return db.post(1, 5_000, "top_up", "pay-race").replayed

    with ThreadPoolExecutor(max_workers=racers) as pool:
        replayed = [f.result() for f in [pool.submit(post_together, i) for i in range(racers)]]
    assert replayed.count(False) == 1 and replayed.count(True) == racers - 1
    assert db.scalar("SELECT count(*) FROM ledger_entry") == 1
    assert db.scalar("SELECT balance_kobo FROM wallet WHERE line_id = 1") == 5_000


def test_a_balance_that_would_overflow_is_refused_and_nothing_half_posted_remains(
    db: Database,
) -> None:
    db.post(1, BIGINT_MAX, "top_up", "huge-1")
    with pytest.raises(InvalidPosting, match="range"), Session(db.engine) as s, s.begin():
        post_entry(SqlLedgerRepository(s), new_posting(1, 1, "top_up", "one-more"))
    assert db.scalar("SELECT count(*) FROM ledger_entry") == 1
    assert db.scalar("SELECT balance_kobo FROM wallet WHERE line_id = 1") == BIGINT_MAX
    with Session(db.engine) as s:
        assert check_wallets(SqlLedgerRepository(s)) == []
