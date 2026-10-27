"""Redeeming prepaid cards: once, with a limit on guessing, and nothing to learn from a refusal."""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bss_money.domain.vouchers import (
    InvalidVoucherTransition,
    VoucherState,
    luhn_check_digit,
)
from app.bss_money.models.ledger import LedgerEntry
from app.bss_money.models.vouchers import Voucher, VoucherAttempt
from app.bss_money.repositories.sql import SqlLedgerRepository, SqlVoucherRepository
from app.bss_money.services.vouchers import (
    RedeemResult,
    RedeemStatus,
    create_batch,
    set_batch_state,
    set_card_state,
)
from tests.app.bss_money.vouchers_data import FACE, T0, issue, redeem, wrong_pin

REFUSED = RedeemResult(RedeemStatus.REFUSED)


def _balance(session: Session, line: int = 1) -> int | None:
    return SqlLedgerRepository(session).balance(line)


def _attempts(session: Session) -> int:
    return session.scalar(select(func.count(VoucherAttempt.attempt_id))) or 0


def test_redeeming_credits_the_face_value_to_the_wallet(session: Session) -> None:
    [card] = issue(session)

    result = redeem(session, card.card_number, card.pin, line=7)

    assert result == RedeemResult(RedeemStatus.REDEEMED, FACE, FACE)
    assert _balance(session, 7) == FACE
    voucher = session.scalars(select(Voucher)).one()
    assert (voucher.state, voucher.used_by_line_id) == ("used", 7)


def test_the_ledger_entry_names_the_voucher_never_the_card_or_pin(session: Session) -> None:
    [card] = issue(session)
    redeem(session, card.card_number, card.pin)

    entry = session.scalars(select(LedgerEntry)).one()
    assert (entry.kind, entry.amount_kobo) == ("top_up", FACE)
    assert card.card_number not in entry.reference
    assert card.pin not in entry.reference


def test_redeeming_twice_credits_once(session: Session) -> None:
    [card] = issue(session)

    first = redeem(session, card.card_number, card.pin)
    second = redeem(session, card.card_number, card.pin)

    assert first == RedeemResult(RedeemStatus.REDEEMED, FACE, FACE)
    assert second == RedeemResult(RedeemStatus.REDEEMED, FACE, FACE, replayed=True)  # a retry
    assert _balance(session) == FACE
    assert session.scalar(select(func.count(LedgerEntry.entry_id))) == 1
    assert _attempts(session) == 0  # a retry is not a failure


def test_a_retry_with_the_wrong_pin_after_redeeming_is_just_a_refusal(session: Session) -> None:
    [card] = issue(session)
    redeem(session, card.card_number, card.pin)

    assert redeem(session, card.card_number, wrong_pin(card.pin)) == REFUSED
    assert _attempts(session) == 1


def test_a_card_used_on_one_line_cannot_be_used_on_another(session: Session) -> None:
    [card] = issue(session)
    redeem(session, card.card_number, card.pin, line=1)

    assert redeem(session, card.card_number, card.pin, line=2) == REFUSED
    assert _balance(session, 2) is None


def test_a_wrong_pin_is_refused_and_counted(session: Session) -> None:
    [card] = issue(session)

    assert redeem(session, card.card_number, wrong_pin(card.pin)) == REFUSED
    assert _attempts(session) == 1
    assert _balance(session) is None


def test_every_reason_for_refusing_looks_the_same_to_the_caller(session: Session) -> None:
    [good] = issue(session, batch="good")
    [used] = issue(session, batch="used")
    redeem(session, used.card_number, used.pin, line=1)
    [stock] = issue(session, batch="stock", to=VoucherState.IN_STOCK)
    [locked] = issue(session, batch="locked")
    set_card_state(SqlVoucherRepository(session), 4, VoucherState.LOCKED)
    [expired] = issue(session, batch="expired", expires_at=T0 - timedelta(days=1))

    results = [
        redeem(session, "9" * 20, good.pin),  # no such card
        redeem(session, good.card_number, wrong_pin(good.pin)),  # wrong PIN
        redeem(session, used.card_number, used.pin, line=2),  # already used, by another line
        redeem(session, stock.card_number, stock.pin),  # not on sale yet
        redeem(session, locked.card_number, locked.pin),  # lost or stolen
        redeem(session, expired.card_number, expired.pin),  # expired
    ]

    assert results == [REFUSED] * 6
    assert _balance(session) == FACE  # only the one real redemption (the "used" card) paid


