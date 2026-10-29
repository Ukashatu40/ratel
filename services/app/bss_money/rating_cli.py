"""The rating job. Run every five minutes by a timer on bss-app (deploy/bss-app, M-27).

    python -m app.bss_money.rating_cli

Exit 0: the run finished and every line was handled. Exit 1: it finished but at least one line
failed (logged as `rating.line_failed` or `rating.line_change_failed`; the next run tries again).
Exit 2: it could not run (the database did not answer, or RatelLink is not configured).

An entry point: it builds the database session and the RatelLink client and hands them to the job.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_lines.services.ratel_link_client import RatelLinkClient
from app.bss_money.gateways.paystack import PaystackGateway
from app.bss_money.repositories.ports import (
    PaymentRepositories,
    PurchaseRepositories,
    RatingRepository,
)
from app.bss_money.repositories.sql import (
    SqlLedgerRepository,
    SqlLineLookup,
    SqlPaymentRepository,
    SqlPurchaseRepository,
    SqlRatingRepository,
)
from app.bss_money.services.line_control import LifecycleLineControl
from app.bss_money.services.payments import settle_pending
from app.bss_money.services.purchase import renew_plan_if_covered
from app.bss_money.services.rating_job import run_rating
from app.config import Settings
from app.db import make_engine, session_factory
from common.logging import configure_logging, log_event

log = logging.getLogger("ratel.bss.money.rating")


def main(argv: Sequence[str] | None = None) -> int:
    settings = Settings()
    configure_logging(settings.log_level, stream=sys.stderr)
    key = settings.ratel_link_api_key
    if key is None:
        log_event(log, logging.ERROR, "rating.failed", reason="ratel_link_api_key_not_set")
        return 2
    engine = make_engine(settings.database_url.get_secret_value())
    sessions = session_factory(engine)

    @contextmanager
    def scope() -> Iterator[RatingRepository]:
        with sessions() as session, session.begin():
            yield SqlRatingRepository(session)

    @contextmanager
    def lines_scope() -> Iterator[SqlLinesRepository]:
        with sessions() as session:
            yield SqlLinesRepository(session)

    @contextmanager
    def payment_scope() -> Iterator[PaymentRepositories]:
        with sessions() as session, session.begin():
            yield PaymentRepositories(
                payments=SqlPaymentRepository(session),
                ledger=SqlLedgerRepository(session),
                lines=SqlLineLookup(session),
            )

    @contextmanager
    def purchase_scope() -> Iterator[PurchaseRepositories]:
        with sessions() as session, session.begin():
            yield PurchaseRepositories(
                purchases=SqlPurchaseRepository(session), ledger=SqlLedgerRepository(session)
            )

    now = datetime.now(UTC)
    paystack_key = settings.paystack_secret_key_value
    gateway = (
        PaystackGateway(paystack_key, base_url=settings.paystack_base_url) if paystack_key else None
    )

    def settle() -> int:
        assert gateway is not None
        return settle_pending(payment_scope, gateway, now)

    def renew(line_id: int) -> bool:
        bought = renew_plan_if_covered(
            purchase_scope, line_id=line_id, now=now, vat_rate_bps=settings.vat_rate_bps
        )
        return bought is not None

    client = RatelLinkClient(settings.ratel_link_base_url, key.get_secret_value())
    try:
        run = run_rating(
            scope,
            LifecycleLineControl(lines_scope, client),
            now=now,
            settle=settle if gateway is not None else None,
            renew=renew if settings.rating_auto_renew else None,
        )
    except SQLAlchemyError as exc:
        # Type only: a driver message can carry the database host and user.
        log_event(log, logging.ERROR, "rating.failed", exc_type=type(exc).__name__)
        return 2
    finally:
        engine.dispose()
    return 1 if run.failures else 0


if __name__ == "__main__":
    sys.exit(main())
