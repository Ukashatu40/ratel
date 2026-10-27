"""The rating job's guarantees that need a real PostgreSQL: a crash, two runs at once, the table.

Build Plan, RatelBSS: money: the rating job marks each record rated in the same transaction as the
deduction, so a crash never rates a record twice; and the rating of a record is never lost.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Line
from app.bss_money.models.allowance import AllowanceBucket
from app.bss_money.models.rating import UsageRating
from app.bss_money.repositories.ports import RatingRepository
from app.bss_money.repositories.sql import SqlRatingRepository
from app.bss_money.services.rating_job import run_rating
from tests.app.bss_money.postgres import Database
from tests.app.bss_money.rating_data import T0, SeededLine, add_bucket, add_usage, seed_line

pytestmark = pytest.mark.integration


class NoControl:
    """Records the changes asked of it; the job's decision, not the lines, is under test here."""

    def __init__(self) -> None:
        self.out_of_data: list[int] = []
        self.expired: list[int] = []
        self.restored: list[int] = []

    def mark_out_of_data(self, line_id: int, idempotency_key: str) -> None:
        self.out_of_data.append(line_id)

    def expire(self, line_id: int, idempotency_key: str) -> None:
        self.expired.append(line_id)

    def restore(self, line_id: int, idempotency_key: str) -> None:
        self.restored.append(line_id)


def _scope(db: Database):  # type: ignore[no-untyped-def]
    @contextmanager
    def scope() -> Iterator[RatingRepository]:
        with Session(db.engine) as session, session.begin():
            yield SqlRatingRepository(session)

    return scope


def _seed(db: Database, records: int, total: int = 1_000_000) -> SeededLine:
    with Session(db.engine) as session, session.begin():
        line = seed_line(session)
        add_bucket(session, line, total)
        for i in range(records):
            add_usage(session, line, 3, 4, minutes_ago=records - i + 10)
        return line


def _totals(db: Database) -> tuple[int, int, int]:
    with Session(db.engine) as session:
        used = session.scalar(select(func.sum(AllowanceBucket.data_bytes_used))) or 0
        rated = session.scalar(select(func.count(UsageRating.usage_record_id))) or 0
        deducted = session.scalar(select(func.sum(UsageRating.deducted_bytes))) or 0
        return used, rated, deducted


def test_a_crash_after_the_deduction_keeps_nothing_and_the_next_run_rates_once(
    db: Database,
) -> None:
    _seed(db, records=5)

    class Crashes(SqlRatingRepository):
        def save_rating(self, line_id, result):  # type: ignore[no-untyped-def]
            super().save_rating(line_id, result)  # stored inside the transaction ...
            raise RuntimeError("the process died")  # ... and then the process dies

    @contextmanager
    def crashing() -> Iterator[RatingRepository]:
        with Session(db.engine) as session, session.begin():
            yield Crashes(session)

    crashed = run_rating(crashing, NoControl(), now=T0)

    assert crashed.failures == 1
    assert _totals(db) == (0, 0, 0)  # neither the deduction nor the marks survived

    first = run_rating(_scope(db), NoControl(), now=T0)
    second = run_rating(_scope(db), NoControl(), now=T0)

    assert (first.records_rated, second.records_rated) == (5, 0)
    assert _totals(db) == (35, 5, 35)


def test_several_runs_at_once_rate_every_record_exactly_once(db: Database) -> None:
    _seed(db, records=120)
    control = NoControl()

    def one_run(_: int):  # type: ignore[no-untyped-def]
        return run_rating(_scope(db), control, now=T0, batch_size=25)

    with ThreadPoolExecutor(max_workers=6) as pool:
        runs = list(pool.map(one_run, range(6)))

    assert [r.failures for r in runs] == [0] * 6
    assert sum(r.records_rated for r in runs) == 120
    assert _totals(db) == (840, 120, 840)  # 120 records of 7 bytes, each taken once


def test_a_record_cannot_be_rated_twice_even_by_hand(db: Database) -> None:
    line = _seed(db, records=1)
    run_rating(_scope(db), NoControl(), now=T0)

    with Session(db.engine) as session, pytest.raises(IntegrityError), session.begin():
        record_id = session.scalar(select(UsageRating.usage_record_id))
        session.add(
            UsageRating(
                usage_record_id=record_id, line_id=line.line_id, deducted_bytes=7, uncovered_bytes=0
            )
        )


def test_a_rating_must_point_at_a_real_record_and_line(db: Database) -> None:
    line = _seed(db, records=1)
    with Session(db.engine) as session, pytest.raises(IntegrityError), session.begin():
        session.add(
            UsageRating(
                usage_record_id=999_999, line_id=line.line_id, deducted_bytes=1, uncovered_bytes=0
            )
        )


def test_the_job_asks_for_out_of_data_once_the_allowance_is_used(db: Database) -> None:
    with Session(db.engine) as session, session.begin():
        line = seed_line(session)
        add_bucket(session, line, 7)
        add_usage(session, line, 3, 4)
    control = NoControl()

    run_rating(_scope(db), control, now=T0)

    assert control.out_of_data == [line.line_id]
    with Session(db.engine) as session:
        assert session.scalar(select(Line.state)) == "active"  # the control, not the job, moves it


def test_downgrade_refuses_while_the_rated_marks_exist_and_works_when_empty(db: Database) -> None:
    _seed(db, records=2)
    run_rating(_scope(db), NoControl(), now=T0)

    with pytest.raises(RuntimeError, match="refusing to drop usage_rating"):
        db.alembic("downgrade", "e3b80975b879")
    assert _totals(db)[1] == 2  # nothing was lost

    with Session(db.engine) as session, session.begin():
        session.query(UsageRating).delete()
    db.alembic("downgrade", "e3b80975b879")
    assert db.scalar("SELECT to_regclass('usage_rating')") is None
    db.alembic("upgrade", "head")
    assert db.scalar("SELECT to_regclass('usage_rating')") is not None