def test_a_typo_is_told_apart_and_does_not_count_against_the_limit(session: Session) -> None:
    [card] = issue(session)
    bad_check = card.pin[:-1] + str((int(card.pin[-1]) + 1) % 10)

    assert redeem(session, card.card_number, bad_check).status is RedeemStatus.MALFORMED
    assert redeem(session, card.card_number[:-1], card.pin).status is RedeemStatus.MALFORMED
    assert redeem(session, card.card_number, card.pin[:-1]).status is RedeemStatus.MALFORMED
    assert redeem(session, "x" * 20, card.pin).status is RedeemStatus.MALFORMED
    assert _attempts(session) == 0
    assert redeem(session, card.card_number, card.pin).status is RedeemStatus.REDEEMED


def test_the_sixth_failed_attempt_in_an_hour_is_refused_even_with_the_right_pin(
    session: Session,
) -> None:
    [card] = issue(session)
    for minute in range(5):
        wrong = redeem(
            session, card.card_number, wrong_pin(card.pin), now=T0 + timedelta(minutes=minute)
        )
        assert wrong == REFUSED

    sixth = redeem(session, card.card_number, card.pin, now=T0 + timedelta(minutes=5))

    assert sixth.status is RedeemStatus.TOO_MANY_ATTEMPTS
    assert _balance(session) is None
    assert _attempts(session) == 5  # the refusal itself is not another failure


def test_four_failures_leave_the_right_pin_working(session: Session) -> None:
    [card] = issue(session)
    for minute in range(4):
        redeem(session, card.card_number, wrong_pin(card.pin), now=T0 + timedelta(minutes=minute))

    assert redeem(session, card.card_number, card.pin, now=T0 + timedelta(minutes=4)).status is (
        RedeemStatus.REDEEMED
    )


def test_the_limit_lifts_once_the_failures_are_an_hour_old(session: Session) -> None:
    [card] = issue(session)
    for _ in range(5):
        redeem(session, card.card_number, wrong_pin(card.pin), now=T0)

    just_inside = redeem(
        session, card.card_number, card.pin, now=T0 + timedelta(minutes=59, seconds=59)
    )
    exactly_an_hour = redeem(session, card.card_number, card.pin, now=T0 + timedelta(hours=1))

    assert just_inside.status is RedeemStatus.TOO_MANY_ATTEMPTS
    assert exactly_an_hour.status is RedeemStatus.REDEEMED


def test_the_limit_is_per_card_number(session: Session) -> None:
    [one, two] = issue(session, count=2)
    for _ in range(5):
        redeem(session, one.card_number, wrong_pin(one.pin))

    assert redeem(session, one.card_number, one.pin).status is RedeemStatus.TOO_MANY_ATTEMPTS
    assert redeem(session, two.card_number, two.pin).status is RedeemStatus.REDEEMED


def test_guessing_at_a_number_that_does_not_exist_is_limited_in_the_same_way(
    session: Session,
) -> None:
    [card] = issue(session)
    ghost = "1" * 20
    answers = [redeem(session, ghost, card.pin).status for _ in range(7)]

    assert answers == [RedeemStatus.REFUSED] * 5 + [RedeemStatus.TOO_MANY_ATTEMPTS] * 2


def test_a_card_that_expired_by_date_is_refused(session: Session) -> None:
    [card] = issue(session, expires_at=T0)

    assert redeem(session, card.card_number, card.pin, now=T0 - timedelta(seconds=1)).status is (
        RedeemStatus.REDEEMED
    )
    [other] = issue(session, batch="b2", expires_at=T0)
    assert redeem(session, other.card_number, other.pin, now=T0) == REFUSED


