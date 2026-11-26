"""Prepaid control of calls and SMS, asked by the voice VM (ADR 0013, docs/catalogue.md).

- authorize_call: at call set-up. A billed caller gets a limit of what their available airtime
  buys (balance minus what other calls hold), and that money is reserved for the call. The same
  Call-ID asked again gets the same answer and nothing more is reserved.
- end_call: at hang-up. The reservation shrinks to the call's cost, freeing the rest at once. The
  call is still charged from its call record (services/call_charging.py), which settles it.
- charge_sms: before the SMSC queues a text from a phone. Charged once per SMSC message id.

Charging of both starts at CALL_CHARGING_FROM (unset: calls unlimited, texts free).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.bss_lines.domain.state_machine import LineState
from app.bss_money.domain.entries import EntryKind, new_posting
from app.bss_money.domain.prepaid import (
    RESERVATION_GRACE_SECONDS,
    SELF_CARE_NUMBER,
    CallDecision,
    CallReason,
    SmsOutcome,
    cost_of,
    digits,
    is_free_number,
    limited_call,
)
from app.bss_money.domain.purchase import split_vat
from app.bss_money.domain.voice import national_msisdn
from app.bss_money.repositories.ports import PrepaidRepositories, PrepaidScope
from app.bss_money.services.catalogue import settings_or_default
from common.logging import log_event

log = logging.getLogger("ratel.bss.money.prepaid")

# A line in one of these states may call and text from airtime; any other (suspended) may not.
_CAN_SPEND = (LineState.ACTIVE, LineState.OUT_OF_DATA, LineState.EXPIRED)


def _charging(charge_from: datetime | None, now: datetime) -> bool:
    return charge_from is not None and now >= charge_from


def _available(repositories: PrepaidRepositories, line_id: int, now: datetime) -> int:
    balance = repositories.ledger.balance(line_id) or 0
    return balance - repositories.prepaid.held_kobo(line_id, now)


def authorize_call(
    scope: PrepaidScope,
    *,
    call_id: str,
    caller: str,
    dialled: str,
    free_numbers: frozenset[str],
    charge_from: datetime | None,
    now: datetime,
) -> CallDecision:
    if is_free_number(dialled, free_numbers):
        return _logged(CallDecision(True, 0, CallReason.FREE_NUMBER), None)
    if not _charging(charge_from, now):
        return _logged(CallDecision(True, 0, CallReason.CHARGING_OFF), None)
    caller_msisdn = national_msisdn(digits(caller))
    with scope() as repositories:
        line = repositories.prepaid.lock_line(caller_msisdn) if caller_msisdn else None
        if line is None:
            return _logged(CallDecision(True, 0, CallReason.NOT_BILLED), None)
        if line.state not in _CAN_SPEND:
            return _logged(CallDecision(False, 0, CallReason.LINE_NOT_IN_SERVICE), line.line_id)
        existing = repositories.prepaid.reservation(call_id)
        if existing is not None:  # the same call asked again: the same answer
            return _logged(
                CallDecision(True, existing.max_seconds, CallReason.LIMITED), line.line_id
            )
        settings = settings_or_default(repositories.catalogue)
        callee = national_msisdn(digits(dialled))
        on_net = callee is not None and repositories.prepaid.is_ratel_number(callee)
        rate = settings.voice_onnet_kobo_per_min if on_net else settings.voice_offnet_kobo_per_min
        decision, reserve = limited_call(_available(repositories, line.line_id, now), rate)
        if decision.allowed:
            repositories.prepaid.add_reservation(
                call_id=call_id,
                line_id=line.line_id,
                rate_kobo_per_min=rate,
                max_seconds=decision.max_seconds,
                reserved_kobo=reserve,
                expires_at=now
                + timedelta(seconds=decision.max_seconds + RESERVATION_GRACE_SECONDS),
            )
    return _logged(decision, line.line_id)


def end_call(scope: PrepaidScope, *, call_id: str, seconds: int) -> bool:
    """True when an open reservation was shrunk to the call's cost; False when there was none."""
    with scope() as repositories:
        reservation = repositories.prepaid.reservation(call_id)
        if reservation is None or reservation.state != "open":
            return False
        used = max(0, min(seconds, reservation.max_seconds))
        cost = min(cost_of(used, reservation.rate_kobo_per_min), reservation.reserved_kobo)
        repositories.prepaid.end_reservation(call_id, used, cost)
    log_event(log, logging.INFO, "calls.ended", line_id=reservation.line_id, seconds=used)
    return True


def charge_sms(
    scope: PrepaidScope,
    *,
    message_id: str,
    sender: str,
    recipient: str,
    vat_rate_bps: int,
    charge_from: datetime | None,
    now: datetime,
) -> tuple[SmsOutcome, int]:
    """(outcome, kobo charged). The same message id asked again gets the first answer."""
    to = digits(recipient)
    sender_msisdn = national_msisdn(digits(sender))
    with scope() as repositories:
        # The line is locked first, so a retry arriving at the same time waits and then finds the
        # first answer instead of charging again.
        line = repositories.prepaid.lock_line(sender_msisdn) if sender_msisdn else None
        earlier = repositories.prepaid.sms_charge(message_id)
        if earlier is not None:
            return SmsOutcome(earlier.outcome), earlier.charged_kobo
        line_id = None if line is None else line.line_id
        callee = national_msisdn(to)
        on_net = callee is not None and repositories.prepaid.is_ratel_number(callee)
        price = 0
        if to == SELF_CARE_NUMBER:
            outcome = SmsOutcome.FREE_SELF_CARE
        elif not on_net:
            outcome = SmsOutcome.REFUSED_OFF_NET
        elif not _charging(charge_from, now):
            outcome = SmsOutcome.FREE_CHARGING_OFF
        elif line is None:
            outcome = SmsOutcome.NOT_BILLED
        elif line.state not in _CAN_SPEND:
            outcome = SmsOutcome.REFUSED_NOT_IN_SERVICE
        else:
            settings = settings_or_default(repositories.catalogue)
            price = settings.sms_onnet_kobo
            if price > _available(repositories, line.line_id, now):
                outcome, price = SmsOutcome.REFUSED_BALANCE, 0
            else:
                outcome = SmsOutcome.CHARGED
                net, vat = split_vat(price, vat_rate_bps)
                reference = f"sms:{message_id}"
                if net:
                    repositories.ledger.append(
                        new_posting(line.line_id, -net, EntryKind.SMS, reference)
                    )
                if vat:
                    repositories.ledger.append(
                        new_posting(line.line_id, -vat, EntryKind.VAT, reference)
                    )
        repositories.prepaid.add_sms_charge(
            message_id=message_id, line_id=line_id, outcome=outcome.value, charged_kobo=price
        )
    log_event(log, logging.INFO, "sms.charged", line_id=line_id, outcome=outcome.value, kobo=price)
    return outcome, price


def _logged(decision: CallDecision, line_id: int | None) -> CallDecision:
    log_event(
        log,
        logging.INFO,
        "calls.authorized",
        line_id=line_id,
        allowed=decision.allowed,
        max_seconds=decision.max_seconds,
        reason=decision.reason.value,
    )
    return decision
