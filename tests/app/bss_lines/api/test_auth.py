"""Auth on the BSS write routes (M-26)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.bss_lines.api.lines import get_client
from app.config import Settings
from app.db import Base
from app.main import create_app
from tests.app.bss_lines.fakes import FakeRatelLinkClient

TEST_KEY = "unit-test-bss-key-00000000000"
AUTH = {"Authorization": f"Bearer {TEST_KEY}"}

WRITE_ROUTES = [
    ("/v1/lines/activate", {"line_id": 1, "idempotency_key": "k"}),
    (
        "/v1/lines/suspend",
        {"line_id": 1, "idempotency_key": "k", "reason": "fraud"},
    ),
    (
        "/v1/lines/reinstate",
        {"line_id": 1, "idempotency_key": "k", "reason": "fraud"},
    ),
    (
        "/v1/lines/terminate",
        {"line_id": 1, "idempotency_key": "k", "reason": "fraud"},
    ),
]


@pytest.fixture
def fake_client() -> FakeRatelLinkClient:
    return FakeRatelLinkClient()


@pytest.fixture
def client(tmp_path, fake_client: FakeRatelLinkClient) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    app = create_app(Settings(ratel_env="test", bss_api_key=SecretStr(TEST_KEY)))
    app.state.session_factory = factory
    app.dependency_overrides[get_client] = lambda: fake_client

    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize(("path", "body"), WRITE_ROUTES)
def test_a_write_route_without_a_key_is_401(client: TestClient, path: str, body: dict) -> None:
    assert client.post(path, json=body).status_code == 401


@pytest.mark.parametrize(("path", "body"), WRITE_ROUTES)
def test_a_write_route_with_a_wrong_key_is_401(client: TestClient, path: str, body: dict) -> None:
    response = client.post(path, json=body, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


@pytest.mark.parametrize(("path", "body"), WRITE_ROUTES)
def test_a_write_route_with_a_bad_body_and_no_key_is_401(
    client: TestClient, path: str, body: dict
) -> None:
    """Auth runs before the body is validated: 401, not 422."""
    assert client.post(path, json={"not": "the right shape"}).status_code == 401


@pytest.mark.parametrize(("path", "body"), WRITE_ROUTES)
def test_a_write_route_with_the_right_key_reaches_the_route(
    client: TestClient, path: str, body: dict
) -> None:
    """The request gets past auth; the line doesn't exist, so 400 from the service."""
    response = client.post(path, json=body, headers=AUTH)
    assert response.status_code == 400


def test_no_key_configured_is_503(tmp_path, fake_client: FakeRatelLinkClient) -> None:
    """A local app with no key refuses every write with 503, not 401."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    app = create_app(Settings(ratel_env="test"))
    app.state.session_factory = factory
    app.dependency_overrides[get_client] = lambda: fake_client
    with TestClient(app) as c:
        response = c.post(
            "/v1/lines/activate",
            json={"line_id": 1, "idempotency_key": "k"},
            headers={"Authorization": "Bearer anything"},
        )
    assert response.status_code == 503


def test_lookup_routes_do_not_require_a_key(tmp_path, fake_client: FakeRatelLinkClient) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    app = create_app(Settings(ratel_env="test"))
    app.state.session_factory = factory
    app.dependency_overrides[get_client] = lambda: fake_client
    with TestClient(app) as c:
        assert c.get("/v1/lines/lookup?msisdn=2340000050000").status_code == 404
