"""Posting money, and checking that the books still add up.

`post_entry` works inside the caller's transaction and never commits, so related entries (a
purchase and its VAT) are posted together or not at all. It is idempotent: posting the same
(line, kind, reference) again returns the first entry and changes nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.bss_money import repositories as repo
from app.bss_money.domain import InvalidPosting, Posting, WalletMismatch
from common.logging import log_event

log = logging.getLogger("ratel.bss.money.ledger")


class ReferenceConflict(Exception):
    """The same (line, kind, reference) was posted before with a different amount."""


@dataclass(frozen=True)
class PostingResult:
    entry_id: int
    line_id: int
    amount_kobo: int
    kind: str
    reference: str
    created_at: datetime | None
    balance_kobo: int
    replayed: bool  # True when this exact posting already existed and nothing changed


def post_entry(session: Session, posting: Posting) -> PostingResult:
    """Append one entry to the ledger and move the wallet by the same amount.

    The two changes sit inside a savepoint, so if either fails the caller's transaction is still
    usable and neither is kept.
    """
    repo.ensure_wallet(session, posting.line_id)
    try:
        with session.begin_nested():
            entry = repo.insert_entry(session, posting)
            balance = repo.add_to_balance(session, posting.line_id, posting.amount_kobo)
    except IntegrityError as exc:
        return _replay(session, posting, exc)
    except DataError as exc:
        # The balance would not fit the column. The savepoint is already rolled back.
        raise InvalidPosting("the balance would leave the supported range") from exc
    log_event(
        log,
        logging.INFO,
        "ledger.entry.posted",
        entry_id=entry.entry_id,
        line_id=posting.line_id,
        kind=posting.kind.value,
        amount_kobo=posting.amount_kobo,
    )
    return PostingResult(
        entry.entry_id,
        posting.line_id,
        posting.amount_kobo,
        posting.kind.value,
        posting.reference,
        entry.created_at,
        balance,
        replayed=False,
    )


def _replay(session: Session, posting: Posting, failure: IntegrityError) -> PostingResult:
    existing = repo.find_entry(session, posting.line_id, posting.kind.value, posting.reference)
    if existing is None:
        # Not a replay: some other integrity rule failed. Do not hide it.
        raise failure
    if existing.amount_kobo != posting.amount_kobo:
        raise ReferenceConflict("this reference was already posted with a different amount")
    balance = repo.wallet_balance(session, posting.line_id)
    log_event(log, logging.INFO, "ledger.entry.replayed", entry_id=existing.entry_id)
    return PostingResult(
        existing.entry_id,
        existing.line_id,
        existing.amount_kobo,
        existing.kind,
        existing.reference,
        existing.created_at,
        0 if balance is None else balance,
        replayed=True,
    )


def check_wallets(session: Session) -> list[WalletMismatch]:
    """The nightly check: every wallet must equal the sum of its entries. Logs each difference."""
    mismatches = repo.wallet_mismatches(session)
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
