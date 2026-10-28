"""Buying a plan or a bundle for a line over HTTP on SQLite, as a signed-in staff member."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bss_lines.models.lines import Bundle, Customer, Line, Number, Plan, Sim
from app.bss_money.models.allowance import AllowanceBucket
from app.bss_money.models.ledger import LedgerEntry, Wallet
from app.db import Base
from tests.app.bss_lines.desk_helpers import add_staff, make_app, signed_in

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.passwords._N", 2**10)


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s, s.begin():
        customer = Customer(
            name="Ada Test",
            phone="2348000000011",
            email="ada@example.test",
            id_type="NIN",
            id_number="00000000000",
            address="1 Test Street",
            kyc_status="verified",
        )
        plan = Plan(
            name="Weekly",
            price_kobo=107_500,
            validity_days=7,
            data_bytes=5_000_000_000,
            speed_ul_mbps=10,
            speed_dl_mbps=20,
            channels="data",
            on_exhaustion="stop",
            state="on_sale",
        )
        s.add_all(
            [
                customer,
                plan,
                Sim(iccid="8923400000000000001", imsi="621000000000001", batch="b", state="in_use"),
                Number(msisdn="2348000010010", state="in_use"),
            ]
        )
        s.add_all(
            [
                Bundle(
                    name="1GB",
                    price_kobo=21_500,
                    data_bytes=1_000_000_000,
                    validity_days=3,
                    channels="data",
                ),
            ]
        )
        s.flush()
        s.add(
            Line(
                customer_id=customer.customer_id,
                iccid="8923400000000000001",
                imsi="621000000000001",
                msisdn="2348000010010",
                plan_id=plan.plan_id,
                state="out_of_data",
            )
        )
        s.flush()
        s.add(Wallet(line_id=1, balance_kobo=200_000))
        s.flush()
        s.add(
            LedgerEntry(
                line_id=1, amount_kobo=200_000, kind="top_up", reference="pay-1", created_at=NOW
            )
        )
    yield factory


@pytest.fixture
def care(factory: sessionmaker[Session]) -> TestClient:
    return signed_in(make_app(factory, clock=lambda: NOW), add_staff(factory, "agent"))


def buy(
    client: TestClient, key: str = "k1", kind: str = "bundle", offer_id: int = 1, line_id: int = 1
):  # type: ignore[no-untyped-def]
    return client.post(
        f"/v1/lines/{line_id}/purchases",
        json={"offer_kind": kind, "offer_id": offer_id},
        headers={"Idempotency-Key": key},
    )


def entries(factory: sessionmaker[Session]) -> dict[str, int]:
    with factory() as s:
        return {
            f"{kind}:{ref}": amount
            for kind, ref, amount in s.execute(
                select(LedgerEntry.kind, LedgerEntry.reference, LedgerEntry.amount_kobo)
            )
        }


def test_buying_a_bundle_debits_the_wallet_with_vat_apart_and_opens_an_allowance(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    response = buy(care)
    assert response.status_code == 200
    body = response.json()
    assert body["price_kobo"] == 21_500
    assert body["net_kobo"] + body["vat_kobo"] == 21_500
    assert body["vat_kobo"] == 1_500  # 7.5% of 20,000 net
    assert body["balance_kobo"] == 200_000 - 21_500
    assert body["valid_to"] == int((NOW + timedelta(days=3)).timestamp())
    assert body["replayed"] is False
    posted = entries(factory)
    assert posted["purchase:desk:k1"] == -20_000
    assert posted["vat:desk:k1"] == -1_500
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(AllowanceBucket)) == 1
        assert s.get(Wallet, 1).balance_kobo == 200_000 - 21_500


def test_buying_a_plan_works_the_same_way(care: TestClient) -> None:
    response = buy(care, "k-plan", "plan", 1)
    assert response.status_code == 200
    assert response.json()["price_kobo"] == 107_500


def test_a_repeat_with_the_same_key_returns_the_first_purchase_and_charges_nothing(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    first = buy(care).json()
    again = buy(care)
    assert again.status_code == 200
    assert again.json()["replayed"] is True
    assert again.json()["price_kobo"] == first["price_kobo"]
    assert again.json()["balance_kobo"] == first["balance_kobo"]
    with factory() as s:
        assert s.get(Wallet, 1).balance_kobo == 200_000 - 21_500
        assert s.scalar(select(func.count()).select_from(AllowanceBucket)) == 1


def test_the_same_key_for_a_different_price_is_refused(care: TestClient) -> None:
    assert buy(care, "same").status_code == 200
    other = buy(care, "same", "plan", 1)
    assert other.status_code == 409
    assert "different purchase" in other.json()["error"]["message"]


def test_a_wallet_that_does_not_cover_the_price_is_refused_and_unchanged(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    assert buy(care, "a", "plan", 1).status_code == 200  # 107,500 of 200,000
    refused = buy(care, "b", "plan", 1)  # 92,500 left
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "insufficient_funds"
    assert "15000 kobo short" in refused.json()["error"]["message"]
    with factory() as s:
        assert s.get(Wallet, 1).balance_kobo == 92_500


@pytest.mark.parametrize("state", ["suspended", "terminated"])
def test_a_suspended_or_terminated_line_cannot_buy(
    care: TestClient, factory: sessionmaker[Session], state: str
) -> None:
    with factory() as s, s.begin():
        s.get(Line, 1).state = state
    response = buy(care)
    assert response.status_code == 409
    assert entries(factory) == {"top_up:pay-1": 200_000}


def test_an_unknown_offer_is_refused(care: TestClient) -> None:
    assert buy(care, "a", "bundle", 99).status_code == 409
    assert buy(care, "b", "plan", 99).status_code == 409


def test_an_unknown_line_is_404(care: TestClient) -> None:
    assert buy(care, line_id=99).status_code == 404


def test_the_key_is_required_and_the_body_is_checked(care: TestClient) -> None:
    assert (
        care.post("/v1/lines/1/purchases", json={"offer_kind": "bundle", "offer_id": 1}).status_code
        == 422
    )
    for body in (
        {"offer_kind": "voucher", "offer_id": 1},
        {"offer_kind": "plan", "offer_id": 0},
        {"offer_kind": "plan", "offer_id": 1, "price_kobo": 1},
    ):
        response = care.post("/v1/lines/1/purchases", json=body, headers={"Idempotency-Key": "k"})
        assert response.status_code == 422


def test_a_caller_who_is_not_signed_in_is_refused_before_the_body_is_read(
    factory: sessionmaker[Session],
) -> None:
    anonymous = TestClient(make_app(factory))
    response = anonymous.post("/v1/lines/1/purchases", json={"nonsense": True})
    assert response.status_code == 401
