"""The Idempotency-Key stores. The Redis store is what runs everywhere except local and test."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import SecretStr

from app.bss_lines.repositories.idempotency import (
    IdempotencyStore,
    InMemoryIdempotencyStore,
    RedisIdempotencyStore,
    StoredResult,
)
from app.config import Settings
from app.main import create_app

FIRST = StoredResult(line_id=7, from_state="active", to_state="suspended")


class FakeRedis:
    """The two calls the store makes, with Redis's habit of returning bytes."""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.expiry: dict[str, int] = {}

    def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value.encode()
        if ex is not None:
            self.expiry[key] = ex


@pytest.fixture(params=["memory", "redis"])
def store(request: pytest.FixtureRequest) -> IdempotencyStore:
    if request.param == "memory":
        return InMemoryIdempotencyStore()
    return RedisIdempotencyStore(FakeRedis())


def test_a_key_that_was_never_used_is_not_found(store: IdempotencyStore) -> None:
    assert store.get("/suspend", "k-1") is None


def test_a_saved_result_comes_back_whole(store: IdempotencyStore) -> None:
    store.put("/suspend", "k-1", FIRST)
    assert store.get("/suspend", "k-1") == FIRST


def test_the_same_key_on_another_endpoint_is_another_operation(store: IdempotencyStore) -> None:
    store.put("/suspend", "k-1", FIRST)
    assert store.get("/terminate", "k-1") is None


def test_another_key_is_another_operation(store: IdempotencyStore) -> None:
    store.put("/suspend", "k-1", FIRST)
    assert store.get("/suspend", "k-2") is None


def test_redis_keeps_a_result_for_24_hours_under_a_namespaced_key() -> None:
    redis = FakeRedis()
    RedisIdempotencyStore(redis).put("/suspend", "k-1", FIRST)
    (key,) = redis.values
    assert key == "bss_lines:idempotency:/suspend:k-1"
    assert redis.expiry[key] == 24 * 60 * 60


def test_redis_keeps_a_chosen_lifetime() -> None:
    redis = FakeRedis()
    RedisIdempotencyStore(redis, ttl_seconds=60).put("/suspend", "k-1", FIRST)
    assert list(redis.expiry.values()) == [60]


def test_redis_stores_the_line_and_the_two_states_and_nothing_else() -> None:
    redis = FakeRedis()
    RedisIdempotencyStore(redis).put("/suspend", "k-1", FIRST)
    (raw,) = redis.values.values()
    assert json.loads(raw) == {"line_id": 7, "from_state": "active", "to_state": "suspended"}


def test_a_result_saved_by_one_store_object_is_found_by_a_new_one() -> None:
    # A restart makes a new store object over the same Redis: a repeat must still be a repeat.
    redis = FakeRedis()
    RedisIdempotencyStore(redis).put("/suspend", "k-1", FIRST)
    assert RedisIdempotencyStore(redis).get("/suspend", "k-1") == FIRST


def _settings(env: str, **extra: Any) -> Settings:
    return Settings(
        ratel_env=env,  # type: ignore[arg-type]
        database_url=SecretStr("sqlite:///:memory:"),
        meter_api_key=SecretStr("k" * 32),
        pay_api_key=SecretStr("k" * 32),
        **extra,
    )


@pytest.mark.parametrize("env", ["local", "test"])
def test_local_and_test_use_the_in_memory_store(env: str) -> None:
    app = create_app(_settings(env))
    assert isinstance(app.state.idempotency_store, InMemoryIdempotencyStore)


@pytest.mark.parametrize("env", ["lab", "staging", "production"])
def test_a_deployed_app_uses_the_redis_store(env: str) -> None:
    # Redis is not contacted when the app is built, only when a route first asks for a key.
    app = create_app(_settings(env))
    assert isinstance(app.state.idempotency_store, RedisIdempotencyStore)
