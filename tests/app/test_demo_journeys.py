"""The four demo journeys (PRODUCT_RULES.md, Demo journeys) through the real routes, on SQLite.

Each test is one journey as the screens would drive it: a signed-in staff member, or RatelPay with
the proxy's key, over HTTP; the rating job as the timer would run it; a fake RatelLink. Nothing
here is lab proof: whether a phone gets data is the lab's to show. What this guards is that the
pieces still fit together, so a change to one route cannot quietly break the demo.

Creating a line takes a SIM and a number with raw SQL that needs PostgreSQL (see
test_line_sales_postgres_integration.py), so each journey starts from a line in the database.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.bss_lines.api.lines import get_client
from app.bss_lines.models.lines import Customer, Line
from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_money.repositories.sql import SqlRatingRepository
from app.bss_money.services.line_control import LifecycleLineControl
from app.bss_money.services.rating_job import RatingRun, run_rating
from app.config import Settings
from app.main import create_app
from tests.app.bss_lines.desk_helpers import PASSWORD, add_staff
from tests.app.bss_lines.fakes import FakeRatelLinkClient
from tests.app.bss_money.rating_data import (
    T0,
    SeededLine,
    add_bucket,
    add_bundle,
    add_usage,
    seed_line,
)
from tests.app.bss_money.sqlite_database import sqlite_engine
from tests.app.bss_money.vouchers_data import issue

PAY_KEY = "test-pay-key-not-a-real-key"
FACE = 120_000  # a voucher; the test plan costs 100,000


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.passwords._N", 2**10)


class Counter:
    """Everything one journey needs: the app, two staff, a fake RatelLink, the rating job."""

    def __init__(self, path: str) -> None:
        self.engine: Engine = sqlite_engine(path)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.network = FakeRatelLinkClient()
        self.app: FastAPI = create_app(Settings(staff_cookie_secure=False, pay_api_key=PAY_KEY))  # type: ignore[arg-type]
        self.app.state.session_factory = self.factory
        self.app.state.clock = lambda: T0
        self.app.dependency_overrides[get_client] = lambda: self.network
        self.agent = self._sign_in("agent")
        self.admin = self._sign_in("admin")
        self.pay = TestClient(self.app)

    def _sign_in(self, role: str) -> TestClient:
        email = add_staff(self.factory, role)
        client = TestClient(self.app)
        client.headers["x-ratel-desk"] = "1"
        response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return client

    def new_line(self, state: str = "awaiting_activation") -> SeededLine:
        with self.factory() as session, session.begin():
            return seed_line(session, state=state)

    def voucher(self, face: int = FACE) -> tuple[str, str]:
        with self.factory() as session, session.begin():
            [card] = issue(session, face=face)
        return card.card_number, card.pin

    def redeem(self, line: SeededLine, card: tuple[str, str]):  # type: ignore[no-untyped-def]
        return self.pay.post(
            "/v1/pay/vouchers/redeem",
            json={"msisdn": f"23480000{line.line_id:05d}", "card_number": card[0], "pin": card[1]},
            headers={"Authorization": f"Bearer {PAY_KEY}"},
        )

    def buy(self, line: SeededLine, kind: str, offer_id: int, key: str):  # type: ignore[no-untyped-def]
        return self.agent.post(
            f"/v1/lines/{line.line_id}/purchases",
            json={"offer_kind": kind, "offer_id": offer_id},
            headers={"Idempotency-Key": key},
        )

    def activate(self, line: SeededLine, key: str):  # type: ignore[no-untyped-def]
        return self.agent.post(
            f"/v1/lines/{line.line_id}/activate", json={}, headers={"Idempotency-Key": key}
        )

    def care(self, client: TestClient, action: str, line: SeededLine, key: str):  # type: ignore[no-untyped-def]
        return client.post(
            f"/v1/lines/{line.line_id}/{action}",
            json={"reason": "customer_request"},
            headers={"Idempotency-Key": key},
        )

    def line(self, line: SeededLine) -> dict:  # type: ignore[type-arg]
        return self.agent.get(f"/v1/lines/{line.line_id}").json()  # type: ignore[no-any-return]

    def run_rating_job(self) -> RatingRun:
        @contextmanager
        def scope() -> Iterator[SqlRatingRepository]:
            with Session(self.engine) as session, session.begin():
                yield SqlRatingRepository(session)

        @contextmanager
        def lines_scope() -> Iterator[SqlLinesRepository]:
            with Session(self.engine) as session:
                yield SqlLinesRepository(session)

        return run_rating(scope, LifecycleLineControl(lines_scope, self.network), now=T0)


@pytest.fixture
def counter(tmp_path: Path) -> Iterator[Counter]:
    counter = Counter(str(tmp_path / "journey.db"))
    yield counter
    counter.engine.dispose()


def test_journey_1_buy_and_activate_a_line(counter: Counter) -> None:
    line = counter.new_line()
    assert counter.line(line)["state"] == "awaiting_activation"

    # Nothing is paid yet: the network is not touched.
    assert counter.activate(line, "a-1").status_code == 409
    assert counter.network.calls == []

    # The customer pays with a voucher, and staff buy the plan from the wallet.
    assert counter.redeem(line, counter.voucher()).json() == {
        "amount_kobo": FACE,
        "balance_kobo": FACE,
    }
    bought = counter.buy(line, "plan", line.plan_id, "buy-1")
    assert bought.status_code == 200
    assert bought.json()["price_kobo"] == 100_000
    assert bought.json()["balance_kobo"] == FACE - 100_000

    activated = counter.activate(line, "a-2")
    assert activated.status_code == 200
    assert activated.json()["state"] == "active"
    assert [c.endpoint for c in counter.network.calls] == ["/activate"]

    # What the screens then show agrees.
    assert counter.line(line)["state"] == "active"
    listed = counter.agent.get("/v1/lines", params={"state": "active"}).json()
    assert [row["line_id"] for row in listed["lines"]] == [line.line_id]
    history = counter.agent.get(f"/v1/lines/{line.line_id}/history").json()
    assert history["entries"][0]["to_state"] == "active"
    assert history["entries"][0]["actor"].startswith("staff:")
    wallet = counter.agent.get(f"/v1/lines/{line.line_id}/wallet").json()
    assert wallet["balance_kobo"] == wallet["ledger_sum_kobo"] == FACE - 100_000
    ledger = counter.agent.get("/v1/ledger", params={"line_id": line.line_id}).json()
    assert {e["kind"] for e in ledger["entries"]} == {"top_up", "purchase", "vat"}


def test_journey_1_for_a_customer_whose_identity_an_admin_has_not_yet_verified(
    counter: Counter,
) -> None:
    line = counter.new_line()
    with counter.factory() as session, session.begin():
        customer_id = session.get(Line, line.line_id).customer_id  # type: ignore[union-attr]
        session.get(Customer, customer_id).kyc_status = "pending"  # type: ignore[union-attr]
    counter.redeem(line, counter.voucher())
    assert counter.buy(line, "plan", line.plan_id, "buy-1").status_code == 200

    # Paid for, but the customer is not verified: customer care cannot go further.
    refused = counter.activate(line, "a-1")
    assert refused.status_code == 409
    assert "KYC" in refused.json()["error"]["message"]
    assert (
        counter.agent.post(
            f"/v1/customers/{customer_id}/kyc", json={"status": "verified", "reason": "seen"}
        ).status_code
        == 403
    )

    # An admin verifies, and the same sale goes through.
    verified = counter.admin.post(
        f"/v1/customers/{customer_id}/kyc",
        json={"status": "verified", "reason": "documents checked"},
    )
    assert verified.json()["kyc_status"] == "verified"
    assert counter.activate(line, "a-2").json()["state"] == "active"
    history = counter.agent.get(f"/v1/customers/{customer_id}/history").json()
    assert [e["action"] for e in history["entries"]] == ["kyc_verified"]


def test_journey_2_top_up_with_a_voucher(counter: Counter) -> None:
    line = counter.new_line(state="active")
    card = counter.voucher()

    first = counter.redeem(line, card)
    assert (first.status_code, first.json()["balance_kobo"]) == (200, FACE)

    # The same card again credits nothing more: the wallet does not move.
    assert counter.redeem(line, card).json()["balance_kobo"] == FACE
    wallet = counter.agent.get(f"/v1/lines/{line.line_id}/wallet").json()
    assert wallet == {"line_id": line.line_id, "balance_kobo": FACE, "ledger_sum_kobo": FACE}

    summary = counter.agent.get("/v1/wallet/summary").json()
    assert (summary["total_balance_kobo"], summary["wallets_with_balance"]) == (FACE, 1)


def test_journey_3_run_out_of_data_buy_a_bundle_and_be_restored(counter: Counter) -> None:
    with counter.factory() as session, session.begin():
        line = seed_line(session, state="active")
        add_bucket(session, line, 1_000)
        add_usage(session, line, up=500, down=1_000)  # more than the allowance
        bundle_id = add_bundle(session, price_kobo=30_000, data_bytes=5_000)

    # The job finds the allowance used up and slows the line (the plan's choice).
    first = counter.run_rating_job()
    assert first.failures == 0
    assert counter.line(line)["state"] == "out_of_data"
    [slowed] = counter.network.calls
    assert (slowed.endpoint, slowed.mode) == ("/data", "slow")  # type: ignore[union-attr]

    # The customer tops up, and staff buy a bundle. The route does not restore the line itself.
    counter.redeem(line, counter.voucher())
    assert counter.buy(line, "bundle", bundle_id, "buy-b").status_code == 200
    assert counter.line(line)["state"] == "out_of_data"

    # The next run sees the new allowance and gives full speed back.
    second = counter.run_rating_job()
    assert (second.lines_restored, second.failures) == (1, 0)
    assert counter.line(line)["state"] == "active"
    restored = counter.network.calls[-1]
    assert (restored.endpoint, restored.mode) == ("/data", "full")  # type: ignore[union-attr]

    # And it is not restored twice.
    assert counter.run_rating_job().lines_restored == 0


def test_journey_4_suspend_a_line_with_a_reason_and_reinstate_it(counter: Counter) -> None:
    line = counter.new_line(state="active")

    suspended = counter.care(counter.agent, "suspend", line, "s-1")
    assert (suspended.status_code, suspended.json()["state"]) == (200, "suspended")
    assert suspended.json()["state_before_suspension"] == "active"

    reinstated = counter.care(counter.agent, "reinstate", line, "r-1")
    assert (reinstated.status_code, reinstated.json()["state"]) == (200, "active")
    assert reinstated.json()["state_before_suspension"] is None

    history = counter.agent.get(f"/v1/lines/{line.line_id}/history").json()
    assert [(e["from_state"], e["to_state"]) for e in history["entries"]] == [
        ("suspended", "active"),
        ("active", "suspended"),
    ]
    assert all(e["reason"] == "customer_request" for e in history["entries"])


def test_only_an_admin_ends_a_line_for_good(counter: Counter) -> None:
    line = counter.new_line(state="active")
    assert counter.care(counter.agent, "terminate", line, "t-1").status_code == 403
    assert counter.line(line)["state"] == "active"
    assert counter.care(counter.admin, "terminate", line, "t-2").json()["state"] == "terminated"
