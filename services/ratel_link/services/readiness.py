"""Can RatelLink actually work right now? Answers with component names only, never with detail.

`/healthz` says the process is up. This says it can do its job: the store answers and the
encryption key is loaded. The result is used by an unauthenticated route, so it carries nothing
that describes the host, the database or the key.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from common.logging import log_event
from ratel_link.repositories.ports import StoreHealth
from ratel_link.security.key_provider import KeyProvider, KeyUnavailableError

log = logging.getLogger("ratel.link.readiness")


@dataclass(frozen=True)
class Readiness:
    ready: bool
    # Which parts failed, by fixed name ("store", "key"). For the log, not for the caller.
    failed: tuple[str, ...]


class ReadinessService:
    def __init__(self, store: StoreHealth | None, keys: KeyProvider) -> None:
        # No store probe means nothing proves the database works, so that counts as not ready.
        self._store = store
        self._keys = keys

    def check(self) -> Readiness:
        failed: list[str] = []
        if not self._store_ok():
            failed.append("store")
        if not self._key_ok():
            failed.append("key")
        return Readiness(ready=not failed, failed=tuple(failed))

    def _store_ok(self) -> bool:
        if self._store is None:
            log_event(log, logging.WARNING, "readiness.failed", component="store", exc_type="none")
            return False
        try:
            self._store.check()
        except Exception as exc:
            # Type only: a driver message can carry a host name or a user name.
            log_event(
                log,
                logging.WARNING,
                "readiness.failed",
                component="store",
                exc_type=type(exc).__name__,
            )
            return False
        return True

    def _key_ok(self) -> bool:
        try:
            self._keys.get_key(self._keys.current_key_id())
        except KeyUnavailableError:
            log_event(
                log,
                logging.WARNING,
                "readiness.failed",
                component="key",
                exc_type="KeyUnavailableError",
            )
            return False
        return True
