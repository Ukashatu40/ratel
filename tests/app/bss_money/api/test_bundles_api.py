"""`GET /v1/pay/bundles` on SQLite: what RatelPay shows, and who may ask."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bss_lines.models.lines import Bundle
from app.config import Settings
from app.db import Base
from app.main import create_app

PAY_KEY = "test-pay-key-not-a-real-key"
AUTH = {"Authorization": f"Bearer {PAY_KEY}"}
URL = "/v1/pay/bundles"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'bss.db'}",  # type: ignore[arg-type]
            pay_api_key=PAY_KEY,  # type: ignore[arg-type]
        )
    )
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as c:
        yield c


def _add(client: TestClient, *bundles: Bundle) -> None:
    with client.app.state.session_factory() as session, session.begin():  # type: ignore[attr-defined]
        session.add_all(bundles)


def _bundle(name: str, price: int, data: int, days: int) -> Bundle:
    return Bundle(name=name, price_kobo=price, data_bytes=data, validity_days=days, channels="data")


def test_no_bundles_is_an_empty_list(client: TestClient) -> None:
    response = client.get(URL, headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"bundles": []}


def test_bundles_come_back_in_id_order_with_the_five_contract_fields_only(
    client: TestClient,
) -> None:
    _add(
        client,
        _bundle("Daily 500MB", 20_000, 524_288_000, 1),
        _bundle("Weekly 2GB", 100_000, 2_147_483_648, 7),
    )
    response = client.get(URL, headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {
        "bundles": [
            {
                "bundle_id": 1,
                "name": "Daily 500MB",
                "price_kobo": 20_000,
                "data_bytes": 524_288_000,
                "validity_days": 1,
            },
            {
                "bundle_id": 2,
                "name": "Weekly 2GB",
                "price_kobo": 100_000,
                "data_bytes": 2_147_483_648,
                "validity_days": 7,
            },
        ]
    }


def test_the_answer_is_not_kept_by_a_cache(client: TestClient) -> None:
    assert client.get(URL, headers=AUTH).headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic abc"}],
    ids=["no-key", "wrong-key", "wrong-scheme"],
)
def test_without_the_proxys_key_the_list_is_401(
    client: TestClient, headers: dict[str, str]
) -> None:
    _add(client, _bundle("Weekly 2GB", 100_000, 2_147_483_648, 7))
    response = client.get(URL, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert "Weekly" not in response.text
