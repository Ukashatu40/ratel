"""Posting money. Idempotent: posting the same (line, kind, reference) again returns the first
entry and changes nothing.

Works inside the caller's transaction (the repository never commits), so related entries, a
purchase and its VAT, are posted together or not at all.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.bss_money.domain.entries import InvalidPosting, Posting
from app.bss_money.repositories.ports import (
    BalanceOutOfRange,
    DuplicateEntry,
    LedgerRepository,
)
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


def post_entry(repository: LedgerRepository, posting: Posting) -> PostingResult:
    """Append one entry to the ledger and move the wallet by the same amount."""
    try:
        stored, balance = repository.append(posting)
    except DuplicateEntry as duplicate:
        return _replay(repository, posting, duplicate)
    except BalanceOutOfRange:
        raise InvalidPosting("the balance would leave the supported range") from None
    log_event(
        log,
        logging.INFO,
        "ledger.entry.posted",
        entry_id=stored.entry_id,
        line_id=posting.line_id,
        kind=posting.kind.value,
        amount_kobo=posting.amount_kobo,
    )
    return PostingResult(
        stored.entry_id,
        posting.line_id,
        posting.amount_kobo,
        posting.kind.value,
        posting.reference,
        stored.created_at,
        balance,
        replayed=False,
    )


def _replay(
    repository: LedgerRepository, posting: Posting, duplicate: DuplicateEntry
) -> PostingResult:
    existing = repository.find(posting.line_id, posting.kind.value, posting.reference)
    if existing is None:
        raise duplicate  # cannot happen in an append-only ledger; do not paper over it
    if existing.amount_kobo != posting.amount_kobo:
        raise ReferenceConflict("this reference was already posted with a different amount")
    balance = repository.balance(posting.line_id)
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
