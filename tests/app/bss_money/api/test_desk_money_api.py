"""RatelDesk's money screens over HTTP on SQLite: wallet, ledger, usage, totals, the front page.

The clock is fixed at 2026-10-28 12:00 UTC (13:00 in Lagos), so "today" is 2026-10-28 Lagos time,
which starts at 2026-10-27 23:00 UTC.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bss_lines.models.lines import Customer, Line, LineAudit, Number, Plan, Sim
from app.bss_money.models.ledger import LedgerEntry, Wallet
from app.bss_money.models.rating import UsageRating
from app.db import Base
from app.meter_api.models import UsageRecordModel
from tests.app.bss_lines.desk_helpers import add_staff, make_app, signed_in

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
LAGOS_MIDNIGHT = datetime(2026, 10, 27, 23, 0, tzinfo=UTC)  # 00:00 on 28 October in Lagos


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
    _seed(factory)
    yield factory


def _customer(n: int, kyc: str, created: datetime) -> Customer:
    return Customer(
        name=f"Person {n}",
        phone=f"23480000000{n:02d}",
        email=f"p{n}@example.test",
        id_type="NIN",
        id_number=f"0000000{n:04d}",
        address="1 Test Street",
        kyc_status=kyc,
        created_at=created,
    )


def _seed(factory: sessionmaker[Session]) -> None:
    """Line 1 (active) and line 2 (out of data); a wallet and entries for line 1 only."""
    with factory() as s, s.begin():
        plan = Plan(
            name="Weekly",
            price_kobo=100_000,
            validity_days=7,
            data_bytes=1_000_000,
            speed_ul_mbps=1,
            speed_dl_mbps=1,
            channels="data",
            on_exhaustion="stop",
            state="on_sale",
        )
        owners = [_customer(1, "verified", NOW - timedelta(days=9))]
        owners.append(_customer(2, "verified", NOW - timedelta(days=8)))
        s.add_all([plan, *owners])
        s.flush()
        for n, state in enumerate(["active", "out_of_data"], start=1):
            s.add(
                Sim(
                    iccid=f"89234000000000000{n}",
                    imsi=f"62100000000000{n}",
                    batch="b",
                    state="in_use",
                )
            )
            s.add(Number(msisdn=f"23480000100{n}0", state="in_use"))
            s.flush()
            s.add(
                Line(
                    customer_id=owners[n - 1].customer_id,
                    iccid=f"89234000000000000{n}",
                    imsi=f"62100000000000{n}",
                    msisdn=f"23480000100{n}0",
                    plan_id=plan.plan_id,
                    state=state,
                )
            )
        s.flush()
        s.add(Wallet(line_id=1, balance_kobo=140_000))
        s.flush()
        entries = [
            # (kind, amount, reference, when)
            ("top_up", 200_000, "pay-1", NOW - timedelta(days=2)),
            ("top_up", 50_000, "pay-2", LAGOS_MIDNIGHT + timedelta(minutes=30)),  # today, Lagos
            ("top_up", 30_000, "pay-3", LAGOS_MIDNIGHT - timedelta(minutes=30)),  # yesterday
            ("purchase", -100_000, "buy-1", NOW - timedelta(hours=1)),
            ("vat", -7_500, "vat-1", NOW - timedelta(hours=1)),
            ("correction", -32_500, "fix-1", NOW - timedelta(days=30)),  # outside the 7 days
        ]
        for kind, amount, ref, when in entries:
            s.add(
                LedgerEntry(
                    line_id=1, amount_kobo=amount, kind=kind, reference=ref, created_at=when
                )
            )
        s.add(
            LineAudit(
                line_id=2,
                from_state="active",
                to_state="out_of_data",
                actor="system",
                reason="allowance_used_up",
                created_at=NOW - timedelta(days=1),
            )
        )


@pytest.fixture
def care(factory: sessionmaker[Session]) -> TestClient:
    return signed_in(make_app(factory, clock=lambda: NOW), add_staff(factory, "agent"))


# --- a line's wallet ---------------------------------------------------------------------------


def test_a_wallet_shows_its_balance_next_to_the_sum_of_its_entries(care: TestClient) -> None:
    body = care.get("/v1/lines/1/wallet").json()
    assert body == {"line_id": 1, "balance_kobo": 140_000, "ledger_sum_kobo": 140_000}


def test_a_line_without_a_wallet_has_zero_for_both(care: TestClient) -> None:
    assert care.get("/v1/lines/2/wallet").json() == {
        "line_id": 2,
        "balance_kobo": 0,
        "ledger_sum_kobo": 0,
    }


def test_a_balance_that_disagrees_with_the_entries_is_shown_not_hidden(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    with factory() as s, s.begin():
        s.get(Wallet, 1).balance_kobo = 1
    body = care.get("/v1/lines/1/wallet").json()
    assert (body["balance_kobo"], body["ledger_sum_kobo"]) == (1, 140_000)


def test_the_wallet_of_an_unknown_line_is_404(care: TestClient) -> None:
    response = care.get("/v1/lines/99/wallet")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- the ledger --------------------------------------------------------------------------------


def test_the_ledger_is_newest_entry_first_with_the_number_and_whole_kobo(care: TestClient) -> None:
    body = care.get("/v1/ledger").json()
    assert body["total"] == 6
    assert [e["reference"] for e in body["entries"]] == [
        "fix-1",
        "vat-1",
        "buy-1",
        "pay-3",
        "pay-2",
        "pay-1",
    ]
    entry = body["entries"][-1]
    assert entry == {
        "entry_id": 1,
        "line_id": 1,
        "msisdn": "2348000010010",
        "amount_kobo": 200_000,
        "kind": "top_up",
        "reference": "pay-1",
        "created_at": int((NOW - timedelta(days=2)).timestamp()),
    }
    assert all(isinstance(e["amount_kobo"], int) for e in body["entries"])


def test_the_kind_filter_narrows_the_page_but_not_the_counts(care: TestClient) -> None:
    body = care.get("/v1/ledger", params={"kind": "top_up"}).json()
    assert body["total"] == 3
    assert {e["kind"] for e in body["entries"]} == {"top_up"}
    assert body["counts"] == {"all": 6, "top_up": 3, "purchase": 1, "vat": 1, "correction": 1}


def test_the_line_filter_narrows_the_ledger_and_the_counts(care: TestClient) -> None:
    assert care.get("/v1/ledger", params={"line_id": 2}).json() == {
        "entries": [],
        "total": 0,
        "counts": {"all": 0},
    }
    assert care.get("/v1/ledger", params={"line_id": 1}).json()["counts"]["all"] == 6


def test_the_ledger_is_paged(care: TestClient) -> None:
    body = care.get("/v1/ledger", params={"page": 2, "page_size": 4}).json()
    assert [e["reference"] for e in body["entries"]] == ["pay-2", "pay-1"]
    assert body["total"] == 6


# --- a line's usage ----------------------------------------------------------------------------


def _usage(
    factory: sessionmaker[Session], imsi: str, starts: list[datetime], rated: int = 0
) -> None:
    with factory() as s, s.begin():
        rows = [
            UsageRecordModel(
                imsi=imsi,
                period_start=start,
                period_end=start + timedelta(minutes=5),
                bytes_up=10,
                bytes_down=20,
            )
            for start in starts
        ]
        s.add_all(rows)
        s.flush()
        for row in rows[:rated]:
            s.add(
                UsageRating(usage_record_id=row.id, line_id=1, deducted_bytes=30, uncovered_bytes=0)
            )


def _window(start: datetime, end: datetime) -> dict[str, int]:
    return {"from": int(start.timestamp()), "to": int(end.timestamp())}


def test_usage_is_newest_first_with_a_rated_flag_and_no_imsi(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    starts = [NOW - timedelta(minutes=5 * i) for i in range(3, 0, -1)]  # oldest first in the table
    _usage(factory, "621000000000001", starts, rated=2)
    body = care.get("/v1/lines/1/usage", params=_window(NOW - timedelta(hours=1), NOW)).json()
    assert [r["period_start"] for r in body["records"]] == sorted(
        (int(s.timestamp()) for s in starts), reverse=True
    )
    assert [r["rated"] for r in body["records"]] == [False, True, True]
    assert set(body["records"][0]) == {
        "period_start",
        "period_end",
        "bytes_up",
        "bytes_down",
        "rated",
    }
    assert body["next_cursor"] is None
    assert (
        "621000000000001"
        not in care.get("/v1/lines/1/usage", params=_window(NOW - timedelta(hours=1), NOW)).text
    )


def test_usage_of_another_line_never_appears(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    _usage(factory, "621000000000002", [NOW - timedelta(minutes=5)])
    body = care.get("/v1/lines/1/usage", params=_window(NOW - timedelta(hours=1), NOW)).json()
    assert body == {"records": [], "next_cursor": None}


def test_usage_from_and_to_include_their_own_instant(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    edge_a, edge_b = NOW - timedelta(minutes=10), NOW - timedelta(minutes=5)
    _usage(factory, "621000000000001", [edge_a, edge_b, NOW - timedelta(minutes=20)])
    body = care.get("/v1/lines/1/usage", params=_window(edge_a, edge_b)).json()
    assert len(body["records"]) == 2


def test_usage_pages_follow_the_cursor_without_a_gap_or_a_repeat(
    care: TestClient, factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.bss_money.services.desk_reads.USAGE_PAGE", 2)
    starts = [NOW - timedelta(minutes=5 * i) for i in range(1, 6)]
    _usage(factory, "621000000000001", starts)
    window = _window(NOW - timedelta(hours=1), NOW)
    seen: list[int] = []
    cursor = None
    for _ in range(5):
        params = dict(window, **({"cursor": cursor} if cursor else {}))
        body = care.get("/v1/lines/1/usage", params=params).json()
        seen += [r["period_start"] for r in body["records"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted((int(s.timestamp()) for s in starts), reverse=True)


@pytest.mark.parametrize("cursor", ["abc", "-1e99", "99999999999999999999999"])
def test_a_cursor_the_service_did_not_give_out_is_422(care: TestClient, cursor: str) -> None:
    params = dict(_window(NOW - timedelta(hours=1), NOW), cursor=cursor)
    assert care.get("/v1/lines/1/usage", params=params).status_code == 422


def test_usage_needs_both_ends_of_the_window(care: TestClient) -> None:
    assert care.get("/v1/lines/1/usage", params={"from": 0}).status_code == 422


def test_usage_of_an_unknown_line_is_404(care: TestClient) -> None:
    assert care.get("/v1/lines/99/usage", params={"from": 0, "to": 1}).status_code == 404


# --- the wallet summary ------------------------------------------------------------------------


def test_the_summary_counts_a_lagos_day_not_a_utc_day(care: TestClient) -> None:
    body = care.get("/v1/wallet/summary").json()
    assert [d["date"] for d in body["daily"]] == [
        "2026-10-22",
        "2026-10-23",
        "2026-10-24",
        "2026-10-25",
        "2026-10-26",
        "2026-10-27",
        "2026-10-28",
    ]
    by_date = {d["date"]: d for d in body["daily"]}
    # 00:30 Lagos on the 28th is 23:30 UTC on the 27th: it belongs to the 28th.
    assert by_date["2026-10-28"] == {"date": "2026-10-28", "in_kobo": 50_000, "out_kobo": 107_500}
    assert by_date["2026-10-27"]["in_kobo"] == 30_000
    assert by_date["2026-10-26"]["in_kobo"] == 200_000
    assert body["entries_today"] == 3  # pay-2, buy-1, vat-1
    assert body["total_balance_kobo"] == 140_000
    assert body["wallets_with_balance"] == 1


# --- the front page ----------------------------------------------------------------------------


def test_the_dashboard_counts_lines_customers_and_topups(care: TestClient) -> None:
    body = care.get("/v1/dashboard").json()
    assert body["line_counts"] == {
        "all": 2,
        "awaiting_activation": 0,
        "active": 1,
        "out_of_data": 1,
        "expired": 0,
        "suspended": 0,
        "terminated": 0,
    }
    assert body["kyc_pending"] == 0
    # Only `top_up` entries count as top-ups: the purchase and the VAT do not.
    assert body["topups_today_kobo"] == 50_000
    assert body["topups_yesterday_kobo"] == 30_000
    assert [d["amount_kobo"] for d in body["topups_last_7_days"]] == [
        0,
        0,
        0,
        0,
        200_000,
        30_000,
        50_000,
    ]
    assert body["topups_last_7_days"][-1]["date"] == "2026-10-28"


def test_money_in_that_is_not_a_top_up_is_not_counted_as_one(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    with factory() as s, s.begin():
        s.add(
            LedgerEntry(
                line_id=1,
                amount_kobo=9_000,
                kind="correction",
                reference="fix-2",
                created_at=LAGOS_MIDNIGHT + timedelta(hours=1),
            )
        )
    assert care.get("/v1/dashboard").json()["topups_today_kobo"] == 50_000


def test_a_line_out_of_data_needs_attention_since_it_ran_out(care: TestClient) -> None:
    attention = care.get("/v1/dashboard").json()["attention"]
    assert attention == [
        {
            "issue": "out_of_data",
            "customer_id": 2,
            "line_id": 2,
            "customer_name": "Person 2",
            "msisdn": "2348000010020",
            "since": int((NOW - timedelta(days=1)).timestamp()),
        }
    ]


def test_attention_lists_the_longest_waiting_first_and_at_most_twenty(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    with factory() as s, s.begin():
        s.add_all(_customer(10 + i, "pending", NOW - timedelta(days=5, hours=i)) for i in range(25))
    body = care.get("/v1/dashboard").json()
    assert body["kyc_pending"] == 25
    waits = [a["since"] for a in body["attention"]]
    assert len(waits) == 20
    assert waits == sorted(waits)
    kinds = {a["issue"] for a in body["attention"]}
    assert kinds == {"pending_kyc"}  # the pending customers have waited longer than the one line
    assert all(a["line_id"] is None and a["msisdn"] is None for a in body["attention"])


def test_a_pending_customer_with_a_line_points_at_it(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    with factory() as s, s.begin():
        s.get(Customer, 1).kyc_status = "pending"
    items = [
        a for a in care.get("/v1/dashboard").json()["attention"] if a["issue"] == "pending_kyc"
    ]
    assert items[0]["line_id"] == 1
    assert items[0]["msisdn"] == "2348000010010"


# --- who may read ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/v1/lines/1/wallet",
        "/v1/lines/1/usage?from=0&to=1",
        "/v1/ledger",
        "/v1/wallet/summary",
        "/v1/dashboard",
    ],
)
def test_these_routes_refuse_a_caller_who_is_not_signed_in(
    factory: sessionmaker[Session], path: str
) -> None:
    anonymous = TestClient(make_app(factory))
    assert anonymous.get(path).status_code == 401
    assert anonymous.get("/v1/lines/1/usage?from=bad&to=bad").status_code == 401
