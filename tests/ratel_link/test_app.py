import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from ratel_link.config import Settings
from ratel_link.main import create_app
from ratel_link.security.key_provider import KeyProvider, NoKeyProvider
from tests.ratel_link.fakes import FakeStoreHealth, StaticKeyProvider
from tests.ratel_link.helpers import all_fakes


def test_healthz() -> None:
    r = TestClient(create_app(Settings())).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["x-request-id"]


def _ready_client(
    *, store: FakeStoreHealth | None = None, keys: KeyProvider | None = None
) -> TestClient:
    fakes = all_fakes()
    if store is not None:
        fakes["store_health"] = store
    return TestClient(
        create_app(Settings(), **fakes, key_provider=keys or StaticKeyProvider()),
        raise_server_exceptions=False,
    )


def test_readyz_is_ok_with_a_healthy_store_and_a_key() -> None:
    r = _ready_client().get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}
    assert r.headers["cache-control"] == "no-store"


def test_readyz_needs_no_api_key() -> None:
    # A monitor has no key. The route is public on purpose and tells nothing.
    assert (
        _ready_client().get("/readyz", headers={"Authorization": "Bearer nope"}).status_code == 200
    )


def test_readyz_is_503_when_mongodb_is_down() -> None:
    store = FakeStoreHealth(ConnectionError("mongodb://u:pw@db-host:27017 timed out"))
    r = _ready_client(store=store).get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable"}


def test_readyz_is_503_when_there_is_no_key() -> None:
    r = _ready_client(keys=NoKeyProvider()).get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable"}


def test_readyz_never_says_why() -> None:
    store = FakeStoreHealth(
        PermissionError("/etc/ratel-link/ratel_link.key at db-host:27017 as user ratel_link")
    )
    r = _ready_client(store=store, keys=NoKeyProvider()).get("/readyz")
    assert r.status_code == 503
    body = r.text.lower()
    for fragment in (
        "/etc",
        "ratel_link.key",
        "db-host",
        "27017",
        "ratel_link",
        "permission",
        "key id",
    ):
        assert fragment not in body
    assert set(r.json()) == {"status"}


def test_readyz_checks_the_store_once_per_call() -> None:
    store = FakeStoreHealth()
    _ready_client(store=store).get("/readyz")
    assert store.checks == 1


def test_request_id_is_echoed() -> None:
    r = TestClient(create_app(Settings())).get("/healthz", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


def test_unknown_route_uses_error_shape() -> None:
    r = TestClient(create_app(Settings())).get("/v1/nothing")
    assert r.status_code == 404
    assert set(r.json()) == {"error"}


@pytest.mark.parametrize(
    "uri",
    [
        "mongodb://127.0.0.1:27017",
        "mongodb://localhost:27017/?authSource=admin",
        "mongodb://user:pw@127.0.0.1:27017/?authSource=admin",
    ],
)
def test_localhost_mongo_accepted(uri: str) -> None:
    assert Settings(mongo_uri=SecretStr(uri)).mongo_uri.get_secret_value() == uri


@pytest.mark.parametrize(
    "uri",
    ["mongodb://192.168.1.50:27017", "mongodb://db.example.com", "mongodb://127.0.0.1,10.0.0.9"],
)
def test_remote_mongo_rejected_without_leaking_uri(uri: str) -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(mongo_uri=SecretStr(uri))
    assert uri not in str(exc.value)


def test_mongo_uri_from_environment_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://10.0.0.5:27017")
    with pytest.raises(ValidationError):
        Settings()
