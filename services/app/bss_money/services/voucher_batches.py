"""Voucher batches managed in RatelDesk (domain/voucher_batches.py; voucher-batches.md runbook).

Every step is one transaction and leaves a `voucher_event` row with who took it and why. Printing
is the only place PINs exist: they are made, hashed for storage and laid out on the PDF in the
same transaction, and the PDF is handed back once. If anything fails, no card is kept.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.bss_money.domain.pins import hash_pin
from app.bss_money.domain.voucher_batches import (
    BatchState,
    BatchStepRefused,
    check_advance,
    check_lock,
    check_print,
    check_request,
)
from app.bss_money.domain.vouchers import (
    ATTEMPT_WINDOW_SECONDS,
    MAX_FAILED_ATTEMPTS,
    VoucherState,
    check_transition,
    new_card_number,
    new_pin,
)
from app.bss_money.repositories.ports import (
    BatchView,
    CardView,
    NewVoucher,
    VoucherAdminScope,
)
from app.bss_money.services.catalogue import settings_or_default
from app.bss_money.services.voucher_sheet import SheetBatch, SheetCard, render
from common.logging import log_event

log = logging.getLogger("ratel.bss.money.voucher_batches")

WAT = timezone(timedelta(hours=1), "WAT")  # Nigeria keeps no daylight saving
_FINAL = (VoucherState.USED, VoucherState.EXPIRED, VoucherState.LOCKED)


class BatchNotFound(LookupError):
    pass


def list_batches(scope: VoucherAdminScope, *, limit: int = 100) -> list[BatchView]:
    with scope() as repositories:
        return repositories.admin.batches(limit)


def voucher_values(scope: VoucherAdminScope) -> tuple[int, ...]:
    with scope() as repositories:
        return settings_or_default(repositories.catalogue).voucher_values_kobo


def request_batch(
    scope: VoucherAdminScope,
    *,
    actor: str,
    face_value_kobo: int,
    card_count: int,
    reason: str,
    idempotency_key: str,
) -> tuple[BatchView, bool]:
    """(the batch, True when this key had made it already). No card exists yet."""
    with scope() as repositories:
        earlier = repositories.admin.batch_for_key(idempotency_key)
        if earlier is not None:
            return earlier, True
        values = settings_or_default(repositories.catalogue).voucher_values_kobo
        check_request(face_value_kobo, card_count, values)
        batch = repositories.admin.add_batch(
            face_value_kobo=face_value_kobo,
            card_count=card_count,
            requested_by=actor,
            idempotency_key=idempotency_key,
        )
        repositories.admin.add_event(
            actor=actor,
            action="request",
            reason=reason,
            detail=f"{card_count} cards of {face_value_kobo} kobo",
            batch_id=batch.batch_id,
        )
    log_event(log, logging.INFO, "voucher.batch_requested", batch=batch.name, count=card_count)
    return batch, False


def advance_batch(
    scope: VoucherAdminScope, *, batch_id: int, to: BatchState, actor: str, reason: str
) -> BatchView:
    """Approve, mark in stock or put on sale. Asked again for where it already is: no change."""
    with scope() as repositories:
        batch = repositories.admin.batch(batch_id, lock=True)
        if batch is None:
            raise BatchNotFound
        current = BatchState(batch.state)
        if current is to:
            return batch
        check_advance(current, to)
        if to is not BatchState.APPROVED:  # the cards exist from printing on and move with it
            cards = repositories.admin.cards_of(batch.name)
            moving = [(vid, state) for vid, state in cards if state not in _FINAL]
            for _, state in moving:  # all or none: checked before anything changes
                check_transition(state, VoucherState(to.value))
            repositories.admin.set_card_states([vid for vid, _ in moving], VoucherState(to.value))
        repositories.admin.set_batch(
            batch_id,
            state=to.value,
            approved_by=actor if to is BatchState.APPROVED else None,
        )
        repositories.admin.add_event(
            actor=actor, action=to.value, reason=reason, detail="", batch_id=batch_id
        )
        moved = repositories.admin.batch(batch_id)
    assert moved is not None
    log_event(log, logging.INFO, "voucher.batch_state", batch=batch.name, to_state=to.value)
    return moved


def print_batch(scope: VoucherAdminScope, *, batch_id: int, actor: str, now: datetime) -> bytes:
    """Make the batch's cards and PINs and return the sheet (PDF). Once per batch."""
    with scope() as repositories:
        batch = repositories.admin.batch(batch_id, lock=True)
        if batch is None:
            raise BatchNotFound
        check_print(BatchState(batch.state))
        pins = [new_pin() for _ in range(batch.card_count)]
        numbers = [new_card_number() for _ in range(batch.card_count)]
        with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
            hashes = list(pool.map(hash_pin, pins))  # scrypt lets other threads run
        repositories.admin.add_cards(
            [
                NewVoucher(number, pin_hash, batch.face_value_kobo, batch.name, None)
                for number, pin_hash in zip(numbers, hashes, strict=True)
            ],
            VoucherState.SENT_TO_PRINTER,
        )
        repositories.admin.set_batch(
            batch_id, state=BatchState.SENT_TO_PRINTER.value, printed_by=actor, printed_at=now
        )
        repositories.admin.add_event(
            actor=actor,
            action="print",
            reason="printed the sheet",
            detail=f"{batch.card_count} cards made; the PINs left only on the PDF",
            batch_id=batch_id,
        )
        pdf = render(
            SheetBatch(
                name=batch.name,
                face_value_kobo=batch.face_value_kobo,
                card_count=batch.card_count,
                printed_at=now.astimezone(WAT),
                printed_by=actor,
            ),
            [
                SheetCard(serial=i, card_number=number, pin=pin)
                for i, (number, pin) in enumerate(zip(numbers, pins, strict=True), start=1)
            ],
        )
    log_event(log, logging.INFO, "voucher.batch_printed", batch=batch.name, count=len(pins))
    return pdf


