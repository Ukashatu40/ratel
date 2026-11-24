"""Charging voice calls to airtime, after they end (docs/catalogue.md).

Run by the rating job (rating_cli) every few minutes. Each call record is handled once, in its own
transaction: the `call_charge` row, the call's ledger entry and its VAT entry go together or not at
all, and the row's key (the call record) makes a second charge impossible.

- Only the caller pays, and only when the caller is a live Ratelplus line.
- Answered time only, per second, at the on-net rate when the other party is a Ratelplus line and
  the off-net rate otherwise (the rates an admin set in RatelDesk).
- The wallet never goes below zero: a wallet that cannot cover a call pays what it has and the rest
  is recorded as uncovered. Calls are not cut off at zero yet (needs online charging in the IMS).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.bss_money.domain.entries import EntryKind, new_posting
from app.bss_money.domain.purchase import split_vat
from app.bss_money.domain.voice import answered_seconds, call_cost, national_msisdn
from app.bss_money.repositories.ports import CallChargeScope, CallToCharge
from app.bss_money.services.catalogue import settings_or_default
from common.logging import log_event

log = logging.getLogger("ratel.bss.money.calls")


@dataclass(frozen=True)
class CallChargeRun:
    handled: int
    charged: int  # calls that took money
    kobo: int  # money taken, VAT included
    uncovered_kobo: int
    failed: int


def charge_calls(
    scope: CallChargeScope, *, vat_rate_bps: int, batch_size: int = 500
) -> CallChargeRun:
    with scope() as repositories:
        calls = repositories.calls.uncharged_calls(batch_size)
    handled = charged = kobo = uncovered = failed = 0
    for call in calls:
        try:
            taken, short = _charge_one(scope, call, vat_rate_bps)
        except Exception as exc:  # one bad record must not stop the others; the next run retries it
            failed += 1
            log_event(
                log,
                logging.ERROR,
                "calls.charge_failed",
                record_id=call.record_id,
                error=type(exc).__name__,
            )
            continue
        handled += 1
        charged += taken > 0
        kobo += taken
        uncovered += short
    run = CallChargeRun(handled, charged, kobo, uncovered, failed)
    log_event(
        log,
        logging.INFO,
        "calls.charge_run",
        handled=handled,
        charged=charged,
        kobo=kobo,
        uncovered_kobo=uncovered,
        failed=failed,
    )
    return run


def _charge_one(scope: CallChargeScope, call: CallToCharge, vat_rate_bps: int) -> tuple[int, int]:
    """(kobo taken, kobo uncovered) for one call, written in one transaction."""
    with scope() as repositories:
        settings = settings_or_default(repositories.catalogue)
        caller = national_msisdn(call.from_msisdn)
        line_id = repositories.calls.lock_line_for_msisdn(caller) if caller else None
        callee = national_msisdn(call.to_msisdn)
        on_net = callee is not None and repositories.calls.is_ratel_number(callee)
        rate = settings.voice_onnet_kobo_per_min if on_net else settings.voice_offnet_kobo_per_min
        cost = call_cost(answered_seconds(call.answered_at, call.ended_at), rate, on_net=on_net)
        taken = 0
        if line_id is not None and cost.cost_kobo > 0:
            balance = repositories.ledger.balance(line_id) or 0
            taken = min(cost.cost_kobo, max(balance, 0))
            if taken > 0:
                net, vat = split_vat(taken, vat_rate_bps)
                reference = f"call:{call.record_id}"
                if net:
                    repositories.ledger.append(
                        new_posting(line_id, -net, EntryKind.CALL, reference)
                    )
                if vat:
                    repositories.ledger.append(new_posting(line_id, -vat, EntryKind.VAT, reference))
        short = cost.cost_kobo - taken if line_id is not None else 0
        repositories.calls.save_charge(
            record_id=call.record_id,
            line_id=line_id,
            seconds=cost.seconds,
            on_net=on_net,
            rate_kobo_per_min=rate,
            charged_kobo=taken,
            uncovered_kobo=short,
        )
    return taken, short
