"""The ledger's guarantees on a real PostgreSQL: the migration, the append-only triggers, BIGINT,
concurrent postings and the nightly check.

SQLite cannot show any of these. Run with RATEL_TEST_POSTGRES_URI set to a connection string that
may create and drop databases. Each test gets its own database, created from the real migration
and dropped afterwards, so nothing here touches an existing database.
"""

from __future__ import annotations

import os
import random
import secrets
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (registers the tables)
from app.bss_money import repositories as repo
from app.bss_money.check_cli import main as run_nightly_check
from app.bss_money.domain import BIGINT_MAX, InvalidPosting, new_posting
from app.bss_money.models import AllowanceBucket, LedgerEntry
from app.bss_money.services import check_wallets, post_entry
from app.db import Base

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "services/app/alembic.ini"
ADMIN_URL = os.environ.get("RATEL_TEST_POSTGRES_URI")


class Database:
    """A fresh database built by the real migration."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.engine: Engine = create_engine(url, pool_size=20, max_overflow=0)

    def alembic(self, *args: str) -> None:
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self.url
        try:
            cfg = Config(str(ALEMBIC_INI))
            if args[0] == "upgrade":
                command.upgrade(cfg, args[1])
            else:
                command.downgrade(cfg, args[1])
        finally:
            if previous is None:
                del os.environ["DATABASE_URL"]
            else:
                os.environ["DATABASE_URL"] = previous

    def post(self, line: int, amount: int, kind: str, reference: str):  # type: ignore[no-untyped-def]
        with Session(self.engine) as s, s.begin():
            return post_entry(s, new_posting(line, amount, kind, reference))

    def scalar(self, sql: str) -> object:
        with self.engine.connect() as conn:
            return conn.execute(text(sql)).scalar()


@pytest.fixture
def db() -> Iterator[Database]:
    if not ADMIN_URL:
        pytest.skip("RATEL_TEST_POSTGRES_URI is not set")
    name = f"ratel_money_{secrets.token_hex(4)}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    database = Database(url)
    database.alembic("upgrade", "head")
    try:
        yield database
    finally:
        database.engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


# --- the migration ------------------------------------------------------------------------------


def test_the_migration_applies_rolls_back_and_applies_again(db: Database) -> None:
    def tables() -> set[str]:
        with db.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
            return set(rows)

    assert {"wallet", "ledger_entry", "allowance_bucket"} <= tables()
    db.alembic("downgrade", "base")
    assert not {"wallet", "ledger_entry", "allowance_bucket"} & tables()
    assert (
        db.scalar("SELECT count(*) FROM pg_proc WHERE proname = 'ledger_entry_refuse_change'") == 0
    )
    db.alembic("upgrade", "head")
    assert {"wallet", "ledger_entry", "allowance_bucket"} <= tables()


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
    with pytest.raises(IntegrityError, match="append-only"):
        with db.engine.begin() as conn:
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
    with pytest.raises(IntegrityError):
        with db.engine.begin() as conn:
            conn.execute(text("DELETE FROM wallet WHERE line_id = 1"))


def test_the_bucket_rules_hold_on_postgresql_too(db: Database) -> None:
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 10, 19, tzinfo=UTC)
    with pytest.raises(IntegrityError, match="used_within_total"):
        with Session(db.engine) as s, s.begin():
            s.add(
                AllowanceBucket(
                    line_id=1,
                    source_kind="plan",
                    source_id=1,
                    data_bytes_total=10,
                    data_bytes_used=11,
                    valid_from=now,
                    valid_to=now + timedelta(days=1),
                )
            )


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
        assert (
            s.execute(select(func.count()).select_from(LedgerEntry)).scalar_one()
            == workers * per_worker
        )
        assert check_wallets(s) == []
        expected: dict[int, int] = {}
        for worker_plan in plan:
            for line, amount in worker_plan:
                expected[line] = expected.get(line, 0) + amount
        for line, total in expected.items():
            assert repo.wallet_balance(s, line) == total


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
    with pytest.raises(InvalidPosting, match="range"):
        with Session(db.engine) as s, s.begin():
            post_entry(s, new_posting(1, 1, "top_up", "one-more"))
    assert db.scalar("SELECT count(*) FROM ledger_entry") == 1
    assert db.scalar("SELECT balance_kobo FROM wallet WHERE line_id = 1") == BIGINT_MAX
    with Session(db.engine) as s:
        assert check_wallets(s) == []


# --- the nightly check --------------------------------------------------------------------------


def test_the_nightly_check_finds_a_corrupted_balance(
    db: Database, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db.post(1, 5_000, "top_up", "pay-1")
    db.post(2, 700, "top_up", "pay-1")
    monkeypatch.setenv("DATABASE_URL", db.url)

    assert run_nightly_check([]) == 0

    with db.engine.begin() as conn:  # the wallet is a plain table: this is the corruption to catch
        conn.execute(text("UPDATE wallet SET balance_kobo = balance_kobo + 1 WHERE line_id = 2"))
    with Session(db.engine) as s:
        found = check_wallets(s)
    assert [(m.line_id, m.wallet_kobo, m.ledger_kobo) for m in found] == [(2, 701, 700)]
    assert run_nightly_check([]) == 1
    assert "1 wallet(s) differ" in capsys.readouterr().err


def test_the_nightly_check_reports_that_it_could_not_run(
    db: Database, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    url = make_url(db.url).set(port=1)  # nothing listens here
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    assert run_nightly_check([]) == 2
    assert make_url(db.url).username not in capsys.readouterr().err
