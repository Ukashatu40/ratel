"""The nightly check: every wallet must equal the sum of its ledger entries."""

from __future__ import annotations

import logging

from app.bss_money.domain.wallets import WalletMismatch
from app.bss_money.repositories.ports import LedgerRepository
from common.logging import log_event

log = logging.getLogger("ratel.bss.money.ledger")


def check_wallets(repository: LedgerRepository) -> list[WalletMismatch]:
    """Return every wallet that disagrees with its ledger, and log each one as an error."""
    mismatches = repository.mismatches()
    for m in mismatches:
        log_event(
            log,
            logging.ERROR,
            "ledger.wallet_mismatch",
            line_id=m.line_id,
            wallet_kobo=m.wallet_kobo,
            ledger_kobo=m.ledger_kobo,
        )
    return mismatches
