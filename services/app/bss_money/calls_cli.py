"""The call-charging job: voice calls paid from airtime, and the SMS that reports each one.
Run every minute by a timer on bss-app (deploy/bss-app, ratel-calls.timer).

    python -m app.bss_money.calls_cli

Off until CALL_CHARGING_FROM is set (docs/catalogue.md): it then logs `calls.charging_off` and
exits 0. Exit 0: done. Exit 1: finished but a call failed (`calls.charge_failed`; the next run
tries it again, nothing is lost). Exit 2: it could not run (the database did not answer).

Its own job, not part of the five-minute rating job, so the SMS after a call comes within about a
minute (docs/customer-sms.md). One run at a time: systemd does not start a timer's service again
while it is still running, and each call is charged once in its own transaction whatever happens.

An entry point: it builds the database session and hands it to services/call_charging.py.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError

from app.bss_money.domain.prepaid import parse_number_prefixes
from app.bss_money.repositories.ports import CallChargeRepositories
from app.bss_money.repositories.sql import (
    SqlCallChargeRepository,
    SqlCatalogueRepository,
    SqlCustomerSmsRepository,
    SqlLedgerRepository,
)
from app.bss_money.services.call_charging import charge_calls
from app.config import Settings
from app.db import make_engine, session_factory
from common.logging import configure_logging, log_event

log = logging.getLogger("ratel.bss.money.calls")


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    settings = Settings()
    configure_logging(settings.log_level, stream=sys.stderr)
    if settings.call_charging_from is None:
        log_event(log, logging.INFO, "calls.charging_off")
        return 0
    engine = make_engine(settings.database_url.get_secret_value())
    sessions = session_factory(engine)

    @contextmanager
    def call_scope() -> Iterator[CallChargeRepositories]:
        with sessions() as session, session.begin():
            yield CallChargeRepositories(
                calls=SqlCallChargeRepository(session),
                ledger=SqlLedgerRepository(session),
                catalogue=SqlCatalogueRepository(session),
                sms=SqlCustomerSmsRepository(session),
            )

    try:
        run = charge_calls(
            call_scope,
            vat_rate_bps=settings.vat_rate_bps,
            charge_from=settings.call_charging_from,
            own_prefixes=parse_number_prefixes(settings.ratel_number_prefixes),
        )
    except SQLAlchemyError as exc:
        # Type only: a driver message can carry the database host and user.
        log_event(log, logging.ERROR, "calls.failed", exc_type=type(exc).__name__)
        return 2
    finally:
        engine.dispose()
    return 1 if run.failed else 0


if __name__ == "__main__":
    sys.exit(main())
