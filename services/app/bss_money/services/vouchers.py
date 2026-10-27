"""Voucher batches and redemption (M-18).

**The caller must commit after `redeem_voucher` returns, whatever the status.** A failed attempt is
written to count against the limit of five per card number per hour, and rolling the transaction
back would throw that record away. That is why a refusal is a result, not an exception.

What a caller learns from a refusal is one thing: it did not work. A wrong number, a wrong PIN, a
card already used, locked, not yet on sale or expired all look the same, and the work done is the
same, so the answer gives nothing to guess from. Two answers differ on purpose and say nothing
about any card: the digits are not well formed (a typo, caught by the check digit and not
counted), and the number has had five failures in the last hour (refused without looking at the
PIN).

The one exception is a repeat by the same line: if the card was already redeemed by this line and
the PIN is right, the answer is success again (`replayed`) and nothing more is credited, so a retry
after a lost reply does not turn a paid top-up into an error. Only someone holding both the number
and the PIN can see it, and only about their own line.

Nothing here logs a card number or a PIN.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.bss_money.domain.entries import new_posting
from app.bss_money.domain.pins import decoy_hash, hash_pin, verify_pin
from app.bss_money.domain.vouchers import (
    ATTEMPT_WINDOW_SECONDS,
    MAX_FAILED_ATTEMPTS,
    VoucherState,
    check_transition,
    is_card_number,
    is_pin,
    new_card_number,
    new_pin,
)
from app.bss_money.repositories.ports import (
    LedgerRepository,
    NewVoucher,
    VoucherNotRedeemable,
    VoucherRepository,
)
from common.logging import log_event

log = logging.getLogger("ratel.bss.money.vouchers")

BATCH_NAME = re.compile(r"[A-Za-z0-9._-]{1,40}")
MAX_BATCH_SIZE = 5000  # each card costs a slow hash, so a batch takes minutes, not seconds


class RedeemStatus(StrEnum):
    REDEEMED = "redeemed"
    MALFORMED = "malformed"  # not 20 digits, or a PIN whose check digit is wrong: a typo
    TOO_MANY_ATTEMPTS = "too_many_attempts"
    REFUSED = "refused"  # for any other reason, which the caller is not told


class Refusal(StrEnum):
    """Why a redemption was refused. For the log only, never for the caller."""

    NO_SUCH_CARD = "no_such_card"
    WRONG_PIN = "wrong_pin"
    NOT_ON_SALE = "not_on_sale"
    EXPIRED = "expired"


@dataclass(frozen=True)
class RedeemResult:
    status: RedeemStatus
    amount_kobo: int = 0
    balance_kobo: int = 0
    replayed: bool = False  # redeemed earlier by this line: nothing was credited this time


def redeem_voucher(
    vouchers: VoucherRepository,
    ledger: LedgerRepository,
    *,
    line_id: int,
    card_number: str,
    pin: str,
    now: datetime,
) -> RedeemResult:
    """Credit the card's face value to the line's wallet, once, if the number and PIN are right."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (UTC)")
    if not is_card_number(card_number) or not is_pin(pin):
        return RedeemResult(RedeemStatus.MALFORMED)

    card = vouchers.lock_card(card_number)  # one redemption at a time per number from here on
    since = now - timedelta(seconds=ATTEMPT_WINDOW_SECONDS)
    if vouchers.failed_attempts_since(card_number, since) >= MAX_FAILED_ATTEMPTS:
        log_event(log, logging.WARNING, "voucher.locked_out", line_id=line_id)
        return RedeemResult(RedeemStatus.TOO_MANY_ATTEMPTS)

    # The same slow hash whether or not the card exists, so the time taken says nothing.
    pin_ok = verify_pin(pin, decoy_hash() if card is None else card.pin_hash)
    refusal: Refusal | None = None
    if card is None:
        refusal = Refusal.NO_SUCH_CARD
    elif not pin_ok:
        refusal = Refusal.WRONG_PIN
    elif card.state is VoucherState.USED and card.used_by_line_id == line_id:
        balance = ledger.balance(line_id) or 0
        log_event(log, logging.INFO, "voucher.replayed", line_id=line_id)
        return RedeemResult(RedeemStatus.REDEEMED, card.face_value_kobo, balance, replayed=True)
    elif card.state is not VoucherState.ON_SALE:
        refusal = Refusal.NOT_ON_SALE
    elif card.expires_at is not None and card.expires_at <= now:
        refusal = Refusal.EXPIRED
    if refusal is not None or card is None:
        vouchers.record_failed_attempt(card_number, now)
        log_event(
            log,
            logging.WARNING,
            "voucher.refused",
            line_id=line_id,
            reason=(refusal or Refusal.NO_SUCH_CARD).value,
        )
        return RedeemResult(RedeemStatus.REFUSED)

    try:
        vouchers.mark_used(card.voucher_id, line_id, now)
    except VoucherNotRedeemable:  # cannot happen under the lock; if it does, nothing is credited
        vouchers.record_failed_attempt(card_number, now)
        return RedeemResult(RedeemStatus.REFUSED)
    posting = new_posting(line_id, card.face_value_kobo, "top_up", f"voucher-{card.voucher_id}")
    _, balance = ledger.append(posting)
    log_event(log, logging.INFO, "voucher.redeemed", line_id=line_id, voucher_id=card.voucher_id)
    return RedeemResult(RedeemStatus.REDEEMED, card.face_value_kobo, balance)


