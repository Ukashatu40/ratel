from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.database import Database
from starlette.concurrency import run_in_threadpool

from common.errors import error_body, install_error_handlers
from common.http import install_request_context
from common.logging import configure_logging, log_event
from common.timeutil import utc_now
from ratel_link.api.router import build_v1_router
from ratel_link.config import Settings
from ratel_link.repositories.mongo import (
    MongoApiKeyRepository,
    MongoAuditLogRepository,
    MongoSimKeyRepository,
    missing_indexes,
    open_database,
)
from ratel_link.repositories.ports import (
    ApiKeyRepository,
    AuditLogRepository,
    SimKeyRepository,
)
from ratel_link.security.key_provider import KeyProvider, KeyUnavailableError, build_key_provider
from ratel_link.services.api_key_admin import KeyPolicy, log_expiring
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.sim_import import SimImportService
from ratel_link.services.sim_keys import SimKeyStore

log = logging.getLogger("ratel.link.startup")


def _startup_checks(
    database: Database[Any] | None,
    api_keys: ApiKeyRepository,
    clock: Callable[[], datetime],
    policy: KeyPolicy,
) -> None:
    """Verify and report. Never changes anything and never stops the service."""
    try:
        if database is not None:
            missing = missing_indexes(database)
            if missing:
                # Creating them is a deliberate step: `python -m ratel_link.admin_cli init-db`.
                log_event(log, logging.ERROR, "startup.indexes.missing", indexes=missing)
        log_expiring(api_keys, clock(), policy)
    except Exception as exc:
        # MongoDB may not be up yet. The service still starts. Type only: messages can carry hosts.
        log_event(log, logging.ERROR, "startup.checks.failed", exc_type=type(exc).__name__)


def create_app(
    settings: Settings | None = None,
    *,
    api_keys: ApiKeyRepository | None = None,
    sim_keys: SimKeyRepository | None = None,
    audit: AuditLogRepository | None = None,
    key_provider: KeyProvider | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    """Build the service. The repositories, key provider and clock exist so tests can supply
    in-memory fakes and a fixed clock. In production they are left out and MongoDB is used."""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    # Fail closed: outside local/test, no usable key file means the service does not start.
    key_provider = key_provider or build_key_provider(settings)
    # The MongoDB client connects lazily, so building the app does not need a database.
    database: Database[Any] | None = None
    if api_keys is None or sim_keys is None or audit is None:
        database = open_database(settings)
        api_keys = api_keys or MongoApiKeyRepository(database)
        sim_keys = sim_keys or MongoSimKeyRepository(database)
        audit = audit or MongoAuditLogRepository(database)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        policy = KeyPolicy.from_settings(settings)
        await run_in_threadpool(_startup_checks, database, api_keys, clock, policy)
        yield
        if database is not None:
            database.client.close()

    app = FastAPI(
        title="RatelLink",
        version="0.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.key_provider = key_provider
    app.state.api_keys = api_keys
    app.state.clock = clock
    app.state.sim_import = SimImportService(
        SimKeyStore(sim_keys, key_provider, clock), AuditLog(audit, clock)
    )
    install_error_handlers(app)
    install_request_context(app)

    @app.exception_handler(KeyUnavailableError)
    async def _key_unavailable(_: Request, exc: KeyUnavailableError) -> JSONResponse:
        # No usable encryption key: refuse rather than store anything unencrypted. Type only.
        log_event(log, logging.ERROR, "key.unavailable")
        return JSONResponse(
            status_code=503,
            content=error_body("unavailable", "The service cannot handle SIM keys right now."),
        )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        # Liveness only, and the only route without an API key. It exposes nothing.
        # TODO: readiness check (MongoDB ping) once RatelLink has a store.
        return {"status": "ok"}

    app.include_router(build_v1_router())
    return app
