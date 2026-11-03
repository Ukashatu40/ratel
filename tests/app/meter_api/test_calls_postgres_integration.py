"""The call store on a real PostgreSQL: one row per call_id however often it is posted, the CHECKs,
the pages, and the migration. Run with RATEL_TEST_POSTGRES_URI set
(tests/app/bss_money/postgres.py).
Synthetic numbers only."""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.meter_api.domain import CallRecord
from app.meter_api.repositories.sql import SqlCallRepository
from common.timeutil import from_epoch
from tests.app.bss_money.postgres import Database

pytestmark = pytest.mark.integration

INSERT_PREFIX = (
    "INSERT INTO call_record (call_id, from_msisdn, to_msisdn, started_at, ended_at, end_reason) "
    "VALUES "
)

T = 1_794_700_000
A, B = "2340000000001", "2340000000002"


def call(n: int, **changes: object) -> CallRecord:
    start = T + n * 100
    values: dict[str, object] = {
        "call_id": f"call-{n:03d}", "from_msisdn": A, "to_msisdn": B, "started_at": start,
        "answered_at": start + 5, "ended_at": start + 60, "end_reason": "completed",
    }  # fmt: skip
    return CallRecord(**{**values, **changes})  # type: ignore[arg-type]


def post(db: Database, *records: CallRecord) -> None:
    with Session(db.engine) as session, session.begin():
        SqlCallRepository(session).upsert_calls(records)


def test_the_same_call_posted_twice_is_one_row_with_the_latest_values(db: Database) -> None:
    post(db, call(1, answered_at=None, ended_at=T + 111, end_reason="not_answered"))
    post(db, call(1))
    assert db.scalar("SELECT count(*) FROM call_record") == 1
    assert db.scalar("SELECT end_reason FROM call_record") == "completed"
    assert db.scalar("SELECT answered_at IS NOT NULL FROM call_record") is True


def test_the_same_call_twice_in_one_batch_is_one_row_and_the_last_wins(db: Database) -> None:
    start = T + 100  # call(1) starts here
    post(db, call(1, ended_at=start + 70), call(1, ended_at=start + 90))
    assert db.scalar("SELECT count(*) FROM call_record") == 1
    assert db.scalar("SELECT extract(epoch FROM ended_at - started_at)::int FROM call_record") == 90


def test_the_database_refuses_what_the_agreement_forbids(db: Database) -> None:
    for sql in (
        INSERT_PREFIX + "('x', '1', '2', now(), now(), 'busy')",
        INSERT_PREFIX + "('y', '1', '2', now(), now(), 'completed')",  # completed, never answered
        INSERT_PREFIX
        + "('z', '1', '2', now(), now() - interval '1 second', 'failed')",  # ends first
    ):
        with pytest.raises(IntegrityError):
            db.run(sql)


def test_pages_have_no_gap_or_duplicate_with_concurrent_starts(db: Database) -> None:
    # Three calls start in each second, so the cursor must break ties on call_id.
    post(db, *[replace(call(n // 3), call_id=f"call-{n:03d}") for n in range(10)])
    seen: list[str] = []
    cursor = None
    with Session(db.engine) as session:
        repo = SqlCallRepository(session)
        while True:
            page, cursor = repo.query_calls(
                from_epoch(T), from_epoch(T + 10_000), limit=4, cursor=cursor
            )
            seen += [r.call_id for r in page]
            if cursor is None:
                break
    assert seen == [f"call-{n:03d}" for n in range(10)]


def test_the_migration_rolls_back_only_while_the_table_is_empty(db: Database) -> None:
    post(db, call(1))
    with pytest.raises(Exception, match="refusing to drop call_record"):
        db.alembic("downgrade", "dd286ac07496")
    db.run("DELETE FROM call_record")
    db.alembic("downgrade", "dd286ac07496")
    assert db.scalar("SELECT to_regclass('call_record')") is None
    db.alembic("upgrade", "head")
    assert db.scalar("SELECT to_regclass('call_record')") is not None
