"""The nightly wallet-versus-ledger check. Run by a timer on bss-app (deploy/bss-app, M-27).

    python -m app.bss_money.check_cli

Exit 0: every wallet equals the sum of its ledger entries. Exit 1: at least one differs; each is
logged as `ledger.wallet_mismatch`. Exit 2: the check could not run (the database did not answer).
Until RatelOps has alerting (TODO(RatelOps)) a non-zero exit shows as a failed unit in systemd.

An entry point: it builds the database session and the repository and hands them to the service.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError

from app.bss_money.repositories.sql import SqlLedgerRepository
from app.bss_money.services.wallet_check import check_wallets
from app.config import Settings
from app.db import make_engine, session_factory
from common.logging import configure_logging, log_event

log = logging.getLogger("ratel.bss.money.check")


def main(argv: Sequence[str] | None = None) -> int:
    settings = Settings()
    configure_logging(settings.log_level, stream=sys.stderr)
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        with session_factory(engine)() as session:
            mismatches = check_wallets(SqlLedgerRepository(session))
    except SQLAlchemyError as exc:
        # Type only: a driver message can carry the database host and user.
        log_event(log, logging.ERROR, "ledger.check.failed", exc_type=type(exc).__name__)
        return 2
    finally:
        engine.dispose()
    sys.stderr.write(f"{len(mismatches)} wallet(s) differ from their ledger\n")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
