"""Buying a plan or a bundle from the wallet, and renewing a plan when a top-up covers it."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Line
from app.bss_lines.models.lines import Plan as PlanRow
from app.bss_money.domain.entries import new_posting
from app.bss_money.domain.purchase import OfferKind
from app.bss_money.models.allowance import AllowanceBucket
from app.bss_money.models.ledger import LedgerEntry
from app.bss_money.repositories.ports import PurchaseRepositories
from app.bss_money.repositories.sql import SqlLedgerRepository, SqlPurchaseRepository
from app.bss_money.services.ledger import post_entry
from app.bss_money.services.purchase import (
    InsufficientFunds,
    LineCannotBuy,
    LineNotFound,
    OfferNotAvailable,
    buy_offer,
    renew_plan_if_covered,
)
from tests.app.bss_money.rating_data import DAY, T0, SeededLine, add_bucket, add_bundle, seed_line
from tests.app.bss_money.sqlite_database import sqlite_engine

VAT = 750
PRICE = 100_000  # what seed_line's plan costs


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = sqlite_engine()
    yield engine
    engine.dispose()


class Shop:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def scope(self) -> Iterator[PurchaseRepositories]:
        with Session(self.engine) as session, session.begin():
            yield PurchaseRepositories(SqlPurchaseRepository(session), SqlLedgerRepository(session))

    def seed(self, state: str = "active") -> SeededLine:
        with Session(self.engine) as session, session.begin():
            return seed_line(session, state=state)

    def fund(self, line: SeededLine, kobo: int, reference: str = "fund-1") -> None:
        with Session(self.engine) as session, session.begin():
            post_entry(
                SqlLedgerRepository(session), new_posting(line.line_id, kobo, "top_up", reference)
            )

    def buy(
        self,
        line: SeededLine,
        *,
        kind: OfferKind = OfferKind.PLAN,
        offer_id: int | None = None,
        reference: str = "buy-1",
        vat: int = VAT,
    ):  # type: ignore[no-untyped-def]
        return buy_offer(
            self.scope,
            line_id=line.line_id,
            kind=kind,
            offer_id=line.plan_id if offer_id is None else offer_id,
            reference=reference,
            now=T0,
            vat_rate_bps=vat,
        )

    def balance(self, line: SeededLine) -> int | None:
        with Session(self.engine) as session:
            return SqlLedgerRepository(session).balance(line.line_id)

    def entries(self) -> list[tuple[str, int, str]]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(LedgerEntry.kind, LedgerEntry.amount_kobo, LedgerEntry.reference).order_by(
                    LedgerEntry.entry_id
                )
            )
            return [tuple(r) for r in rows]  # type: ignore[misc]

    def buckets(self) -> list[AllowanceBucket]:
        with Session(self.engine) as session:
            return list(
                session.scalars(select(AllowanceBucket).order_by(AllowanceBucket.bucket_id))
            )


@pytest.fixture
def shop(engine: Engine) -> Shop:
    return Shop(engine)


def test_buying_a_plan_debits_the_wallet_splits_the_vat_and_creates_the_bucket(shop: Shop) -> None:
    line = shop.seed()
    shop.fund(line, 250_000)

    result = shop.buy(line)

    assert (result.price_kobo, result.net_kobo, result.vat_kobo) == (100_000, 93_023, 6_977)
    assert (result.balance_kobo, result.replayed) == (150_000, False)
    assert shop.balance(line) == 150_000
    assert shop.entries() == [
        ("top_up", 250_000, "fund-1"),
        ("purchase", -93_023, "buy-1"),
        ("vat", -6_977, "buy-1"),  # its own entry, so reports can separate it
    ]
    [bucket] = shop.buckets()
    assert (bucket.line_id, bucket.source_kind, bucket.source_id) == (
        line.line_id,
        "plan",
        line.plan_id,
    )
    assert (bucket.data_bytes_total, bucket.data_bytes_used) == (1_000, 0)
    assert bucket.valid_from.replace(tzinfo=T0.tzinfo) == T0
    assert bucket.valid_to.replace(tzinfo=T0.tzinfo) == T0 + 30 * DAY
    assert result.valid_to == T0 + 30 * DAY


def test_a_wallet_that_does_not_cover_the_price_is_refused_and_nothing_changes(shop: Shop) -> None:
    line = shop.seed()
    shop.fund(line, 99_999)

    with pytest.raises(InsufficientFunds) as refused:
        shop.buy(line)

    assert refused.value.shortfall_kobo == 1
    assert shop.balance(line) == 99_999
    assert shop.buckets() == []
    assert shop.entries() == [("top_up", 99_999, "fund-1")]


def test_a_line_with_no_wallet_at_all_is_refused(shop: Shop) -> None:
    line = shop.seed()
    with pytest.raises(InsufficientFunds) as refused:
        shop.buy(line)
    assert refused.value.shortfall_kobo == PRICE


def test_exactly_the_price_is_enough_and_leaves_zero(shop: Shop) -> None:
    line = shop.seed()
    shop.fund(line, PRICE)

    shop.buy(line)

    assert shop.balance(line) == 0


def test_the_same_reference_again_changes_nothing_and_returns_the_first_purchase(
    shop: Shop,
) -> None:
    line = shop.seed()
    shop.fund(line, 250_000)
    first = shop.buy(line)

    again = shop.buy(line)

    assert again.replayed is True
    assert (again.price_kobo, again.net_kobo, again.vat_kobo) == (
        first.price_kobo,
        first.net_kobo,
        first.vat_kobo,
    )
    assert again.balance_kobo == 150_000
    assert shop.balance(line) == 150_000
    assert len(shop.buckets()) == 1


def test_two_different_references_are_two_purchases(shop: Shop) -> None:
    line = shop.seed()
    shop.fund(line, 250_000)
    shop.buy(line, reference="a")
    shop.buy(line, reference="b")

    assert shop.balance(line) == 50_000
    assert len(shop.buckets()) == 2


def test_no_vat_entry_when_the_vat_is_zero(shop: Shop) -> None:
    line = shop.seed()
    shop.fund(line, PRICE)

    shop.buy(line, vat=0)

    assert [k for k, _, _ in shop.entries()] == ["top_up", "purchase"]
    assert shop.balance(line) == 0


def test_a_bundle_is_bought_like_a_plan(shop: Shop, engine: Engine) -> None:
    line = shop.seed()
    with Session(engine) as session, session.begin():
        bundle_id = add_bundle(session, price_kobo=30_000, data_bytes=5_000, days=7)
    shop.fund(line, 50_000)

    result = shop.buy(line, kind=OfferKind.BUNDLE, offer_id=bundle_id)

    assert result.price_kobo == 30_000
    [bucket] = shop.buckets()
    assert (bucket.source_kind, bucket.source_id, bucket.data_bytes_total) == (
        "bundle",
        bundle_id,
        5_000,
    )
    assert bucket.valid_to.replace(tzinfo=T0.tzinfo) == T0 + timedelta(days=7)


def test_what_cannot_be_bought_is_refused(shop: Shop, engine: Engine) -> None:
    line = shop.seed()
    shop.fund(line, 500_000)
    with pytest.raises(OfferNotAvailable):
        shop.buy(line, offer_id=999)  # no such plan
    with pytest.raises(OfferNotAvailable):
        shop.buy(line, kind=OfferKind.BUNDLE, offer_id=999)
    with Session(engine) as session, session.begin():
        session.get(PlanRow, line.plan_id).state = "retired"  # type: ignore[union-attr]
    with pytest.raises(OfferNotAvailable):
        shop.buy(line)  # retired
    with pytest.raises(LineNotFound):
        buy_offer(
            shop.scope,
            line_id=999,
            kind=OfferKind.PLAN,
            offer_id=1,
            reference="x",
            now=T0,
            vat_rate_bps=VAT,
        )
    assert shop.buckets() == []
    assert shop.balance(line) == 500_000


def test_a_free_offer_is_not_sold_yet(shop: Shop, engine: Engine) -> None:
    line = shop.seed()
    with Session(engine) as session, session.begin():
        free = add_bundle(session, price_kobo=0)
    with pytest.raises(OfferNotAvailable, match="free"):
        shop.buy(line, kind=OfferKind.BUNDLE, offer_id=free)


@pytest.mark.parametrize("state", ["suspended", "terminated"])
def test_a_suspended_or_terminated_line_cannot_buy(shop: Shop, state: str) -> None:
    line = shop.seed(state=state)
    shop.fund(line, PRICE)
    with pytest.raises(LineCannotBuy):
        shop.buy(line)
    assert shop.buckets() == []


@pytest.mark.parametrize("state", ["awaiting_activation", "active", "out_of_data", "expired"])
def test_every_other_state_can_buy(shop: Shop, state: str) -> None:
    line = shop.seed(state=state)
    shop.fund(line, PRICE)
    shop.buy(line)
    assert len(shop.buckets()) == 1


def test_a_purchase_does_not_touch_the_lines_state(shop: Shop, engine: Engine) -> None:
    line = shop.seed(state="out_of_data")
    shop.fund(line, PRICE)
    shop.buy(line)
    with Session(engine) as session:
        assert session.scalar(select(Line.state)) == "out_of_data"  # the rating job brings it back


def test_the_clock_must_carry_a_timezone(shop: Shop) -> None:
    line = shop.seed()
    with pytest.raises(ValueError, match="timezone"):
        buy_offer(
            shop.scope,
            line_id=line.line_id,
            kind=OfferKind.PLAN,
            offer_id=line.plan_id,
            reference="x",
            now=T0.replace(tzinfo=None),
            vat_rate_bps=VAT,
        )


# --- renewal -------------------------------------------------------------------------------------


def _renew(shop: Shop, line: SeededLine):  # type: ignore[no-untyped-def]
    return renew_plan_if_covered(shop.scope, line_id=line.line_id, now=T0, vat_rate_bps=VAT)


def _spent(engine: Engine, line: SeededLine) -> None:
    with Session(engine) as session, session.begin():
        add_bucket(session, line, 500, used=500)


@pytest.mark.parametrize("state", ["out_of_data", "expired"])
def test_a_covered_plan_is_bought_again_for_a_line_that_ran_out(
    shop: Shop, engine: Engine, state: str
) -> None:
    line = shop.seed(state=state)
    _spent(engine, line)
    shop.fund(line, 120_000)

    result = _renew(shop, line)

    assert result is not None
    assert (result.price_kobo, result.balance_kobo) == (100_000, 20_000)
    assert len(shop.buckets()) == 2
    assert [k for k, _, _ in shop.entries()] == ["top_up", "purchase", "vat"]
    assert shop.entries()[1][2].startswith("auto-renew-")


def test_renewal_happens_once_because_the_new_bucket_has_allowance(
    shop: Shop, engine: Engine
) -> None:
    line = shop.seed(state="out_of_data")
    _spent(engine, line)
    shop.fund(line, 500_000)

    assert _renew(shop, line) is not None
    assert _renew(shop, line) is None
    assert len(shop.buckets()) == 2
    assert shop.balance(line) == 400_000


def test_no_renewal_when_the_wallet_falls_short(shop: Shop, engine: Engine) -> None:
    line = shop.seed(state="out_of_data")
    _spent(engine, line)
    shop.fund(line, 99_999)
    assert _renew(shop, line) is None
    assert len(shop.buckets()) == 1


@pytest.mark.parametrize("state", ["active", "awaiting_activation", "suspended", "terminated"])
def test_only_a_line_that_ran_out_is_renewed(shop: Shop, engine: Engine, state: str) -> None:
    line = shop.seed(state=state)
    _spent(engine, line)
    shop.fund(line, 500_000)
    assert _renew(shop, line) is None


def test_no_renewal_while_allowance_is_left_or_on_its_way(shop: Shop, engine: Engine) -> None:
    line = shop.seed(state="out_of_data")
    with Session(engine) as session, session.begin():
        add_bucket(session, line, 500, used=500)
        add_bucket(
            session, line, 1_000, starts=T0 + DAY, expires=T0 + 30 * DAY
        )  # bought, not started
    shop.fund(line, 500_000)
    assert _renew(shop, line) is None


def test_no_renewal_of_a_retired_plan(shop: Shop, engine: Engine) -> None:
    line = shop.seed(state="out_of_data")
    _spent(engine, line)
    shop.fund(line, 500_000)
    with Session(engine) as session, session.begin():
        session.get(PlanRow, line.plan_id).state = "retired"  # type: ignore[union-attr]
    assert _renew(shop, line) is None


def test_no_renewal_for_a_line_with_no_wallet_or_no_line(shop: Shop, engine: Engine) -> None:
    line = shop.seed(state="out_of_data")
    _spent(engine, line)
    assert _renew(shop, line) is None
    assert renew_plan_if_covered(shop.scope, line_id=999, now=T0, vat_rate_bps=VAT) is None
    with Session(engine) as session:
        assert session.scalar(select(func.count(LedgerEntry.entry_id))) == 0
