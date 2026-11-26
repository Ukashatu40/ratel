"""The catalogue an admin keeps in RatelDesk, over HTTP on SQLite (docs/catalogue.md)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from tests.app.bss_lines.desk_helpers import add_staff, make_app, signed_in
from tests.app.bss_money.sqlite_database import sqlite_engine

GB = 1_000_000_000

WEEKLY = {
    "kind": "bundle",
    "name": "Weekly 3GB",
    "price_kobo": 60_000,
    "data_bytes": 3 * GB,
    "validity_days": 7,
    "channels": ["desk", "sms", "ussd"],
    "reason": "launch price list",
}
HOME = {
    "kind": "plan",
    "name": "Home 10 Mbps",
    "price_kobo": 1_500_000,
    "data_bytes": 150 * GB,
    "validity_days": 30,
    "channels": ["desk"],
    "speed_dl_mbps": 10,
    "speed_ul_mbps": 5,
    "on_exhaustion": "slow",
    "slow_dl_mbps": 2,
    "slow_ul_mbps": 1,
    "reason": "launch price list",
}


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.passwords._N", 2**10)


@pytest.fixture
def factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = sqlite_engine(str(tmp_path / "catalogue.db"))
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def admin(factory: sessionmaker[Session]) -> TestClient:
    return signed_in(make_app(factory), add_staff(factory, "admin"))


@pytest.fixture
def agent(factory: sessionmaker[Session]) -> TestClient:
    return signed_in(make_app(factory), add_staff(factory, "agent"))


def _create(client: TestClient, body: dict[str, object], key: str) -> object:
    return client.post("/v1/catalogue/offers", json=body, headers={"Idempotency-Key": key})


def test_an_admin_publishes_a_bundle_and_a_plan_and_everyone_can_read_them(
    admin: TestClient, agent: TestClient
) -> None:
    bundle = _create(admin, WEEKLY, "k1")
    plan = _create(admin, HOME, "k2")
    assert bundle.status_code == 201, bundle.text  # type: ignore[attr-defined]
    assert plan.status_code == 201, plan.text  # type: ignore[attr-defined]

    body = agent.get("/v1/catalogue").json()
    offers = {(o["kind"], o["name"]): o for o in body["offers"]}
    weekly = offers[("bundle", "Weekly 3GB")]
    assert weekly["channels"] == ["desk", "sms", "ussd"]
    assert weekly["state"] == "on_sale"
    assert weekly["speed_dl_mbps"] is None
    home = offers[("plan", "Home 10 Mbps")]
    assert (home["on_exhaustion"], home["slow_dl_mbps"]) == ("slow", 2)
    assert body["settings"]["airtime_min_kobo"] == 2_000
    assert body["gateway"] == {"min_kobo": 10_000, "max_kobo": 100_000_000}


def test_an_agent_may_not_change_the_catalogue(agent: TestClient) -> None:
    response = _create(agent, WEEKLY, "k1")
    assert response.status_code == 403  # type: ignore[attr-defined]
    retire = agent.post("/v1/catalogue/offers/bundle/1/retire", json={"reason": "x"})
    assert retire.status_code == 403
    settings = agent.put("/v1/catalogue/settings", json={})
    assert settings.status_code in (403, 422)


def test_a_repeated_create_returns_the_first_offer_and_a_reused_key_is_refused(
    admin: TestClient,
) -> None:
    first = _create(admin, WEEKLY, "same").json()  # type: ignore[attr-defined]
    again = _create(admin, WEEKLY, "same")
    assert again.status_code == 200  # type: ignore[attr-defined]
    assert again.json() == {"offer_id": first["offer_id"], "replayed": True}  # type: ignore[attr-defined]
    reused = _create(admin, HOME, "same")
    assert reused.status_code == 409  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ({"on_exhaustion": "slow", "slow_dl_mbps": None}, "slow"),
        ({"speed_dl_mbps": None}, "speeds"),
        ({"name": "   "}, "name"),
    ],
)
def test_an_offer_that_breaks_a_rule_is_refused_in_words(
    admin: TestClient, change: dict[str, object], words: str
) -> None:
    response = _create(admin, {**HOME, **change}, "bad")
    assert response.status_code == 422  # type: ignore[attr-defined]
    assert words in response.text  # type: ignore[attr-defined]


def test_retiring_takes_an_offer_off_sale_once(admin: TestClient) -> None:
    offer_id = _create(admin, WEEKLY, "k1").json()["offer_id"]  # type: ignore[attr-defined]
    url = f"/v1/catalogue/offers/bundle/{offer_id}/retire"
    assert admin.post(url, json={"reason": "new prices"}).json() == {"retired": True}
    assert admin.post(url, json={"reason": "new prices"}).json() == {"retired": False}
    assert (
        admin.post("/v1/catalogue/offers/bundle/999/retire", json={"reason": "x"}).status_code
        == 404
    )
    states = {o["offer_id"]: o["state"] for o in admin.get("/v1/catalogue").json()["offers"]}
    assert states[offer_id] == "retired"


def test_settings_stay_inside_the_gateway_and_every_change_is_audited(admin: TestClient) -> None:
    good = {
        "airtime_min_kobo": 2_000,
        "card_min_kobo": 10_000,
        "card_max_kobo": 5_000_000,
        "airtime_presets_kobo": [10_000, 50_000],
        "voice_onnet_kobo_per_min": 800,
        "voice_offnet_kobo_per_min": 1_500,
        "sms_onnet_kobo": 250,
        "reason": "launch rates",
    }
    below = admin.put("/v1/catalogue/settings", json={**good, "card_min_kobo": 5_000})
    assert below.status_code == 422
    assert "gateway" in below.text
    saved = admin.put("/v1/catalogue/settings", json=good)
    assert saved.status_code == 200, saved.text
    assert saved.json()["voice_onnet_kobo_per_min"] == 800
    assert admin.get("/v1/catalogue").json()["settings"]["airtime_presets_kobo"] == [10_000, 50_000]

    _create(admin, WEEKLY, "k1")
    items = admin.get("/v1/catalogue/audit").json()["items"]
    assert [i["action"] for i in items] == ["create_bundle", "update_settings"]
    assert items[0]["actor"] == "admin@example.test"
    assert items[0]["reason"] == "launch price list"
    assert "600.00 naira" in items[0]["detail"]
    assert "voice_onnet_kobo_per_min 1000 -> 800" in items[1]["detail"]
    assert "sms_onnet_kobo 200 -> 250" in items[1]["detail"]
    negative = admin.put("/v1/catalogue/settings", json={**good, "sms_onnet_kobo": -1})
    assert negative.status_code == 422
