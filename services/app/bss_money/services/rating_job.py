"""The rating job (M-17): deduct usage from each line's allowance, then act on what is left.

Run every five minutes by a timer on bss-app (`python -m app.bss_money.rating_cli`).

1. Rate. For every line with usage records nobody has rated, in one transaction per line: take the
   line, load its oldest unrated records and its buckets, deduct soonest-expiry-first (the pure
   `rate()`), store the new bucket totals and mark every record rated. All or nothing, so a crash
   rates nothing twice and loses nothing: the records are still unrated and the next run takes them.
   One line failing is logged and counted and does not stop the others.
2. Settle (only when a payment gateway is configured). Payments still pending with the gateway are
   asked about and, if they went through, credited once, so the system works without a webhook.
3. Renew (only when the deployment turns it on). A line that is out of data or expired, whose
   wallet covers its plan, has the plan bought again (`renew`), so a top-up brings data back by
   itself.
4. Act. For every active, out-of-data or expired line that holds an allowance, judge it
   (`action_for()`): used up -> `out_of_data`, validity ended -> `expired`, allowance back (a
   purchase made the bucket) -> `active` again, all through the state machine. This pass does not
   depend on step 1 having had records, so a change that failed last time (RatelLink was down) is
   tried again now. A line already moved is judged NONE, so it is moved once.

Calls are not rated for the demo. Nothing here logs an IMSI or a byte count per line.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.bss_money.domain.exhaustion import ServiceAction, action_for
from app.bss_money.domain.rating import rate
from app.bss_money.repositories.ports import RatingRepository
from common.logging import log_event

log = logging.getLogger("ratel.bss.money.rating")

# At most this many records per line per run; a bigger backlog is taken over the next runs.
BATCH_SIZE = 5000

Settle = Callable[[], int]
"""Settles payments still pending with the gateway; returns how many it credited."""

Renew = Callable[[int], bool]
"""Buys the line's plan again if its wallet covers it; True if it did (services/purchase.py)."""

Scope = Callable[[], AbstractContextManager[RatingRepository]]
"""Opens one transaction and yields the repository inside it: commit on exit, rollback on error."""


class LineControl(Protocol):
    """The two changes the job makes to a line, through the state machine (BSS: lines)."""

    def mark_out_of_data(self, line_id: int, idempotency_key: str) -> None: ...

    def expire(self, line_id: int, idempotency_key: str) -> None: ...

    def restore(self, line_id: int, idempotency_key: str) -> None: ...


@dataclass(frozen=True)
class RatingRun:
    lines_rated: int = 0
    records_rated: int = 0
    bytes_deducted: int = 0
    bytes_uncovered: int = 0
    lines_out_of_data: int = 0
    lines_expired: int = 0
    payments_credited: int = 0
    lines_restored: int = 0
    lines_renewed: int = 0
    failures: int = 0


def run_rating(
    scope: Scope,
    control: LineControl,
    *,
    now: datetime,
    batch_size: int = BATCH_SIZE,
    settle: Settle | None = None,
    renew: Renew | None = None,
) -> RatingRun:
    """One pass of the job at `now`. Never raises for one line's failure; see `failures`."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (UTC)")
    run = _RunCounts()
    with scope() as repository:
        to_rate = repository.lines_with_unrated_usage()
    for line_id in to_rate:
        try:
            _rate_line(scope, line_id, now, batch_size, run)
        except Exception as exc:
            run.failures += 1
            log_event(
                log,
                logging.ERROR,
                "rating.line_failed",
                line_id=line_id,
                exc_type=type(exc).__name__,
            )
    if settle is not None:
        # Payments that went through but whose notification never came are credited here, so a
        # top-up reaches the wallet before the line is judged below.
        try:
            run.payments_credited += settle()
        except Exception as exc:
            run.failures += 1
            log_event(log, logging.ERROR, "rating.settle_failed", exc_type=type(exc).__name__)
    if renew is not None:
        with scope() as repository:
            to_renew = repository.lines_with_allowance()
        for line_id in to_renew:
            try:
                if renew(line_id):
                    run.lines_renewed += 1
            except Exception as exc:
                run.failures += 1
                log_event(
                    log,
                    logging.ERROR,
                    "rating.line_renew_failed",
                    line_id=line_id,
                    exc_type=type(exc).__name__,
                )
    with scope() as repository:
        to_judge = repository.lines_with_allowance()
    for line_id in to_judge:
        try:
            _judge_line(scope, control, line_id, now, run)
        except Exception as exc:
            run.failures += 1
            log_event(
                log,
                logging.ERROR,
                "rating.line_change_failed",
                line_id=line_id,
                exc_type=type(exc).__name__,
            )
    result = run.freeze()
    log_event(
        log,
        logging.INFO,
        "rating.run",
        lines_rated=result.lines_rated,
        records_rated=result.records_rated,
        bytes_uncovered=result.bytes_uncovered,
        lines_out_of_data=result.lines_out_of_data,
        lines_expired=result.lines_expired,
        payments_credited=result.payments_credited,
        lines_restored=result.lines_restored,
        lines_renewed=result.lines_renewed,
        failures=result.failures,
    )
    return result


@dataclass
class _RunCounts:
    lines_rated: int = 0
    records_rated: int = 0
    bytes_deducted: int = 0
    bytes_uncovered: int = 0
    lines_out_of_data: int = 0
    lines_expired: int = 0
    payments_credited: int = 0
    lines_restored: int = 0
    lines_renewed: int = 0
    failures: int = 0

    def freeze(self) -> RatingRun:
        return RatingRun(**vars(self))


def _rate_line(scope: Scope, line_id: int, now: datetime, batch_size: int, run: _RunCounts) -> None:
    with scope() as repository:
        line = repository.lock_line(line_id)
        if line is None:
            return
        records = repository.unrated_records(line, batch_size)
        if not records:  # another run took them while this one waited for the line
            return
        result = rate(records, repository.buckets(line_id), line.plan, now)
        repository.save_rating(line_id, result)
    run.lines_rated += 1
    run.records_rated += len(result.ratings)
    run.bytes_deducted += sum(r.deducted_bytes for r in result.ratings)
    run.bytes_uncovered += result.uncovered_bytes


def _judge_line(
    scope: Scope, control: LineControl, line_id: int, now: datetime, run: _RunCounts
) -> None:
    with scope() as repository:
        line = repository.lock_line(line_id)
        if line is None:
            return
        action = action_for(line.state, repository.buckets(line_id), now)
    # The transaction ends before RatelLink is called: no line stays locked across a network call.
    stamp = int(now.timestamp())
    if action is ServiceAction.OUT_OF_DATA:
        control.mark_out_of_data(line_id, f"rating-out-of-data-{line_id}-{stamp}")
        run.lines_out_of_data += 1
    elif action is ServiceAction.EXPIRE:
        control.expire(line_id, f"rating-expire-{line_id}-{stamp}")
        run.lines_expired += 1
    elif action is ServiceAction.RESTORE:
        control.restore(line_id, f"rating-restore-{line_id}-{stamp}")
        run.lines_restored += 1
