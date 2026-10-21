"""The usage store on a real PostgreSQL: one row per (imsi, period_start) however often an interval
is posted, no gap or duplicate across pages, and the migration rolls back.

SQLite (test_repository.py) uses a different upsert statement from PostgreSQL, so the guarantees the
issue asks for are proved here, on the database the service really runs on. Run with
RATEL_TEST_POSTGRES_URI set (tests/app/bss_money/postgres.py). Synthetic IMSIs only.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.meter_api.domain import UsageRecord
from app.meter_api.repositories.sql import SqlUsageRepository
from common.timeutil import from_epoch
from tests.app.bss_money.postgres import Database

pytestmark = pytest.mark.integration

T0 = 1791820800  # 2026-10-12 12:00 UTC, a multiple of 300
IMSI = "621000000000001"
USAGE_TABLE = "usage_record"
MONEY_ROOT = "4776e9127fec"


def _record(imsi: str = IMSI, start: int = T0, up: int = 1000, down: int = 2000) -> UsageRecord:
    return UsageRecord(imsi, start, start + 300, up, down)


def _post(database: Database, records: list[UsageRecord]) -> None:
    with Session(database.engine) as session, session.begin():
        SqlUsageRepository(session).upsert_records(records)


def _count(database: Database) -> object:
    return database.scalar("SELECT count(*) FROM usage_record")


def test_the_same_interval_posted_twice_leaves_one_row_with_the_latest_bytes(db: Database) -> None:
    _post(db, [_record(up=1000, down=2000)])
    _post(db, [_record(up=1500, down=3000)])
    assert _count(db) == 1
    assert db.scalar("SELECT bytes_up FROM usage_record") == 1500
    assert db.scalar("SELECT bytes_down FROM usage_record") == 3000


def test_a_replayed_batch_does_not_change_the_row_count(db: Database) -> None:
    batch = [_record(start=T0 + 300 * i, up=i + 1, down=i + 2) for i in range(50)]
    _post(db, batch)
    _post(db, batch)
    _post(db, batch)
    assert _count(db) == 50


def test_the_same_interval_from_two_lines_is_two_rows(db: Database) -> None:
    _post(db, [_record(IMSI), _record("621000000000002")])
    assert _count(db) == 2


def test_the_same_interval_posted_at_once_is_one_row(db: Database) -> None:
    racers = 8
    barrier = threading.Barrier(racers)

    def post(i: int) -> None:
        barrier.wait()
        _post(db, [_record(up=1000 + i, down=2000 + i)])

    with ThreadPoolExecutor(max_workers=racers) as pool:
        for future in [pool.submit(post, i) for i in range(racers)]:
            future.result()  # none of them may fail
    assert _count(db) == 1


def test_pagination_covers_12000_records_with_no_gap_and_no_duplicate(db: Database) -> None:
    imsis = [f"6210000000{n:05d}" for n in range(40)]
    expected = set()
    batch = []
    for n, imsi in enumerate(imsis):
        for i in range(300):  # 40 lines x 300 intervals = 12,000 records
            start = T0 + 300 * i
            batch.append(_record(imsi, start, up=n + 1, down=i + 1))
            expected.add((start, imsi))
    for chunk in range(0, len(batch), 3000):
        _post(db, batch[chunk : chunk + 3000])
    assert _count(db) == 12_000

    seen: list[tuple[int, str]] = []
    cursor = None
    pages = 0
    with Session(db.engine) as session:
        repo = SqlUsageRepository(session)
        while True:
            records, cursor = repo.query_usage(
                from_time=from_epoch(T0 - 1),
                to_time=from_epoch(T0 + 300 * 400),
                limit=5000,
                cursor=cursor,
            )
            seen += [(r.period_start, r.imsi) for r in records]
            pages += 1
            if cursor is None:
                break
    assert pages == 3  # 5,000 + 5,000 + 2,000
    assert len(seen) == 12_000 and set(seen) == expected  # no duplicate, no gap
    assert seen == sorted(seen)  # in a stable order


def test_times_are_stored_as_utc_and_read_back_as_the_same_epoch_seconds(db: Database) -> None:
    _post(db, [_record(start=T0)])
    with Session(db.engine) as session:
        records, _ = SqlUsageRepository(session).query_usage(
            from_time=from_epoch(T0 - 1), to_time=from_epoch(T0 + 1)
        )
    assert [(r.period_start, r.period_end, r.bytes_up, r.bytes_down) for r in records] == [
        (T0, T0 + 300, 1000, 2000)
    ]
    assert db.scalar(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'usage_record' AND column_name = 'period_start'"
    ) == ("timestamp with time zone")


BAD_ROWS = [
    # negative upload, negative download, and a period that ends before it starts
    "VALUES ('621000000000001', now(), now(), -1, 0)",
    "VALUES ('621000000000001', now(), now(), 0, -1)",
    "VALUES ('621000000000001', now(), now() - interval '1 second', 0, 0)",
]


@pytest.mark.parametrize("values", BAD_ROWS)
def test_the_database_refuses_a_row_that_breaks_a_check(db: Database, values: str) -> None:
    statement = (
        "INSERT INTO usage_record (imsi, period_start, period_end, bytes_up, bytes_down) " + values
    )
    with pytest.raises(IntegrityError), db.engine.begin() as conn:
        conn.execute(text(statement))
    assert _count(db) == 0


def test_the_usage_migration_rolls_back_and_applies_again(db: Database) -> None:
    def tables() -> set[str]:
        with db.engine.connect() as conn:
            return set(
                conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).scalars()
            )

    assert USAGE_TABLE in tables()
    db.alembic("downgrade", MONEY_ROOT)  # undoes the lines step and the usage step
    assert USAGE_TABLE not in tables()
    assert "wallet" in tables()  # the money tables stay
    db.alembic("upgrade", "head")
    assert USAGE_TABLE in tables()
