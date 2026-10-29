"""Whether the app can do its job: `/readyz`.

`/healthz` says the process is up. This says what a deployment needs before it takes traffic: the
database answers, its schema is at the code's migration head, Redis answers (it holds the
Idempotency-Keys, and without it every state-changing route fails), and the key for RatelLink is
set. A missing migration or a missing Redis would otherwise show up as errors on the first sale.

`/readyz` answers 200 or 503 and never says why, because a monitor has no key and a body could
help a stranger. The reason goes to the log as component names only, never a driver message.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import Settings
from common.logging import log_event

log = logging.getLogger("ratel.app.readiness")

ALEMBIC_INI = Path(__file__).resolve().parent / "alembic.ini"


@dataclass(frozen=True)
class Readiness:
    failed: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.failed


def migrations_current(engine: Engine) -> bool:
    """True if the database is at exactly the migration head(s) this code ships."""
    heads = set(ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads())
    with engine.connect() as connection:
        current = set(MigrationContext.configure(connection).get_current_heads())
    return current == heads


def _database(engine: Engine) -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def check(settings: Settings, engine: Engine, redis_client: Any | None) -> Readiness:
    """Run every check; none stops the others. `redis_client` is None where Redis is not used."""
    checks: dict[str, Any] = {"database": lambda: _database(engine)}
    checks["migrations"] = lambda: migrations_current(engine)
    if redis_client is not None:
        checks["redis"] = lambda: bool(redis_client.ping())
    if settings.ratel_env not in ("local", "test"):
        checks["ratel_link_key"] = lambda: (
            settings.ratel_link_api_key is not None
            and bool(settings.ratel_link_api_key.get_secret_value().strip())
        )
    failed = []
    for component, run in checks.items():
        try:
            ok = run()
        except Exception as exc:
            ok = False
            log_event(
                log,
                logging.ERROR,
                "readiness.error",
                component=component,
                exc_type=type(exc).__name__,
            )
        if not ok:
            failed.append(component)
    if failed:
        log_event(log, logging.ERROR, "readiness.failed", components=",".join(failed))
    return Readiness(tuple(failed))
