"""The Idempotency-Key store (M-26).

A repeat of a state-changing call with the same key returns the first result
and changes nothing. The key is scoped per endpoint, so the same string on
/activate and /data are two different keys — the same discipline the fake
RatelLinkClient uses.

Production uses Redis (keys kept for 24 hours). Tests use the in-memory
implementation. The service never depends on either concretely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredResult:
    """The first result of a state-changing call, saved for replay."""

    line_id: int
    from_state: str
    to_state: str


class IdempotencyStore(Protocol):
    """Storage for the first result of a state-changing call."""

    def get(self, endpoint: str, idempotency_key: str) -> StoredResult | None:
        """The saved result, or None if this key has not been used before."""
        ...

    def put(self, endpoint: str, idempotency_key: str, result: StoredResult) -> None:
        """Save the result of a call. Called once per key."""
        ...


class InMemoryIdempotencyStore:
    """A store that holds results for the process's lifetime. Tests only."""

    def __init__(self) -> None:
        self._results: dict[tuple[str, str], StoredResult] = {}

    def get(self, endpoint: str, idempotency_key: str) -> StoredResult | None:
        return self._results.get((endpoint, idempotency_key))

    def put(self, endpoint: str, idempotency_key: str, result: StoredResult) -> None:
        self._results[(endpoint, idempotency_key)] = result


class RedisIdempotencyStore:
    """A Redis-backed store, kept for 24 hours per key. Production."""

    def __init__(self, redis_client: object, ttl_seconds: int = 24 * 60 * 60) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, endpoint: str, idempotency_key: str) -> str:
        return f"bss_lines:idempotency:{endpoint}:{idempotency_key}"

    def get(self, endpoint: str, idempotency_key: str) -> StoredResult | None:
        import json

        raw = self._redis.get(self._key(endpoint, idempotency_key))  # type: ignore[attr-defined]
        if raw is None:
            return None
        data = json.loads(raw)
        return StoredResult(
            line_id=data["line_id"],
            from_state=data["from_state"],
            to_state=data["to_state"],
        )

    def put(self, endpoint: str, idempotency_key: str, result: StoredResult) -> None:
        import json

        self._redis.set(  # type: ignore[attr-defined]
            self._key(endpoint, idempotency_key),
            json.dumps(
                {
                    "line_id": result.line_id,
                    "from_state": result.from_state,
                    "to_state": result.to_state,
                }
            ),
            ex=self._ttl,
        )
