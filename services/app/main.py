from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from fastapi import FastAPI, Request, Response

from app.bss_lines.api.desk import router as desk_router
from app.bss_lines.api.desk_reads import router as desk_reads_router
from app.bss_lines.api.kyc import router as kyc_router
from app.bss_lines.api.lines import router as bss_lines_router
from app.bss_lines.api.staff import router as staff_router
from app.bss_lines.repositories.desk_sql import SqlDeskReadRepository
from app.bss_money.api.bundles import router as bundles_router
from app.bss_money.api.desk import router as money_desk_router
from app.bss_money.api.payments import router as payments_router
from app.bss_money.api.purchases import router as purchases_router
from app.bss_money.api.vouchers import router as bss_money_router
from app.bss_money.gateways.paystack import PaystackGateway
from app.bss_money.repositories.ports import (
    BundleCatalog,
    DeskReads,
    PaymentRepositories,
    PurchaseRepositories,
    RedemptionRepositories,
)
from app.bss_money.repositories.sql import (
    SqlBundleCatalog,
    SqlLedgerRepository,
    SqlLineLookup,
    SqlMoneyReadRepository,
    SqlPaidPlanCheck,
    SqlPaymentRepository,
    SqlPurchaseRepository,
    SqlVoucherRepository,
)
from app.config import Settings
from app.db import make_engine, session_factory
from app.meter_api.api import router as meter_api_router
from common.errors import install_error_handlers
from common.http import install_request_context
from common.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    if settings.ratel_env not in ("local", "test") and settings.meter_api_key_value is None:
        # Fail closed: a deployed app must not come up with the usage API unprotected or unusable.
        raise RuntimeError("METER_API_KEY is not set: refusing to start outside local and test")
    if settings.ratel_env not in ("local", "test") and settings.pay_api_key_value is None:
        # Fail closed, the same way: no key means the redemption route would answer nobody.
        raise RuntimeError("PAY_API_KEY is not set: refusing to start outside local and test")
    app = FastAPI(
        title="Ratel app", version="0.0.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    install_error_handlers(app)
    install_request_context(app)

    app.state.settings = settings
    db_url = settings.database_url.get_secret_value()
    if db_url.startswith("sqlite"):
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = make_engine(db_url)
    app.state.engine = engine
    app.state.session_factory = session_factory(engine)

    @contextmanager
    def redemption_scope() -> Iterator[RedemptionRepositories]:
        # One transaction per redemption, committed even when the card is refused: the failed
        # attempt must stay on record (services/vouchers.py).
        with app.state.session_factory() as session, session.begin():
            yield RedemptionRepositories(
                vouchers=SqlVoucherRepository(session),
                ledger=SqlLedgerRepository(session),
                lines=SqlLineLookup(session),
            )

    app.state.redemption_scope = redemption_scope

    # Idempotency-Key store (M-26). In local and test a per-process dict is
    # enough; everywhere else it must be Redis, so a restart does not turn a
    # repeat into a new operation.
    from app.bss_lines.repositories.idempotency import (
        InMemoryIdempotencyStore,
        RedisIdempotencyStore,
    )

    if settings.ratel_env in ("local", "test"):
        app.state.idempotency_store = InMemoryIdempotencyStore()
    else:
        import redis

        app.state.idempotency_store = RedisIdempotencyStore(
            redis.Redis.from_url(settings.redis_url.get_secret_value())
        )

    @contextmanager
    def catalog_scope() -> Iterator[BundleCatalog]:
        with app.state.session_factory() as session, session.begin():
            yield SqlBundleCatalog(session)

    app.state.catalog_scope = catalog_scope

    @contextmanager
    def desk_read_scope() -> Iterator[DeskReads]:
        with app.state.session_factory() as session, session.begin():
            yield DeskReads(
                money=SqlMoneyReadRepository(session), lines=SqlDeskReadRepository(session)
            )

    app.state.desk_read_scope = desk_read_scope

    # BSS: lines asks BSS: money whether a line has paid for data, and may not import it, so the
    # answer is wired here. Given a session, it returns the checker (services/activation.py).
    app.state.paid_plan_check = SqlPaidPlanCheck

    @contextmanager
    def purchase_scope() -> Iterator[PurchaseRepositories]:
        # One transaction per purchase: the debit, its VAT entry and the bucket go together or not.
        with app.state.session_factory() as session, session.begin():
            yield PurchaseRepositories(
                purchases=SqlPurchaseRepository(session), ledger=SqlLedgerRepository(session)
            )

    app.state.purchase_scope = purchase_scope

    @contextmanager
    def payment_scope() -> Iterator[PaymentRepositories]:
        # One transaction per step; the step commits on a normal return (refusals included).
        with app.state.session_factory() as session, session.begin():
            yield PaymentRepositories(
                payments=SqlPaymentRepository(session),
                ledger=SqlLedgerRepository(session),
                lines=SqlLineLookup(session),
            )

    app.state.payment_scope = payment_scope
    secret = settings.paystack_secret_key_value
    app.state.payment_gateway = (
        PaystackGateway(secret, base_url=settings.paystack_base_url) if secret else None
    )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        # Liveness only. TODO: readiness check (PostgreSQL, Redis) once models exist.
        return {"status": "ok"}

    @app.middleware("http")
    async def _handle_options(request: Request, call_next: Any) -> Response:
        if request.method == "OPTIONS" and request.url.path == "/v1/usage":
            return Response(status_code=200, headers={"Allow": "GET, POST, OPTIONS"})
        return cast(Response, await call_next(request))

    # Network access rules (RatelDesk and API only over the WireGuard VPN; RatelPay and the
    # payment webhook are the only public paths) are enforced at the reverse proxy and
    # documented in deploy/bss-app/README.md.
    app.include_router(staff_router)
    # Before the desk router: /v1/lines/lookup must be tried before /v1/lines/{line_id}.
    app.include_router(bss_lines_router)
    app.include_router(desk_router)
    app.include_router(desk_reads_router)
    app.include_router(kyc_router)
    app.include_router(bss_money_router)
    app.include_router(money_desk_router)
    app.include_router(purchases_router)
    app.include_router(payments_router)
    app.include_router(bundles_router)
    app.include_router(meter_api_router)
    return app
