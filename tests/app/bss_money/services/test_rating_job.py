"""The rating job, end to end on SQLite: real storage, real state machine, a fake RatelLink.

The guarantees that need a real PostgreSQL (the transaction, two runs at once, the migration) are
in test_rating_job_postgres_integration.py.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import Engine, Select, func, select
from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Line, LineAudit
from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_money.models.allowance import AllowanceBucket
from app.bss_money.models.rating import UsageRating
from app.bss_money.repositories.ports import RatingRepository
from app.bss_money.repositories.sql import SqlRatingRepository
from app.bss_money.services.line_control import LifecycleLineControl
from app.bss_money.services.rating_job import RatingRun, run_rating
from tests.app.bss_lines.fakes import FakeRatelLinkClient, RecordedData
from tests.app.bss_money.rating_data import (
    DAY,
    T0,
    SeededLine,
    add_bucket,
    add_usage,
    seed_line,
)
from tests.app.bss_money.sqlite_database import sqlite_engine


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = sqlite_engine()
    yield engine
    engine.dispose()


class Job:
    """The rating job wired to one SQLite database and one fake RatelLink."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.client = FakeRatelLinkClient()
        self.wrap: Callable[[RatingRepository], RatingRepository] = lambda repository: repository

    @contextmanager
    def scope(self) -> Iterator[RatingRepository]:
        with Session(self.engine) as session, session.begin():
            yield self.wrap(SqlRatingRepository(session))

    @contextmanager
    def _lines_scope(self) -> Iterator[SqlLinesRepository]:
        with Session(self.engine) as session:
            yield SqlLinesRepository(session)

    def run(self, *, batch_size: int = 5000) -> RatingRun:
        control = LifecycleLineControl(self._lines_scope, self.client)
        return run_rating(self.scope, control, now=T0, batch_size=batch_size)

    def seed(self, build: Callable[[Session], SeededLine]) -> SeededLine:
        with Session(self.engine) as session, session.begin():
            return build(session)

    def query(self, statement: Select[Any]) -> Sequence[Any]:
        with Session(self.engine) as session:
            return session.execute(statement).scalars().all()


@pytest.fixture
def job(engine: Engine) -> Job:
    return Job(engine)


def _used(job: Job) -> list[int]:
    return list(
        job.query(select(AllowanceBucket.data_bytes_used).order_by(AllowanceBucket.bucket_id))
    )


def _ratings(job: Job) -> int:
    return len(job.query(select(UsageRating.usage_record_id)))


def _state(job: Job, line: SeededLine) -> str:
    return job.query(select(Line.state).where(Line.line_id == line.line_id))[0]


def test_usage_is_deducted_and_marked_rated(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s)
        add_bucket(s, line, 1_000)
        add_usage(s, line, 100, 200, minutes_ago=20)
        add_usage(s, line, 50, 50, minutes_ago=10)
        return line

    job.seed(build)
    run = job.run()

    assert (run.lines_rated, run.records_rated, run.bytes_deducted) == (1, 2, 400)
    assert _used(job) == [400]
    assert _ratings(job) == 2


def test_running_again_changes_nothing(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s)
        add_bucket(s, line, 1_000)
        add_usage(s, line, 100, 200)
        return line

    job.seed(build)
    job.run()
    second = job.run()

    assert (second.lines_rated, second.records_rated) == (0, 0)
    assert _used(job) == [300]
    assert _ratings(job) == 1


def test_usage_comes_off_the_bucket_that_expires_first(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s)
        add_bucket(s, line, 1_000, expires=T0 + 20 * DAY)  # the plan
        add_bucket(s, line, 1_000, expires=T0 + 5 * DAY)  # a bundle that expires sooner
        add_usage(s, line, 600, 0)
        return line

    job.seed(build)
    job.run()

    assert _used(job) == [0, 600]


def test_a_record_that_no_allowance_covers_is_kept_as_uncovered(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s)
        add_bucket(s, line, 100)
        add_usage(s, line, 150, 0)
        return line

    job.seed(build)
    run = job.run()

    assert (run.bytes_deducted, run.bytes_uncovered) == (100, 50)
    assert job.query(select(UsageRating.uncovered_bytes)) == [50]


def test_usage_of_a_sim_with_no_line_stays_unrated_and_is_not_a_failure(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s)
        add_usage(s, line, 10, 10)
        s.query(Line).delete()  # the SIM has no line any more
        return line

    job.seed(build)
    run = job.run()

    assert run == RatingRun()
    assert _ratings(job) == 0


def test_a_line_with_no_allowance_is_rated_but_never_cut(job: Job) -> None:
    line = job.seed(lambda s: _with_usage_only(s))
    run = job.run()

    assert run.bytes_uncovered == 30
    assert run.lines_out_of_data == 0
    assert job.client.calls == []
    assert _state(job, line) == "active"


def _with_usage_only(s: Session) -> SeededLine:
    line = seed_line(s)
    add_usage(s, line, 10, 20)
    return line


def test_a_line_whose_allowance_runs_out_is_slowed_once_and_voice_is_untouched(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s, on_exhaustion="slow")
        add_bucket(s, line, 500)
        add_usage(s, line, 300, 300)
        return line

    line = job.seed(build)
    first = job.run()
    second = job.run()
    third = job.run()

    assert (first.lines_out_of_data, second.lines_out_of_data, third.lines_out_of_data) == (1, 0, 0)
    assert (first.failures, second.failures, third.failures) == (0, 0, 0)  # not retried and refused
    assert _state(job, line) == "out_of_data"
    [call] = job.client.calls  # one call in all: /data, never /activate or /deactivate
    assert isinstance(call, RecordedData)
    assert (call.mode, call.speed_ul_mbps, call.speed_dl_mbps) == ("slow", 0.5, 1.0)
    audit = job.query(select(LineAudit))
    assert [(a.from_state, a.to_state, a.actor, a.reason) for a in audit] == [
        ("active", "out_of_data", "system:rating-job", "allowance_used_up")
    ]