def lock_batch(scope: VoucherAdminScope, *, batch_id: int, actor: str, reason: str) -> BatchView:
    """Lock the batch and every card of it that is not used: none of them can be redeemed."""
    with scope() as repositories:
        batch = repositories.admin.batch(batch_id, lock=True)
        if batch is None:
            raise BatchNotFound
        check_lock(BatchState(batch.state))
        cards = repositories.admin.cards_of(batch.name)
        locking = [vid for vid, state in cards if state not in _FINAL]
        repositories.admin.set_card_states(locking, VoucherState.LOCKED)
        repositories.admin.set_batch(batch_id, state=BatchState.LOCKED.value)
        repositories.admin.add_event(
            actor=actor,
            action="lock_batch",
            reason=reason,
            detail=f"{len(locking)} cards locked",
            batch_id=batch_id,
        )
        locked = repositories.admin.batch(batch_id)
    assert locked is not None
    log_event(log, logging.INFO, "voucher.batch_locked", batch=batch.name, count=len(locking))
    return locked


@dataclass(frozen=True)
class CardLookup:
    card: CardView
    failed_attempts: int  # in the last hour
    max_attempts: int


def lookup_card(scope: VoucherAdminScope, *, card_number: str, now: datetime) -> CardLookup | None:
    with scope() as repositories:
        card = repositories.admin.card(card_number)
        if card is None:
            return None
        since = now - timedelta(seconds=ATTEMPT_WINDOW_SECONDS)
        failed = repositories.vouchers.failed_attempts_since(card_number, since)
    return CardLookup(card, failed, MAX_FAILED_ATTEMPTS)


def lock_card(scope: VoucherAdminScope, *, voucher_id: int, actor: str, reason: str) -> CardView:
    """Lock one card (lost or stolen). A used, expired or locked card cannot be locked."""
    with scope() as repositories:
        card = repositories.admin.card_by_id(voucher_id, lock=True)
        if card is None:
            raise LookupError("no such card")
        if card.state in _FINAL:
            raise BatchStepRefused(f"a {card.state.value} card cannot be locked")
        check_transition(card.state, VoucherState.LOCKED)
        repositories.admin.set_card_states([voucher_id], VoucherState.LOCKED)
        repositories.admin.add_event(
            actor=actor,
            action="lock_card",
            reason=reason,
            detail=f"card ending {card.card_number[-4:]}",
            voucher_id=voucher_id,
        )
        locked = repositories.admin.card_by_id(voucher_id)
    assert locked is not None
    log_event(log, logging.INFO, "voucher.card_locked", voucher_id=voucher_id)
    return locked
