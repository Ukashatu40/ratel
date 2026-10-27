"""Synthetic voucher batches for the tests. Nothing here is a real card."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.bss_money.domain.vouchers import VoucherState
from app.bss_money.repositories.sql import SqlLedgerRepository, SqlVoucherRepository
from app.bss_money.services.vouchers import (
    IssuedCard,
    RedeemResult,
    create_batch,
    redeem_voucher,
    set_batch_state,
)

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
FACE = 50_000  # kobo
PATH = (
    VoucherState.APPROVED,
    VoucherState.SENT_TO_PRINTER,
    VoucherState.IN_STOCK,
    VoucherState.ON_SALE,
)


def issue(
    session: Session,
    *,
    batch: str = "b1",
    count: int = 1,
    to: VoucherState | None = None,
    face: int = FACE,
    expires_at: datetime | None = None,
) -> list[IssuedCard]:
    """New cards, moved along the printing path as far as `to` (default: on sale)."""
    vouchers = SqlVoucherRepository(session)
    cards = create_batch(
        vouchers, batch=batch, count=count, face_value_kobo=face, expires_at=expires_at
    )
    target = VoucherState.ON_SALE if to is None else to
    if target is not VoucherState.REQUESTED:
        for step in PATH:
            set_batch_state(vouchers, batch, step)
            if step is target:
                break
    return cards


def redeem(
    session: Session, card_number: str, pin: str, *, line: int = 1, now: datetime = T0
) -> RedeemResult:
    return redeem_voucher(
        SqlVoucherRepository(session),
        SqlLedgerRepository(session),
        line_id=line,
        card_number=card_number,
        pin=pin,
        now=now,
    )


def wrong_pin(pin: str) -> str:
    """A well formed PIN that is not `pin`."""
    from app.bss_money.domain.vouchers import luhn_check_digit

    body = pin[:-1]
    other = f"{(int(body[-1]) + 1) % 10}"
    body = body[:-1] + other
    return body + luhn_check_digit(body)
