"""Voucher batches in RatelDesk, over HTTP on SQLite (docs/runbooks/voucher-batches.md).

The whole life of a batch: requested, approved, printed (the PDF is the only place the PINs are),
in stock, on sale; then a PIN read back from the printed sheet recharges a line.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.bss_money.models.vouchers import Voucher, VoucherBatch, VoucherEvent
from app.bss_money.repositories.ports import RedemptionRepositories
from app.bss_money.repositories.sql import (
    SqlLedgerRepository,
    SqlLineLookup,
    SqlVoucherRepository,
)
from app.bss_money.services.vouchers import RedeemStatus, redeem_for_number
from app.db import Base
from tests.app.bss_lines.desk_helpers import add_staff, make_app, signed_in
from tests.app.bss_money.rating_data import seed_line
from tests.app.bss_money.sqlite_database import sqlite_engine

NOW = datetime(2026, 11, 27, 13, 5, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.passwords._N", 2**10)


@pytest.fixture
def factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = sqlite_engine(str(tmp_path / "vouchers.db"))
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def admin(factory: sessionmaker[Session]) -> TestClient:
    return signed_in(make_app(factory, clock=lambda: NOW), add_staff(factory, "admin"))


@pytest.fixture
def agent(factory: sessionmaker[Session]) -> TestClient:
    return signed_in(make_app(factory, clock=lambda: NOW), add_staff(factory, "agent"))


def _request(client: TestClient, key: str = "k1", value: int = 50_000, count: int = 3):
    return client.post(
        "/v1/voucher-batches",
        json={"face_value_kobo": value, "card_count": count, "reason": "demo stock"},
        headers={"Idempotency-Key": key},
    )


def _advance(client: TestClient, batch_id: int, to: str):
    return client.post(
        f"/v1/voucher-batches/{batch_id}/advance", json={"state": to, "reason": "checked"}
    )


def sheet_text(pdf: bytes) -> str:
    """The text drawn on the sheet: every content stream, inflated, joined."""
    streams = re.findall(rb"/Filter /FlateDecode >>\nstream\n(.*?)\nendstream", pdf, re.S)
    return "\n".join(zlib.decompress(s).decode("latin-1") for s in streams)


def sheet_cards(pdf: bytes) -> list[tuple[str, str]]:
    """(card number, PIN) pairs as printed, in order."""
    text = sheet_text(pdf)
    pins = re.findall(r"\((\d{4} \d{4} \d{4} \d{2})\) Tj", text)
    numbers = re.findall(r"\((\d{4} \d{4} \d{4} \d{4} \d{4})\) Tj", text)
    return [(n.replace(" ", ""), p.replace(" ", "")) for n, p in zip(numbers, pins, strict=True)]


def _printed_batch(admin: TestClient, count: int = 3) -> tuple[int, bytes]:
    batch_id = _request(admin, count=count).json()["batch"]["batch_id"]
    assert _advance(admin, batch_id, "approved").status_code == 200
    printed = admin.post(f"/v1/voucher-batches/{batch_id}/print")
    assert printed.status_code == 200, printed.text
    return batch_id, printed.content


def test_a_batch_goes_from_request_to_sale_and_a_printed_pin_recharges_a_line(
    factory: sessionmaker[Session], admin: TestClient
) -> None:
    requested = _request(admin)
    assert requested.status_code == 201, requested.text
    batch = requested.json()["batch"]
    assert (batch["name"], batch["state"], batch["card_count"]) == ("V-00001", "requested", 3)
    with factory() as s:
        assert s.scalars(select(Voucher)).all() == []  # no card, no PIN, before printing

    assert _advance(admin, batch["batch_id"], "approved").json()["approved_by"] == (
        "admin@example.test"
    )
    printed = admin.post(f"/v1/voucher-batches/{batch['batch_id']}/print")
    assert printed.status_code == 200
    assert printed.headers["content-type"] == "application/pdf"
    assert printed.headers["cache-control"] == "no-store"
    assert printed.content.startswith(b"%PDF-1.4") and printed.content.rstrip().endswith(b"%%EOF")
    cards = sheet_cards(printed.content)
    assert len(cards) == 3
    assert "V-00001" in sheet_text(printed.content)
    with factory() as s:
        stored = s.scalars(select(Voucher).order_by(Voucher.voucher_id)).all()
        assert [v.card_number for v in stored] == [n for n, _ in cards]
        assert {v.state for v in stored} == {"sent_to_printer"}
        for v, (_, pin) in zip(stored, cards, strict=True):
            assert pin not in v.pin_hash  # stored hashed only

    assert _advance(admin, batch["batch_id"], "in_stock").status_code == 200
    on_sale = _advance(admin, batch["batch_id"], "on_sale")
    assert on_sale.json()["state"] == "on_sale"

    with factory() as s, s.begin():
        seed_line(s, 1)

    @contextmanager
    def scope() -> Iterator[RedemptionRepositories]:
        with factory() as session, session.begin():
            yield RedemptionRepositories(
                vouchers=SqlVoucherRepository(session),
                ledger=SqlLedgerRepository(session),
                lines=SqlLineLookup(session),
            )

    number, pin = cards[0]
    result = redeem_for_number(scope, msisdn="2348000000001", card_number=number, pin=pin, now=NOW)
    assert (result.status, result.amount_kobo) == (RedeemStatus.REDEEMED, 50_000)


def test_the_sheet_is_made_once_only(admin: TestClient, factory: sessionmaker[Session]) -> None:
    batch_id, _ = _printed_batch(admin)
    again = admin.post(f"/v1/voucher-batches/{batch_id}/print")
    assert again.status_code == 409
    assert "printed already" in again.json()["error"]["message"]
    with factory() as s:
        assert len(s.scalars(select(Voucher)).all()) == 3


def test_a_batch_cannot_be_printed_before_it_is_approved(admin: TestClient) -> None:
    batch_id = _request(admin).json()["batch"]["batch_id"]
    assert admin.post(f"/v1/voucher-batches/{batch_id}/print").status_code == 409


def test_steps_go_in_order_and_a_repeat_changes_nothing(admin: TestClient) -> None:
    batch_id = _request(admin).json()["batch"]["batch_id"]
    assert _advance(admin, batch_id, "on_sale").status_code == 409  # not before printing
    assert _advance(admin, batch_id, "approved").status_code == 200
    assert _advance(admin, batch_id, "approved").status_code == 200  # a double click
    assert _advance(admin, batch_id, "in_stock").status_code == 409  # printing comes first


def test_a_request_with_the_same_key_is_the_same_batch(admin: TestClient) -> None:
    first, again = _request(admin, "same"), _request(admin, "same")
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["replayed"] is True
    assert again.json()["batch"]["batch_id"] == first.json()["batch"]["batch_id"]
    assert len(admin.get("/v1/voucher-batches").json()["items"]) == 1


def test_only_the_catalogue_s_face_values_and_at_most_240_cards(admin: TestClient) -> None:
    listing = admin.get("/v1/voucher-batches").json()
    assert listing["voucher_values_kobo"] == [10_000, 20_000, 50_000, 100_000, 200_000]
    assert listing["max_cards"] == 240
    assert _request(admin, "a", value=30_000).status_code == 422
    assert _request(admin, "b", count=241).status_code == 422
    assert _request(admin, "c", count=0).status_code == 422


def test_locking_a_batch_locks_its_unused_cards(
    admin: TestClient, factory: sessionmaker[Session]
) -> None:
    batch_id, _ = _printed_batch(admin)
    locked = admin.post(f"/v1/voucher-batches/{batch_id}/lock", json={"reason": "sheet lost"})
    assert locked.json()["state"] == "locked"
    with factory() as s:
        assert {v.state for v in s.scalars(select(Voucher))} == {"locked"}
    assert _advance(admin, batch_id, "in_stock").status_code == 409


def test_a_card_is_looked_up_without_its_pin_and_can_be_locked(
    admin: TestClient, agent: TestClient
) -> None:
    _, pdf = _printed_batch(admin)
    number, pin = sheet_cards(pdf)[1]
    found = agent.post("/v1/vouchers/lookup", json={"card_number": number})
    assert found.status_code == 200, found.text
    card = found.json()
    assert card["card_number_last4"] == number[-4:]
    assert card["state"] == "sent_to_printer"
    assert (card["failed_attempts"], card["max_attempts"]) == (0, 5)
    assert number not in found.text and pin not in found.text
    missing = agent.post("/v1/vouchers/lookup", json={"card_number": "0" * 20})
    assert missing.status_code == 404
    locked = admin.post(f"/v1/vouchers/{card['voucher_id']}/lock", json={"reason": "stolen"})
    assert locked.json()["state"] == "locked"
    again = admin.post(f"/v1/vouchers/{card['voucher_id']}/lock", json={"reason": "stolen"})
    assert again.status_code == 409


def test_staff_who_are_not_admins_see_batches_but_change_nothing(
    admin: TestClient, agent: TestClient
) -> None:
    batch_id = _request(admin).json()["batch"]["batch_id"]
    assert agent.get("/v1/voucher-batches").status_code == 200
    assert _request(agent, "agent").status_code == 403
    assert _advance(agent, batch_id, "approved").status_code == 403
    assert agent.post(f"/v1/voucher-batches/{batch_id}/print").status_code == 403
    assert (
        agent.post(f"/v1/voucher-batches/{batch_id}/lock", json={"reason": "x" * 5}).status_code
        == 403
    )


def test_every_step_is_recorded_with_who_and_why_and_never_a_pin(
    admin: TestClient, factory: sessionmaker[Session]
) -> None:
    batch_id, pdf = _printed_batch(admin)
    admin.post(f"/v1/voucher-batches/{batch_id}/lock", json={"reason": "sheet lost"})
    with factory() as s:
        events = s.scalars(select(VoucherEvent).order_by(VoucherEvent.event_id)).all()
        row = s.scalars(select(VoucherBatch)).one()
    assert [(e.action, e.actor) for e in events] == [
        ("request", "admin@example.test"),
        ("approved", "admin@example.test"),
        ("print", "admin@example.test"),
        ("lock_batch", "admin@example.test"),
    ]
    assert (row.printed_by, row.printed_at is not None) == ("admin@example.test", True)
    recorded = " ".join(f"{e.reason} {e.detail}" for e in events)
    for number, pin in sheet_cards(pdf):
        assert pin not in recorded and number not in recorded


def test_voucher_values_are_kept_in_the_catalogue_settings(admin: TestClient) -> None:
    settings = admin.get("/v1/catalogue").json()["settings"]
    assert settings["voucher_values_kobo"] == [10_000, 20_000, 50_000, 100_000, 200_000]
    saved = admin.put(
        "/v1/catalogue/settings",
        json={**settings, "voucher_values_kobo": [50_000, 100_000], "reason": "demo values"},
    )
    assert saved.status_code == 200, saved.text
    assert admin.get("/v1/voucher-batches").json()["voucher_values_kobo"] == [50_000, 100_000]
    bad = admin.put(
        "/v1/catalogue/settings",
        json={**settings, "voucher_values_kobo": [100_000, 50_000], "reason": "unsorted"},
    )
    assert bad.status_code == 422
