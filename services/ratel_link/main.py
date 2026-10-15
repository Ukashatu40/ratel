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
from ratel_link.domain.ip_pool import IpPool
from ratel_link.domain.subscriber import VoiceTemplateError
from ratel_link.repositories.mongo import (
    MongoApiKeyRepository,
    MongoAuditLogRepository,
    MongoIpAllocationRepository,
    MongoLineStateRepository,
    MongoSimKeyRepository,
    MongoSubscriberRepository,
    missing_indexes,
    open_database,
    subscriber_index_missing,
)
from ratel_link.repositories.ports import (
    ApiKeyRepository,
    AuditLogRepository,
    IpAllocationRepository,
    LineStateRepository,
    SimKeyRepository,
    SubscriberRepository,
    VoiceTemplateSource,
)
from ratel_link.repositories.voice_template import FileVoiceTemplate
from ratel_link.security.key_provider import KeyProvider, KeyUnavailableError, build_key_provider
from ratel_link.services.api_key_admin import KeyPolicy, log_expiring
from ratel_link.services.assignments import AssignmentService
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.data_mode import DataModeService
from ratel_link.services.ip_allocation import IpAllocator
from ratel_link.services.line_activation import LineActivationService
from ratel_link.services.line_deactivation import LineDeactivationService
from ratel_link.services.line_status import LineStatusService
from ratel_link.services.sim_import import SimImportService
from ratel_link.services.sim_keys import SimKeyStore

log = logging.getLogger("ratel.link.startup")


def _startup_checks(
    database: Database[Any] | None,
    api_keys: ApiKeyRepository,
    clock: Callable[[], datetime],
    policy: KeyPolicy,
    settings: Settings,
    voice_template: VoiceTemplateSource,
) -> None:
    """Verify and report. Never changes anything and never stops the service."""
    try:
        if database is not None:
            missing = missing_indexes(database)
            if missing:
                # Creating them is a deliberate step: `python -m ratel_link.admin_cli init-db`.
                log_event(log, logging.ERROR, "startup.indexes.missing", indexes=missing)
            if subscriber_index_missing(database.client[settings.open5gs_db_name]):
                # RatelLink never creates indexes in the core's database. Ask the network team.
                log_event(log, logging.ERROR, "startup.subscribers.index.missing")
        try:
            if voice_template.ims_session() is None:
                log_event(log, logging.WARNING, "startup.voice.template.not_configured")
        except VoiceTemplateError:
            log_event(log, logging.ERROR, "startup.voice.template.invalid")
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
    line_states: LineStateRepository | None = None,
    ip_allocations: IpAllocationRepository | None = None,
    subscribers: SubscriberRepository | None = None,
    voice_template: VoiceTemplateSource | None = None,
    key_provider: KeyProvider | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    """Build the service. The repositories, key provider and clock exist so tests can supply
    in-memory fakes and a fixed clock. In production they are left out and MongoDB is used."""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    # Fail closed: outside local/test, no usable key file means the service does not start.
    key_provider = key_provider or build_key_provider(settings)

    # The MongoDB client connects lazily, so building the app does not need a database. It is
    # opened only if at least one repository was not supplied.
    opened: list[Database[Any]] = []

    def mongo() -> Database[Any]:
        if not opened:
            opened.append(open_database(settings))
        return opened[0]

    api_keys = api_keys if api_keys is not None else MongoApiKeyRepository(mongo())
    sim_keys = sim_keys if sim_keys is not None else MongoSimKeyRepository(mongo())
    audit = audit if audit is not None else MongoAuditLogRepository(mongo())
    line_states = line_states if line_states is not None else MongoLineStateRepository(mongo())
    ip_allocations = (
        ip_allocations if ip_allocations is not None else MongoIpAllocationRepository(mongo())
    )
    subscribers = (
        subscribers
        if subscribers is not None
        else MongoSubscriberRepository(mongo().client[settings.open5gs_db_name])
    )
    voice_template = voice_template or FileVoiceTemplate(settings.ratel_link_voice_template_file)
    database = opened[0] if opened else None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        policy = KeyPolicy.from_settings(settings)
        await run_in_threadpool(
            _startup_checks, database, api_keys, clock, policy, settings, voice_template
        )
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
    app.state.line_status = LineStatusService(line_states, sim_keys)
    app.state.assignments = AssignmentService(ip_allocations, clock)
    audit_log = AuditLog(audit, clock)
    allocator = IpAllocator(ip_allocations, IpPool.from_cidr(settings.ratel_link_ue_pool), clock)
    app.state.line_activation = LineActivationService(
        SimKeyStore(sim_keys, key_provider, clock),
        subscribers,
        line_states,
        allocator,
        voice_template,
        audit_log,
        clock,
    )
    app.state.line_deactivation = LineDeactivationService(
        sim_keys, subscribers, line_states, allocator, audit_log, clock
    )
    app.state.data_mode = DataModeService(subscribers, line_states, audit_log, clock)
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
