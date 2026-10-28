"""The Idempotency-Key store (M-26).

A repeat of a state-changing call with the same key and the same line returns
the first result and changes nothing. A repeat with the same key for a
*different* line is refused (`IdempotencyConflictError`): a key names one
operation, not a template.

Concurrency: `get` and `put` are separate calls, so two simultaneous requests
with the same key can both miss `get`, both run, and the second then fails at
the state machine (active -> active is refused). SET ... NX would reserve the
key first; until then, the state machine is what stops the double effect.

In local and test the app uses InMemoryIdempotencyStore (single process, lost
on restart). Everywhere else create_app uses RedisIdempotencyStore, so a
restart does not turn a repeat into a new operation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol


class IdempotencyConflictError(Exception):
    """This Idempotency-Key was already used for a different line."""


@dataclass(frozen=True)
class StoredResult:
    """The first result of a state-changing call, saved for replay."""

    line_id: int
    from_state: str
    to_state: str


class IdempotencyStore(Protocol):
    """Storage for the first result of a state-changing call.

    Two simultaneous requests with the same key can both run; the second fails
    at the state machine (SET ... NX would reserve the key first, planned).
    """

    def get(self, endpoint: str, idempotency_key: str) -> StoredResult | None:
        """The saved result, or None if this key has not been used before."""
        ...

    def put(self, endpoint: str, idempotency_key: str, result: StoredResult) -> None:
        """Save the result of a call. Called once per key."""
        ...


class InMemoryIdempotencyStore:
    """A store that holds results for the process's lifetime. local and test."""

    def __init__(self) -> None:
        self._results: dict[tuple[str, str], StoredResult] = {}

    def get(self, endpoint: str, idempotency_key: str) -> StoredResult | None:
        return self._results.get((endpoint, idempotency_key))

    def put(self, endpoint: str, idempotency_key: str, result: StoredResult) -> None:
        self._results[(endpoint, idempotency_key)] = result


class RedisIdempotencyStore:
    """A Redis-backed store, kept for 24 hours per key. lab, staging, production."""

    def __init__(self, redis_client: object, ttl_seconds: int = 24 * 60 * 60) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, endpoint: str, idempotency_key: str) -> str:
        return f"bss_lines:idempotency:{endpoint}:{idempotency_key}"

    def get(self, endpoint: str, idempotency_key: str) -> StoredResult | None:
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