@dataclass(frozen=True)
class IssuedCard:
    """A new card as it is printed. The PIN exists here and nowhere else, and only this once."""

    voucher_id: int
    card_number: str
    pin: str


def create_batch(
    vouchers: VoucherRepository,
    *,
    batch: str,
    count: int,
    face_value_kobo: int,
    expires_at: datetime | None = None,
) -> list[IssuedCard]:
    """Make `count` new cards in the `requested` state, and return their numbers and PINs."""
    if not BATCH_NAME.fullmatch(batch):
        raise ValueError("batch must be 1 to 40 letters, digits, dots, dashes or underscores")
    if not 1 <= count <= MAX_BATCH_SIZE:
        raise ValueError(f"count must be between 1 and {MAX_BATCH_SIZE}")
    if isinstance(face_value_kobo, bool) or not isinstance(face_value_kobo, int):
        raise ValueError("face_value_kobo must be a whole number of kobo")
    if face_value_kobo <= 0:
        raise ValueError("face_value_kobo must be positive")  # TODO(PRD): the allowed face values
    cards = [(new_card_number(), new_pin()) for _ in range(count)]
    ids = vouchers.add_all(
        [
            NewVoucher(number, hash_pin(pin), face_value_kobo, batch, expires_at)
            for number, pin in cards
        ]
    )
    log_event(log, logging.INFO, "voucher.batch_created", batch=batch, count=count)
    return [IssuedCard(i, number, pin) for i, (number, pin) in zip(ids, cards, strict=True)]


def set_batch_state(vouchers: VoucherRepository, batch: str, target: VoucherState) -> int:
    """Move every card of the batch to `target`, or none if any cannot move. Returns how many."""
    cards = vouchers.batch_cards(batch)
    if not cards:
        raise LookupError("no such batch")
    for _, current in cards:
        check_transition(current, target)  # raises before anything has been changed
    for voucher_id, _ in cards:
        vouchers.set_state(voucher_id, target)
    log_event(
        log,
        logging.INFO,
        "voucher.batch_state",
        batch=batch,
        count=len(cards),
        to_state=target.value,
    )
    return len(cards)


def set_card_state(vouchers: VoucherRepository, voucher_id: int, target: VoucherState) -> None:
    """Move one card, for example to `locked` when it is reported lost or stolen."""
    current = vouchers.state_of(voucher_id)
    if current is None:
        raise LookupError("no such card")
    check_transition(current, target)
    vouchers.set_state(voucher_id, target)
    log_event(log, logging.INFO, "voucher.card_state", voucher_id=voucher_id, to_state=target.value)
