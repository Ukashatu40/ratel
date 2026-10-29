"""The rating job and staff changing the same lines at the same moment, on a real PostgreSQL.

A change to a line holds that line's row until it commits (`SqlLinesRepository.get`), and a change
calls RatelLink while holding it. These tests make RatelLink slow, so the overlap is certain, and
check that the two sides take turns: no change is lost or doubled, the audit trail is a chain, each
RatelLink call has its audit entry, and nothing hangs.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bss_lines.api.lines import get_client
from app.bss_lines.models.lines import Line, LineAudit
from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_money.repositories.sql import SqlRatingRepository
from app.bss_money.services.line_control import LifecycleLineControl
from app.bss_money.services.rating_job import RatingRun, run_rating
from tests.app.bss_lines.fakes import FakeRatelLinkClient
from tests.app.bss_money.api.desk_postgres import Desk
from tests.app.bss_money.rating_data import DAY, SeededLine, add_bucket, add_bundle, seed_line

pytestmark = pytest.mark.integration

SLOW = 0.4  # seconds RatelLink takes to answer


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.passwords._N", 2**10)


class SlowRatelLink(FakeRatelLinkClient):
    def deactivate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        time.sleep(SLOW)
        return super().deactivate(*args, **kwargs)

    def data(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        time.sleep(SLOW)
        return super().data(*args, **kwargs)

    def activate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        time.sleep(SLOW)
        return super().activate(*args, **kwargs)


@pytest.fixture
def desk(db) -> Iterator[Desk]:  # type: ignore[no-untyped-def]
    desk = Desk(db)
    desk.network = SlowRatelLink()
    desk.app.dependency_overrides[get_client] = lambda: desk.network
    yield desk


def _job(desk: Desk) -> RatingRun:
    @contextmanager
    def scope() -> Iterator[SqlRatingRepository]:
        with Session(desk.db.engine) as session, session.begin():
            yield SqlRatingRepository(session)

    @contextmanager
    def lines_scope() -> Iterator[SqlLinesRepository]:
        with Session(desk.db.engine) as session:
            yield SqlLinesRepository(session)

    return run_rating(scope, LifecycleLineControl(lines_scope, desk.network), now=datetime.now(UTC))


def _spent_lines(desk: Desk, count: int) -> list[SeededLine]:
    """Active lines whose whole allowance is used: the job's next pass puts them out of data."""
    now = datetime.now(UTC)
    with Session(desk.db.engine) as session, session.begin():
        lines = [seed_line(session, n, state="active") for n in range(1, count + 1)]
        for line in lines:
            add_bucket(session, line, 1_000, starts=now - DAY, expires=now + 29 * DAY, used=1_000)
        return lines


def _audit(desk: Desk, line: SeededLine) -> list[tuple[str, str]]:
    with Session(desk.db.engine) as session:
        rows = session.scalars(
            select(LineAudit).where(LineAudit.line_id == line.line_id).order_by(LineAudit.id)
        )
        return [(r.from_state, r.to_state) for r in rows]


def test_staff_suspending_while_the_job_puts_lines_out_of_data_loses_and_doubles_nothing(
    desk: Desk,
) -> None:
    lines = _spent_lines(desk, 4)

    def suspend(line: SeededLine):  # type: ignore[no-untyped-def]
        return desk.agent.post(
            f"/v1/lines/{line.line_id}/suspend",
            json={"reason": "fraud"},
            headers={"Idempotency-Key": f"s-{line.line_id}"},
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        job = pool.submit(_job, desk)
        replies = [pool.submit(suspend, line) for line in lines]
        run = job.result(timeout=60)
        codes = [r.result(timeout=60).status_code for r in replies]

    assert codes == [200] * 4  # suspending is allowed from active and from out of data
    with Session(desk.db.engine) as session:
        assert {s for (s,) in session.execute(select(Line.state))} == {"suspended"}
    for line in lines:
        chain = _audit(desk, line)
        assert chain[0][0] == "active"
        assert all(a[1] == b[0] for a, b in pairwise(chain)), chain
        assert chain[-1][1] == "suspended"
        assert len(chain) in (1, 2)  # suspended alone, or out of data first and then suspended
    # Every change made one RatelLink call, and every call is in the audit trail.
    audits = sum(len(_audit(desk, line)) for line in lines)
    assert len(desk.network.calls) == audits
    # The job did not crash. A line it found already suspended is not a failure to chase.
    assert run.failures <= len(lines)


def test_a_purchase_waits_for_a_line_being_restored_and_then_goes_through(desk: Desk) -> None:
    now = datetime.now(UTC)
    with Session(desk.db.engine) as session, session.begin():
        line = seed_line(session, 1, state="out_of_data")
        add_bucket(session, line, 1_000, starts=now - DAY, expires=now + 29 * DAY, used=1_000)
        bundle_id = add_bundle(session, price_kobo=30_000, data_bytes=5_000)
    desk.db.post(line.line_id, 200_000, "top_up", "pay-1")
    assert (
        desk.agent.post(
            f"/v1/lines/{line.line_id}/purchases",
            json={"offer_kind": "bundle", "offer_id": bundle_id},
            headers={"Idempotency-Key": "buy-1"},
        ).status_code
        == 200
    )

    def buy_again():  # type: ignore[no-untyped-def]
        time.sleep(SLOW / 4)  # arrives while the job holds the line for its slow call
        return desk.agent.post(
            f"/v1/lines/{line.line_id}/purchases",
            json={"offer_kind": "bundle", "offer_id": bundle_id},
            headers={"Idempotency-Key": "buy-2"},
        )

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        job = pool.submit(_job, desk)
        second = pool.submit(buy_again)
        run = job.result(timeout=60)
        bought = second.result(timeout=60)
    elapsed = time.monotonic() - started

    assert (run.lines_restored, run.failures) == (1, 0)
    assert bought.status_code == 200
    assert elapsed < 10, "the purchase should wait for the line, not hang"
    with Session(desk.db.engine) as session:
        assert session.get(Line, line.line_id).state == "active"  # type: ignore[union-attr]
    wallet = desk.agent.get(f"/v1/lines/{line.line_id}/wallet").json()
    assert wallet["balance_kobo"] == wallet["ledger_sum_kobo"] == 200_000 - 2 * 30_000
    assert [c.endpoint for c in desk.network.calls] == ["/data"]  # restored once


def test_two_job_runs_at_once_restore_a_line_once(desk: Desk) -> None:
    now = datetime.now(UTC)
    with Session(desk.db.engine) as session, session.begin():
        line = seed_line(session, 1, state="out_of_data")
        add_bucket(session, line, 1_000, starts=now - DAY, expires=now + 29 * DAY, used=1_000)
        add_bucket(session, line, 5_000, starts=now - DAY, expires=now + timedelta(days=3))

    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(lambda _: _job(desk), range(2)))

    assert sum(r.lines_restored for r in runs) >= 1
    with Session(desk.db.engine) as session:
        assert session.get(Line, line.line_id).state == "active"  # type: ignore[union-attr]
    chain = _audit(desk, line)
    assert chain == [("out_of_data", "active")], chain
    assert len(desk.network.calls) == 1
