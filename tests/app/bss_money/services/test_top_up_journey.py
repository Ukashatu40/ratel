"""Act 5 of the demo, end to end on SQLite: a voucher is redeemed and data returns.

Real storage, real state machine, a fake RatelLink. The order is the one the deployment runs: the
redemption credits the wallet; the next run of the rating job buys the line's plan again (when the
deployment turned that on) and brings the line back, once.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Line, LineAudit
from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_money.models.ledger import LedgerEntry
from app.bss_money.repositories.ports import PurchaseRepositories, RatingRepository
from app.bss_money.repositories.sql import (
    SqlLedgerRepository,
    SqlPurchaseRepository,
    SqlRatingRepository,
    SqlVoucherRepository,
)
from app.bss_money.services.line_control import LifecycleLineControl
from app.bss_money.services.purchase import renew_plan_if_covered
from app.bss_money.services.rating_job import RatingRun, run_rating
from app.bss_money.services.vouchers import RedeemStatus, redeem_voucher
from tests.app.bss_lines.fakes import FakeRatelLinkClient, RecordedData
from tests.app.bss_money.rating_data import T0, SeededLine, add_bucket, seed_line
from tests.app.bss_money.sqlite_database import sqlite_engine
from tests.app.bss_money.vouchers_data import issue

VAT = 750


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = sqlite_engine()
    yield engine
    engine.dispose()


class Journey:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.client = FakeRatelLinkClient()

    @contextmanager
    def scope(self) -> Iterator[RatingRepository]:
        with Session(self.engine) as session, session.begin():
            yield SqlRatingRepository(session)

    @contextmanager
    def lines_scope(self) -> Iterator[SqlLinesRepository]:
        with Session(self.engine) as session:
            yield SqlLinesRepository(session)

    @contextmanager
    def purchase_scope(self) -> Iterator[PurchaseRepositories]:
        with Session(self.engine) as session, session.begin():
            yield PurchaseRepositories(SqlPurchaseRepository(session), SqlLedgerRepository(session))

    def run(self, *, auto_renew: bool = True) -> RatingRun:
        def renew(line_id: int) -> bool:
            bought = renew_plan_if_covered(
                self.purchase_scope, line_id=line_id, now=T0, vat_rate_bps=VAT
            )
            return bought is not None

        return run_rating(
            self.scope,
            LifecycleLineControl(self.lines_scope, self.client),
            now=T0,
            renew=renew if auto_renew else None,
        )

    def spent_line(
        self, state: str = "out_of_data", face: int = 120_000
    ) -> tuple[SeededLine, str, str]:
        with Session(self.engine) as session, session.begin():
            line = seed_line(session, state=state)
            add_bucket(session, line, 500, used=500)
            [card] = issue(session, face=face)
        return line, card.card_number, card.pin

    def redeem(self, line: SeededLine, number: str, pin: str) -> RedeemStatus:
        with Session(self.engine) as session, session.begin():
            return redeem_voucher(
                SqlVoucherRepository(session),
                SqlLedgerRepository(session),
                line_id=line.line_id,
                card_number=number,
                pin=pin,
                now=T0,
            ).status

    def state(self, line: SeededLine) -> str:
        with Session(self.engine) as session:
            return session.scalar(select(Line.state).where(Line.line_id == line.line_id)) or ""

    def entries(self) -> list[tuple[str, int]]:
        with Session(self.engine) as session:
            return [
                tuple(r)
                for r in session.execute(
                    select(LedgerEntry.kind, LedgerEntry.amount_kobo).order_by(LedgerEntry.entry_id)
                )
            ]  # type: ignore[misc]

    def balance(self, line: SeededLine) -> int | None:
        with Session(self.engine) as session:
            return SqlLedgerRepository(session).balance(line.line_id)


@pytest.fixture
def journey(engine: Engine) -> Journey:
    return Journey(engine)


def test_redeeming_a_voucher_brings_an_out_of_data_line_back_with_full_speed(
    journey: Journey,
) -> None:
    line, number, pin = journey.spent_line()
    assert journey.redeem(line, number, pin) is RedeemStatus.REDEEMED

    first = journey.run()
    second = journey.run()

    assert (first.lines_renewed, first.lines_restored, first.failures) == (1, 1, 0)
    assert (second.lines_renewed, second.lines_restored, second.failures) == (0, 0, 0)
    assert journey.state(line) == "active"
    [call] = (
        journey.client.calls
    )  # one call, /data at the plan's full speed: voice is never touched
    assert isinstance(call, RecordedData)
    assert (call.mode, call.speed_ul_mbps, call.speed_dl_mbps) == ("full", 5.0, 10.0)
    assert journey.entries() == [("top_up", 120_000), ("purchase", -93_023), ("vat", -6_977)]
    assert journey.balance(line) == 20_000


def test_an_expired_line_is_activated_again_by_the_same_top_up(journey: Journey) -> None:
    line, number, pin = journey.spent_line(state="expired")
    journey.redeem(line, number, pin)

    run = journey.run()

    assert (run.lines_renewed, run.lines_restored) == (1, 1)
    assert journey.state(line) == "active"
    assert [c.endpoint for c in journey.client.calls] == ["/activate"]


def test_a_voucher_that_does_not_cover_the_plan_changes_nothing_but_the_wallet(
    journey: Journey,
) -> None:
    line, number, pin = journey.spent_line(face=50_000)
    journey.redeem(line, number, pin)

    run = journey.run()

    assert (run.lines_renewed, run.lines_restored) == (0, 0)
    assert journey.state(line) == "out_of_data"
    assert journey.balance(line) == 50_000
    assert journey.client.calls == []


def test_with_auto_renew_off_the_wallet_is_credited_and_nothing_is_bought(journey: Journey) -> None:
    line, number, pin = journey.spent_line()
    journey.redeem(line, number, pin)

    run = journey.run(auto_renew=False)

    assert (run.lines_renewed, run.lines_restored) == (0, 0)
    assert journey.state(line) == "out_of_data"
    assert journey.entries() == [("top_up", 120_000)]


def test_if_ratellink_is_down_the_payment_stands_and_the_line_returns_on_the_next_run(
    journey: Journey,
) -> None:
    line, number, pin = journey.spent_line()
    journey.redeem(line, number, pin)
    journey.client.fail_on_data = RuntimeError("RatelLink is down")

    first = journey.run()

    assert (first.lines_renewed, first.lines_restored, first.failures) == (1, 0, 1)
    assert journey.state(line) == "out_of_data"
    assert journey.balance(line) == 20_000  # the money was spent on a plan the customer now holds

    journey.client.fail_on_data = None
    second = journey.run()

    assert (second.lines_renewed, second.lines_restored, second.failures) == (
        0,
        1,
        0,
    )  # not charged again
    assert journey.state(line) == "active"
    assert journey.balance(line) == 20_000
    audit = journey.entries()
    assert [k for k, _ in audit] == ["top_up", "purchase", "vat"]


def test_the_audit_trail_says_why_the_line_came_back(journey: Journey, engine: Engine) -> None:
    line, number, pin = journey.spent_line()
    journey.redeem(line, number, pin)
    journey.run()

    with Session(engine) as session:
        rows = session.execute(
            select(LineAudit.from_state, LineAudit.to_state, LineAudit.actor, LineAudit.reason)
        ).all()
    assert [tuple(r) for r in rows] == [
        ("out_of_data", "active", "system:rating-job", "allowance_restored")
    ]


def test_a_line_that_is_still_active_is_never_charged_by_a_top_up(journey: Journey) -> None:
    line, number, pin = journey.spent_line(state="active")
    journey.redeem(line, number, pin)

    run = journey.run()

    assert (run.lines_renewed, run.lines_restored) == (0, 0)
    assert journey.entries() == [("top_up", 120_000)]  # the money waits in the wallet
