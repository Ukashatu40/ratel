"""What the SMS short number 555 and USSD may do for a line, by its phone number.

Reached only through the reverse proxy, which lets the voice VM in on exact paths and adds the
payments key (deploy/bss-app/nginx). The number comes from the network (the SMS centre or the
S-CSCF asserts who sent it), never from what a customer typed.

- The balance: airtime, and the data left in buckets valid now.
- Buying a bundle from airtime: the same purchase as at RatelDesk (services/purchase.py), for a
  bundle that lists the channel it is bought from.
- The customer SMS queue (docs/customer-sms.md): what is due, with its text, and marking one sent.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.bss_money.domain.allowance import Bucket
from app.bss_money.repositories.ports import (
    CustomerSmsRepository,
    LedgerRepository,
    LineLookup,
    PendingSms,
)


class BucketReader(Protocol):
    def buckets(self, line_id: int) -> list[Bucket]: ...


@dataclass(frozen=True)
class PayLineRepositories:
    lines: LineLookup
    ledger: LedgerRepository
    buckets: BucketReader
    sms: CustomerSmsRepository


PayLineScope = Callable[[], AbstractContextManager[PayLineRepositories]]


class UnknownNumber(Exception):
    pass


@dataclass(frozen=True)
class LineBalance:
    balance_kobo: int
    data_bytes_left: int
    data_valid_to: datetime | None  # the latest end among buckets with data left


def line_id(scope: PayLineScope, msisdn: str) -> int:
    with scope() as repositories:
        found = repositories.lines.line_id_for_msisdn(msisdn)
    if found is None:
        raise UnknownNumber("no live line has this number")
    return found


def balance(scope: PayLineScope, msisdn: str, now: datetime) -> LineBalance:
    with scope() as repositories:
        found = repositories.lines.line_id_for_msisdn(msisdn)
        if found is None:
            raise UnknownNumber("no live line has this number")
        wallet = repositories.ledger.balance(found) or 0
        left = 0
        valid_to: datetime | None = None
        for bucket in repositories.buckets.buckets(found):
            remaining = bucket.data_bytes_total - bucket.data_bytes_used
            if remaining <= 0 or bucket.valid_from > now or bucket.valid_to <= now:
                continue
            left += remaining
            valid_to = bucket.valid_to if valid_to is None else max(valid_to, bucket.valid_to)
    return LineBalance(balance_kobo=wallet, data_bytes_left=left, data_valid_to=valid_to)


class NoSuchSms(Exception):
    pass


def sms_due(scope: PayLineScope, limit: int) -> list[PendingSms]:
    with scope() as repositories:
        return repositories.sms.pending(limit)


def mark_sms_sent(scope: PayLineScope, sms_id: int, now: datetime) -> datetime:
    """When it was sent. The first call records it; a repeat answers the same time."""
    with scope() as repositories:
        sent_at = repositories.sms.mark_sent(sms_id, now)
    if sent_at is None:
        raise NoSuchSms("no such SMS")
    return sent_at
