"""The call store on SQLite: one row per call_id, filters, and pages with no gap or duplicate."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.meter_api.domain import CallRecord
from app.meter_api.models import CallRecordModel
from app.meter_api.repositories.sql import SqlCallRepository
from common.timeutil import from_epoch

T = 1_794_700_000
A, B, C = "2340000000001", "2340000000002", "2340000000003"


def call(
    n: int, *, frm: str = A, to: str = B, started: int | None = None, **changes: object
) -> CallRecord:
    start = T + n * 100 if started is None else started
    values: dict[str, object] = {
        "call_id": f"call-{n:03d}",
        "from_msisdn": frm,
        "to_msisdn": to,
        "started_at": start,
        "answered_at": start + 5,
        "ended_at": start + 60,
        "end_reason": "completed",
    }
    return CallRecord(**{**values, **changes})  # type: ignore[arg-type]


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def window(repo: SqlCallRepository, **kw: object) -> tuple[list[CallRecord], str | None]:
    return repo.query_calls(from_epoch(T - 10), from_epoch(T + 10_000), **kw)  # type: ignore[arg-type]


def test_a_call_posted_twice_is_one_row_and_the_second_post_overwrites(session: Session) -> None:
    repo = SqlCallRepository(session)
    repo.upsert_calls([call(1, answered_at=None, ended_at=T + 111, end_reason="not_answered")])
    repo.upsert_calls([call(1)])  # the same call, now with its answer and its end
    assert session.scalar(select(func.count()).select_from(CallRecordModel)) == 1
    [only], _ = window(repo)
    assert only == call(1)


def test_the_same_call_twice_in_one_batch_keeps_the_last(session: Session) -> None:
    repo = SqlCallRepository(session)
    assert repo.upsert_calls([call(1, end_reason="completed"), call(1, ended_at=T + 999)]) == 1
    [only], _ = window(repo)
    assert only.ended_at == T + 999


def test_an_unanswered_call_has_answered_at_none(session: Session) -> None:
    repo = SqlCallRepository(session)
    repo.upsert_calls([call(1, answered_at=None, end_reason="declined")])
    [only], _ = window(repo)
    assert only.answered_at is None and only.end_reason == "declined"


def test_calls_come_oldest_first_and_the_window_is_inclusive_on_started_at(
    session: Session,
) -> None:
    repo = SqlCallRepository(session)
    repo.upsert_calls([call(3), call(1), call(2)])
    got, _ = repo.query_calls(
        from_epoch(T + 100), from_epoch(T + 300), None
    )  # call 1 and call 3 sit on the edges
    assert [r.call_id for r in got] == ["call-001", "call-002", "call-003"]
    got, _ = repo.query_calls(from_epoch(T + 101), from_epoch(T + 299), None)
    assert [r.call_id for r in got] == ["call-002"]


def test_a_number_finds_the_calls_it_made_and_the_calls_it_received(session: Session) -> None:
    repo = SqlCallRepository(session)
    repo.upsert_calls([call(1, frm=A, to=B), call(2, frm=B, to=C), call(3, frm=C, to=A)])
    assert [r.call_id for r in window(repo, msisdn=B)[0]] == ["call-001", "call-002"]
    assert [r.call_id for r in window(repo, msisdn=A)[0]] == ["call-001", "call-003"]
    assert window(repo, msisdn="2349999999999")[0] == []


def test_pages_have_no_gap_and_no_duplicate_even_when_calls_start_in_the_same_second(
    session: Session,
) -> None:
    repo = SqlCallRepository(session)
    repo.upsert_calls(
        [call(n, started=T + (n // 3) * 100) for n in range(10)]
    )  # three calls per second
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        page, cursor = window(repo, limit=4, cursor=cursor)
        seen += [r.call_id for r in page]
        pages += 1
        if cursor is None:
            break
    assert pages == 3 and seen == [f"call-{n:03d}" for n in range(10)]


def test_a_cursor_that_is_not_ours_gives_an_empty_page(session: Session) -> None:
    repo = SqlCallRepository(session)
    repo.upsert_calls([call(1)])
    assert window(repo, cursor="not-a-cursor") == ([], None)


def test_the_database_itself_refuses_a_call_that_breaks_a_rule(session: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    repo = SqlCallRepository(session)
    repo.upsert_calls([call(1)])
    session.flush()
    for bad in (
        call(2, end_reason="busy"),  # not an end reason
        call(3, answered_at=None),  # completed, but never answered
        call(4, ended_at=T + 100 * 4 - 1),  # ends before it starts
    ):
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(
                CallRecordModel(
                    call_id=bad.call_id,
                    from_msisdn=bad.from_msisdn,
                    to_msisdn=bad.to_msisdn,
                    started_at=from_epoch(bad.started_at),
                    answered_at=None if bad.answered_at is None else from_epoch(bad.answered_at),
                    ended_at=from_epoch(bad.ended_at),
                    end_reason=bad.end_reason,
                )
            )
            session.flush()
