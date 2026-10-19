"""Rating: turn a line's usage records and its allowance into what is left and what to do.

Pure: no database, no clock (the moment to judge at is passed in), no logging. Money is not
involved, only bytes. Calls are not rated for the demo.

The rules (Build Plan, RatelBSS: money):
- Usage is deducted from the line's buckets, **soonest expiry first**. A record spills into the
  next bucket when the first runs out.
- A record is charged to the buckets that are valid at the record's `period_start`.
- Data left in an expired bucket is lost; it does not count as remaining.
- When nothing remains, the plan's `on_exhaustion` decides: slow the line or cut its data.
- The result does not depend on the order the records or buckets arrive in, and rating the same
  input twice gives the same result. A record id seen twice counts once.

TODO(PRD): whether a line that never had any allowance counts as out of data. Here it does:
nothing remaining means exhausted. The job that decides when to call this is M-17.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.bss_money.domain.allowance import Bucket
from app.bss_money.domain.plans import OnExhaustion, Plan


class DataDecision(StrEnum):
    STAY = "stay"  # allowance left: the line keeps full speed
    SLOW = "slow"  # exhausted and the plan slows: use the plan's slow speeds
    CUT = "cut"  # exhausted and the plan stops: data off


@dataclass(frozen=True)
class UsageRecord:
    """One interval of a line's usage, as the RatelMeter API stores it."""

    record_id: str
    period_start: datetime
    bytes_up: int
    bytes_down: int

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("a usage record needs an id")
        if self.period_start.tzinfo is None:
            raise ValueError("period_start must be timezone-aware (UTC)")
        if self.bytes_up < 0 or self.bytes_down < 0:
            raise ValueError("bytes cannot be negative")

    @property
    def total_bytes(self) -> int:
        return self.bytes_up + self.bytes_down


@dataclass(frozen=True)
class RecordRating:
    record_id: str
    deducted_bytes: int  # taken from allowance
    uncovered_bytes: int  # used with no allowance left to cover it


@dataclass(frozen=True)
class RatingResult:
    buckets: tuple[Bucket, ...]  # updated, in the order they are used (soonest expiry first)
    ratings: tuple[RecordRating, ...]  # in processing order (by period_start, then id)
    remaining_bytes: int  # usable at the moment judged
    exhausted: bool
    decision: DataDecision
    slow_ul_mbps: float | None  # set only when the decision is SLOW
    slow_dl_mbps: float | None

    @property
    def uncovered_bytes(self) -> int:
        return sum(r.uncovered_bytes for r in self.ratings)


def rate(
    records: Iterable[UsageRecord],
    buckets: Iterable[Bucket],
    plan: Plan,
    as_of: datetime,
) -> RatingResult:
    """Deduct `records` from `buckets` and decide what the line should do at `as_of`."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware (UTC)")
    ordered_buckets = _ordered_buckets(buckets)
    used = {b.bucket_id: b.data_bytes_used for b in ordered_buckets}

    ratings: list[RecordRating] = []
    for record in _ordered_records(records):
        needed = record.total_bytes
        for bucket in ordered_buckets:
            if needed == 0:
                break
            if not bucket.is_valid_at(record.period_start):
                continue
            free = bucket.data_bytes_total - used[bucket.bucket_id]
            take = min(free, needed)
            used[bucket.bucket_id] += take
            needed -= take
        ratings.append(RecordRating(record.record_id, record.total_bytes - needed, needed))

    updated = tuple(replace(b, data_bytes_used=used[b.bucket_id]) for b in ordered_buckets)
    remaining = sum(b.remaining_bytes for b in updated if b.is_valid_at(as_of))
    decision, slow_ul, slow_dl = _decide(remaining, plan)
    return RatingResult(
        buckets=updated,
        ratings=tuple(ratings),
        remaining_bytes=remaining,
        exhausted=remaining == 0,
        decision=decision,
        slow_ul_mbps=slow_ul,
        slow_dl_mbps=slow_dl,
    )


def _decide(remaining: int, plan: Plan) -> tuple[DataDecision, float | None, float | None]:
    if remaining > 0:
        return DataDecision.STAY, None, None
    if plan.on_exhaustion is OnExhaustion.SLOW:
        return DataDecision.SLOW, plan.slow_ul_mbps, plan.slow_dl_mbps
    return DataDecision.CUT, None, None


def _ordered_buckets(buckets: Iterable[Bucket]) -> list[Bucket]:
    """Soonest expiry first. Ties break on start, then id, so the order never depends on input."""
    first_seen: dict[int, Bucket] = {}
    for bucket in sorted(buckets, key=lambda b: (b.valid_to, b.valid_from, b.bucket_id)):
        first_seen.setdefault(bucket.bucket_id, bucket)
    return list(first_seen.values())


def _ordered_records(records: Iterable[UsageRecord]) -> list[UsageRecord]:
    """Oldest first, one per id. Ties break on id, then size: the order never depends on input."""
    unique: dict[str, UsageRecord] = {}
    for record in sorted(
        records, key=lambda r: (r.period_start, r.record_id, r.bytes_up, r.bytes_down)
    ):
        unique.setdefault(record.record_id, record)
    return list(unique.values())  # inserted in time order, so already in time order
