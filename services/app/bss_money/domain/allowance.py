"""An allowance bucket as the rules see it: data a line may still use, until it expires.

A plain value, not the database row. The table is `models.allowance.AllowanceBucket`; the
repository turns one into the other. Data left in an expired bucket is lost: there is no rollover
in the first release (Build Plan, RatelBSS: money).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.bss_money.domain.plans import Bundle, Plan


class SourceKind(StrEnum):
    PLAN = "plan"
    BUNDLE = "bundle"


@dataclass(frozen=True)
class Bucket:
    bucket_id: int
    source_kind: SourceKind
    source_id: int
    data_bytes_total: int
    data_bytes_used: int
    valid_from: datetime
    valid_to: datetime

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "source_kind", SourceKind(self.source_kind))
        except ValueError:
            raise ValueError("source_kind must be 'plan' or 'bundle'") from None
        if self.data_bytes_total < 0 or self.data_bytes_used < 0:
            raise ValueError("bytes cannot be negative")
        if self.data_bytes_used > self.data_bytes_total:
            raise ValueError("a bucket cannot have used more than it held")
        for value in (self.valid_from, self.valid_to):
            if value.tzinfo is None:
                raise ValueError("bucket times must be timezone-aware (UTC)")
        if self.valid_to <= self.valid_from:
            raise ValueError("a bucket must expire after it starts")

    @property
    def remaining_bytes(self) -> int:
        return self.data_bytes_total - self.data_bytes_used

    def is_valid_at(self, moment: datetime) -> bool:
        """Valid from its start up to, but not including, its expiry."""
        return self.valid_from <= moment < self.valid_to


def bucket_for(offer: Plan | Bundle, bucket_id: int, starts_at: datetime) -> Bucket:
    """The bucket a purchase creates: the offer's data, from `starts_at` for its validity days."""
    if starts_at.tzinfo is None:
        raise ValueError("starts_at must be timezone-aware (UTC)")
    if isinstance(offer, Plan):
        kind, source_id = SourceKind.PLAN, offer.plan_id
    else:
        kind, source_id = SourceKind.BUNDLE, offer.bundle_id
    return Bucket(
        bucket_id=bucket_id,
        source_kind=kind,
        source_id=source_id,
        data_bytes_total=offer.data_bytes,
        data_bytes_used=0,
        valid_from=starts_at,
        valid_to=starts_at + timedelta(days=offer.validity_days),
    )
