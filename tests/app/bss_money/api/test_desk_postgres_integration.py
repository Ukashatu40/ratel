"""RatelDesk's reads, the purchase route and the payment check on a real PostgreSQL.

The unit tests prove the logic on SQLite. This file proves what only the real database can: the
queries (`ILIKE ... ESCAPE`, conditional sums, the correlated count, `EXISTS`), the migration
matching the models, and what two requests at the same moment do to a wallet and a line.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.orm import Session

from tests.app.bss_money.api.desk_postgres import Desk
from tests.app.bss_money.postgres import Database
from tests.app.bss_money.rating_data import add_usage

pytestmark = pytest.mark.integration

PRICE = 100_000  # the seeded plan


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.passwords._N", 2**10)


@pytest.fixture
def desk(db: Database) -> Iterator[Desk]:
    yield Desk(db)


def test_the_desk_reads_answer_on_postgres(desk: Desk) -> None:
    one, two, three = desk.lines(3)
    with Session(desk.db.engine) as session, session.begin():
        from app.bss_lines.models.lines import Line

        session.get(Line, two.line_id).state = "out_of_data"  # type: ignore[union-attr]
        session.get(Line, three.line_id).state = "suspended"  # type: ignore[union-attr]
        add_usage(session, one, up=100, down=200)
    desk.db.post(one.line_id, 250_000, "top_up", "pay-1")
    desk.db.post(one.line_id, -50_000, "purchase", "buy-1")

    lines = desk.agent.get("/v1/lines", params={"q": "Customer 2"}).json()
    assert [r["line_id"] for r in lines["lines"]] == [two.line_id]
    assert lines["counts"]["all"] == 1
    # A percent sign or an underscore in a search matches itself, as the unit tests say.
    assert desk.agent.get("/v1/lines", params={"q": "%"}).json()["total"] == 0
    assert desk.agent.get("/v1/lines", params={"q": "_"}).json()["total"] == 0
    everything = desk.agent.get("/v1/lines").json()
    assert everything["counts"] == {
        "all": 3,
        "awaiting_activation": 0,
        "active": 1,
        "out_of_data": 1,
        "expired": 0,
        "suspended": 1,
        "terminated": 0,
    }
    exact_imsi = desk.agent.get("/v1/lines", params={"q": one.imsi}).json()
    assert [r["line_id"] for r in exact_imsi["lines"]] == [one.line_id]

    customers = desk.agent.get("/v1/customers", params={"kyc_status": "verified"}).json()
    assert customers["total"] == 3
    assert {c["lines_count"] for c in customers["customers"]} == {1}

    ledger = desk.agent.get("/v1/ledger", params={"line_id": one.line_id}).json()
    assert [e["amount_kobo"] for e in ledger["entries"]] == [-50_000, 250_000]
    assert ledger["counts"] == {"all": 2, "top_up": 1, "purchase": 1}
    wallet = desk.agent.get(f"/v1/lines/{one.line_id}/wallet").json()
    assert wallet["balance_kobo"] == wallet["ledger_sum_kobo"] == 200_000

    summary = desk.agent.get("/v1/wallet/summary").json()
    assert (summary["total_balance_kobo"], summary["wallets_with_balance"]) == (200_000, 1)
    assert summary["daily"][-1]["in_kobo"] == 250_000
    assert summary["daily"][-1]["out_kobo"] == 50_000

    dashboard = desk.agent.get("/v1/dashboard").json()
    assert dashboard["line_counts"]["out_of_data"] == 1
    assert dashboard["topups_today_kobo"] == 250_000
    assert [a["issue"] for a in dashboard["attention"]] == ["out_of_data"]

    usage = desk.agent.get(
        f"/v1/lines/{one.line_id}/usage", params={"from": 0, "to": 4_000_000_000}
    ).json()
    assert [(r["bytes_up"], r["bytes_down"], r["rated"]) for r in usage["records"]] == [
        (100, 200, False)
    ]

    assert desk.agent.get(f"/v1/lines/{one.line_id}/history").json() == {"entries": [], "total": 0}


def test_simultaneous_purchases_cannot_overdraw_a_wallet(desk: Desk) -> None:
    [line] = desk.lines()
    desk.db.post(line.line_id, 250_000, "top_up", "pay-1")  # pays for two plans, not three

    with ThreadPoolExecutor(max_workers=10) as pool:
        replies = list(pool.map(lambda i: desk.buy(line, f"k-{i}"), range(10)))

    codes = sorted(r.json().get("error", {}).get("code", "bought") for r in replies)
    assert codes == ["bought"] * 2 + ["insufficient_funds"] * 8
    wallet = desk.agent.get(f"/v1/lines/{line.line_id}/wallet").json()
    assert wallet["balance_kobo"] == wallet["ledger_sum_kobo"]
    assert wallet["balance_kobo"] == 250_000 - 2 * PRICE
    assert desk.db.scalar("SELECT count(*) FROM allowance_bucket") == 2
    assert desk.db.scalar("SELECT count(*) FROM ledger_entry WHERE kind = 'vat'") == 2


def test_the_same_key_sent_at_once_buys_exactly_once(desk: Desk) -> None:
    [line] = desk.lines()
    desk.db.post(line.line_id, 250_000, "top_up", "pay-1")

    with ThreadPoolExecutor(max_workers=10) as pool:
        replies = list(pool.map(lambda _: desk.buy(line, "same-key"), range(10)))

    assert {r.status_code for r in replies} == {200}
    assert sorted(r.json()["replayed"] for r in replies) == [False] + [True] * 9
    assert desk.db.scalar("SELECT count(*) FROM allowance_bucket") == 1
    assert desk.db.scalar("SELECT count(*) FROM ledger_entry WHERE kind = 'purchase'") == 1
    wallet = desk.agent.get(f"/v1/lines/{line.line_id}/wallet").json()
    assert wallet["balance_kobo"] == 250_000 - PRICE


def test_activation_needs_a_paid_plan_on_postgres(desk: Desk) -> None:
    [line] = desk.lines(state="awaiting_activation")
    assert desk.activate(line, "a-1").status_code == 409
    assert desk.network.calls == []

    desk.db.post(line.line_id, 150_000, "top_up", "pay-1")
    assert desk.buy(line, "buy-1").status_code == 200
    activated = desk.activate(line, "a-2")
    assert (activated.status_code, activated.json()["state"]) == (200, "active")
    assert [c.endpoint for c in desk.network.calls] == ["/activate"]


def test_an_allowance_of_another_line_does_not_activate_this_one(desk: Desk) -> None:
    paid, unpaid = desk.lines(2, state="awaiting_activation")
    desk.db.post(paid.line_id, 150_000, "top_up", "pay-1")
    assert desk.buy(paid, "buy-1").status_code == 200
    assert desk.activate(unpaid, "a-1").status_code == 409


def test_two_activations_at_once_leave_one_audit_entry(desk: Desk) -> None:
    [line] = desk.lines(state="awaiting_activation")
    desk.db.post(line.line_id, 150_000, "top_up", "pay-1")
    assert desk.buy(line, "buy-1").status_code == 200

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda i: desk.activate(line, f"a-{i}"), range(2)))

    assert sorted(r.status_code for r in replies) == [200, 409]
    assert desk.db.scalar("SELECT count(*) FROM line_audit") == 1
    assert len(desk.network.calls) == 1


def test_terminating_retires_the_sim_on_postgres(desk: Desk) -> None:
    [line] = desk.lines()
    response = desk.admin.post(
        f"/v1/lines/{line.line_id}/terminate",
        json={"reason": "fraud"},
        headers={"Idempotency-Key": "t-1"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "terminated"
    assert desk.db.scalar("SELECT state FROM sim") == "retired"


def test_two_admins_deciding_one_customer_at_once_take_turns(desk: Desk) -> None:
    [line] = desk.lines()
    customer_id = desk.db.scalar("SELECT customer_id FROM customer")
    desk.db.run("UPDATE customer SET kyc_status = 'pending'")

    def decide(status: str):  # type: ignore[no-untyped-def]
        return desk.admin.post(
            f"/v1/customers/{customer_id}/kyc", json={"status": status, "reason": f"to {status}"}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(decide, ["verified", "rejected"]))

    codes = sorted(r.status_code for r in replies)
    final = desk.db.scalar("SELECT kyc_status FROM customer")
    actions = [
        a
        for (a,) in desk.db.rows(
            "SELECT action FROM customer_audit WHERE action <> 'registered' ORDER BY id"
        )
    ]
    # Either verify won and reject was refused, or reject won and verify then went through.
    assert codes in ([200, 409], [200, 200])
    assert len(actions) == codes.count(200)
    assert final == {"kyc_verified": "verified", "kyc_rejected": "rejected"}[actions[-1]]
    if codes == [200, 409]:
        assert final == "verified"
    _ = line


def test_the_customer_history_reads_on_postgres(desk: Desk) -> None:
    desk.lines()
    customer_id = desk.db.scalar("SELECT customer_id FROM customer")
    desk.db.run("UPDATE customer SET kyc_status = 'pending'")
    assert (
        desk.admin.post(
            f"/v1/customers/{customer_id}/kyc", json={"status": "verified", "reason": "seen"}
        ).status_code
        == 200
    )
    history = desk.agent.get(f"/v1/customers/{customer_id}/history").json()
    assert history["total"] == 1
    assert history["entries"][0]["action"] == "kyc_verified"


def test_the_customer_audit_migration_rolls_back_only_while_empty(desk: Desk) -> None:
    desk.lines()
    customer_id = desk.db.scalar("SELECT customer_id FROM customer")
    desk.db.run(
        "INSERT INTO customer_audit (customer_id, action, actor, reason) "
        "VALUES (:customer_id, 'registered', 'staff:1', 'test')",
        customer_id=customer_id,
    )
    with pytest.raises(RuntimeError, match="refusing to drop customer_audit"):
        desk.db.alembic("downgrade", "27c13d2d79bc")
    desk.db.run("DELETE FROM customer_audit")
    desk.db.alembic("downgrade", "27c13d2d79bc")
    assert desk.db.scalar("SELECT to_regclass('customer_audit')") is None
    desk.db.alembic("upgrade", "head")
    assert desk.db.scalar("SELECT to_regclass('customer_audit')") is not None