def test_nothing_secret_reaches_a_log_line(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    [good, other] = issue(session, count=2)

    redeem(session, good.card_number, good.pin)  # success
    redeem(session, good.card_number, good.pin)  # refused: used
    redeem(session, other.card_number, wrong_pin(other.pin))  # refused: wrong PIN
    for _ in range(5):  # and locked out
        redeem(session, other.card_number, wrong_pin(other.pin))

    text = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "voucher.redeemed" in text
    assert "voucher.refused" in text
    assert "voucher.locked_out" in text
    for secret in (good.card_number, good.pin, other.card_number, other.pin):
        assert secret not in text
        assert secret[-4:] not in text or len(secret) < 4  # not even masked: it is never logged


def test_no_pin_is_stored_anywhere_in_the_database(session: Session) -> None:
    cards = issue(session, count=3)
    stored = " ".join(
        str(v) for row in session.execute(select(Voucher)).all() for v in row[0].__dict__.values()
    )

    for card in cards:
        assert card.pin not in stored


def test_the_clock_must_carry_a_timezone(session: Session) -> None:
    [card] = issue(session)
    with pytest.raises(ValueError, match="timezone"):
        redeem(session, card.card_number, card.pin, now=T0.replace(tzinfo=None))


# --- batches and states ---------------------------------------------------------------------


def test_a_new_batch_is_requested_hashed_and_prints_valid_pins(session: Session) -> None:
    cards = issue(session, count=20, to=VoucherState.REQUESTED)

    rows = session.scalars(select(Voucher)).all()
    assert len(rows) == 20
    assert {r.state for r in rows} == {"requested"}
    assert len({c.card_number for c in cards}) == 20
    assert all(luhn_check_digit(c.pin[:-1]) == c.pin[-1] for c in cards)
    assert all(r.pin_hash.startswith("scrypt$") for r in rows)


def test_a_batch_that_asks_for_nonsense_is_refused(session: Session) -> None:
    vouchers = SqlVoucherRepository(session)
    for kwargs in (
        {"batch": "", "count": 1, "face_value_kobo": 100},
        {"batch": "bad name!", "count": 1, "face_value_kobo": 100},
        {"batch": "b", "count": 0, "face_value_kobo": 100},
        {"batch": "b", "count": 5001, "face_value_kobo": 100},
        {"batch": "b", "count": 1, "face_value_kobo": 0},
        {"batch": "b", "count": 1, "face_value_kobo": -5},
        {"batch": "b", "count": 1, "face_value_kobo": 10.5},
        {"batch": "b", "count": 1, "face_value_kobo": True},
    ):
        with pytest.raises(ValueError):
            create_batch(vouchers, **kwargs)  # type: ignore[arg-type]
    assert session.scalar(select(func.count(Voucher.voucher_id))) == 0


def test_a_batch_moves_along_the_printing_path_in_order(session: Session) -> None:
    issue(session, count=3, to=VoucherState.REQUESTED)
    vouchers = SqlVoucherRepository(session)

    assert set_batch_state(vouchers, "b1", VoucherState.APPROVED) == 3
    with pytest.raises(InvalidVoucherTransition):
        set_batch_state(vouchers, "b1", VoucherState.ON_SALE)  # cannot skip the printer
    assert {s for _, s in vouchers.batch_cards("b1")} == {VoucherState.APPROVED}


def test_one_card_that_cannot_move_stops_the_whole_batch_from_moving(session: Session) -> None:
    issue(session, count=3, to=VoucherState.APPROVED)
    vouchers = SqlVoucherRepository(session)
    set_card_state(vouchers, 2, VoucherState.LOCKED)  # lost on the way to the printer

    with pytest.raises(InvalidVoucherTransition):
        set_batch_state(vouchers, "b1", VoucherState.SENT_TO_PRINTER)

    assert [s for _, s in vouchers.batch_cards("b1")] == [
        VoucherState.APPROVED,
        VoucherState.LOCKED,
        VoucherState.APPROVED,
    ]


def test_an_unknown_batch_or_card_is_an_error(session: Session) -> None:
    vouchers = SqlVoucherRepository(session)
    with pytest.raises(LookupError):
        set_batch_state(vouchers, "nope", VoucherState.APPROVED)
    with pytest.raises(LookupError):
        set_card_state(vouchers, 999, VoucherState.LOCKED)


def test_a_locked_card_cannot_be_redeemed_and_stays_locked(session: Session) -> None:
    [card] = issue(session)
    set_card_state(SqlVoucherRepository(session), 1, VoucherState.LOCKED)

    assert redeem(session, card.card_number, card.pin) == REFUSED
    with pytest.raises(InvalidVoucherTransition):
        set_card_state(SqlVoucherRepository(session), 1, VoucherState.ON_SALE)