def test_a_line_on_a_plan_that_stops_has_its_data_cut(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s, on_exhaustion="stop")
        add_bucket(s, line, 100)
        add_usage(s, line, 100, 0)
        return line

    job.seed(build)
    job.run()

    [call] = job.client.calls
    assert isinstance(call, RecordedData)
    assert call.mode == "off"


def test_exactly_zero_left_is_out_of_data_and_one_byte_left_is_not(job: Job) -> None:
    def build(s: Session) -> tuple[SeededLine, SeededLine]:
        empty = seed_line(s, 1)
        add_bucket(s, empty, 1_000)
        add_usage(s, empty, 500, 500)
        one_left = seed_line(s, 2)
        add_bucket(s, one_left, 1_000)
        add_usage(s, one_left, 500, 499)
        return empty, one_left

    with Session(job.engine) as session, session.begin():
        empty, one_left = build(session)
    run = job.run()

    assert run.lines_out_of_data == 1
    assert _state(job, empty) == "out_of_data"
    assert _state(job, one_left) == "active"


def test_a_change_that_failed_is_tried_again_on_the_next_run_even_without_new_usage(
    job: Job,
) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s)
        add_bucket(s, line, 100)
        add_usage(s, line, 100, 0)
        return line

    line = job.seed(build)
    job.client.fail_on_data = RuntimeError("RatelLink is down")
    first = job.run()
    assert first.failures == 1
    assert _state(job, line) == "active"  # nothing half-done
    assert _used(job) == [100]  # the usage was still rated

    job.client.fail_on_data = None
    second = job.run()

    assert (second.failures, second.lines_out_of_data) == (0, 1)
    assert _state(job, line) == "out_of_data"
    assert len(job.client.calls) == 1


def test_a_line_whose_validity_ended_expires_and_loses_service(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s)
        add_bucket(s, line, 1_000, starts=T0 - 31 * DAY, expires=T0 - DAY)
        return line

    line = job.seed(build)
    run = job.run()

    assert run.lines_expired == 1
    assert _state(job, line) == "expired"
    assert [c.endpoint for c in job.client.calls] == ["/deactivate"]
    assert job.run().lines_expired == 0


def test_an_out_of_data_line_whose_validity_ended_expires(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s, state="out_of_data")
        add_bucket(s, line, 1_000, starts=T0 - 31 * DAY, expires=T0 - DAY, used=1_000)
        return line

    line = job.seed(build)
    job.run()

    assert _state(job, line) == "expired"


def test_a_renewed_line_is_left_alone(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s)
        add_bucket(s, line, 1_000, starts=T0 - 31 * DAY, expires=T0 - DAY)  # the old plan
        add_bucket(s, line, 1_000, starts=T0 - DAY, expires=T0 + 29 * DAY)  # the renewal
        return line

    line = job.seed(build)
    run = job.run()

    assert (run.lines_expired, run.lines_out_of_data) == (0, 0)
    assert _state(job, line) == "active"


def test_one_line_failing_does_not_stop_the_others(job: Job) -> None:
    def build(s: Session) -> tuple[SeededLine, SeededLine]:
        first, second = seed_line(s, 1), seed_line(s, 2)
        for line in (first, second):
            add_bucket(s, line, 1_000)
            add_usage(s, line, 100, 0)
        return first, second

    with Session(job.engine) as session, session.begin():
        first, _ = build(session)

    class Breaks(SqlRatingRepository):
        def save_rating(self, line_id, result):  # type: ignore[no-untyped-def]
            if line_id == first.line_id:
                raise RuntimeError("disk full")
            super().save_rating(line_id, result)

    job.wrap = lambda repository: Breaks(repository._session)  # type: ignore[attr-defined]
    run = job.run()

    assert (run.failures, run.lines_rated) == (1, 1)
    assert _used(job) == [0, 100]  # the first line kept all its usage unrated
    assert _ratings(job) == 1


def test_a_backlog_bigger_than_a_batch_is_taken_over_several_runs(job: Job) -> None:
    def build(s: Session) -> SeededLine:
        line = seed_line(s)
        add_bucket(s, line, 10_000)
        for minutes_ago in (50, 40, 30):
            add_usage(s, line, 10, 0, minutes_ago=minutes_ago)
        return line

    job.seed(build)
    first = job.run(batch_size=2)
    second = job.run(batch_size=2)
    third = job.run(batch_size=2)

    assert (first.records_rated, second.records_rated, third.records_rated) == (2, 1, 0)
    assert _used(job) == [30]


def test_a_second_count_matches_the_first_whatever_the_order_of_runs(job: Job) -> None:
    """Rating in two runs gives the same bucket totals as rating in one."""

    def build(s: Session) -> SeededLine:
        line = seed_line(s)
        add_bucket(s, line, 1_000)
        for minutes_ago in (50, 40, 30, 20):
            add_usage(s, line, 7, 3, minutes_ago=minutes_ago)
        return line

    job.seed(build)
    job.run(batch_size=3)
    job.run(batch_size=3)

    assert _used(job) == [40]
    assert job.query(select(func.sum(UsageRating.deducted_bytes))) == [40]
