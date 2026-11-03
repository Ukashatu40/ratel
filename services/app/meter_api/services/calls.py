"""Ingest and query call records from the meter agent's call mode (docs/call-record-agreement.md).

Call records are personal data: nothing here logs a number, a Call-ID or a time.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from common.logging import log_event
from common.timeutil import from_epoch

from ..domain import NUMBER_PATTERN, CallRecord
from ..repositories.ports import CallRepository

log = logging.getLogger("ratel.meter.calls")

MAX_BATCH = 5000
MAX_TIMESTAMP_EPOCH = 253402300799


class CallIngestService:
    def __init__(self, repository: CallRepository) -> None:
        self._repo = repository

    def ingest_batch(self, records: Sequence[CallRecord]) -> int:
        if not records:
            return 0
        if len(records) > MAX_BATCH:
            raise ValueError(f"Batch size exceeds {MAX_BATCH} records")
        for record in records:  # any invalid record rejects the whole batch
            record.validate()
        tidy = [record.normalised() for record in records]
        changed = sum(1 for before, after in zip(records, tidy, strict=True) if before is not after)
        count = self._repo.upsert_calls(tidy)
        log_event(
            log, logging.INFO, "meter.calls_ingested", record_count=count, times_adjusted=changed
        )
        return count


class CallQueryService:
    def __init__(self, repository: CallRepository) -> None:
        self._repo = repository

    def get_calls(
        self,
        from_epoch_sec: int,
        to_epoch_sec: int,
        msisdn: str | None = None,
        limit: int = MAX_BATCH,
        cursor: str | None = None,
    ) -> tuple[list[CallRecord], str | None]:
        if from_epoch_sec > to_epoch_sec:
            return [], None
        if msisdn is not None and not NUMBER_PATTERN.match(msisdn):
            raise ValueError("Invalid msisdn")
        if limit < 1 or limit > MAX_BATCH:
            raise ValueError(f"Limit must be between 1 and {MAX_BATCH}")
        records, next_cursor = self._repo.query_calls(
            from_time=from_epoch(min(from_epoch_sec, MAX_TIMESTAMP_EPOCH)),
            to_time=from_epoch(min(to_epoch_sec, MAX_TIMESTAMP_EPOCH)),
            msisdn=msisdn,
            limit=limit,
            cursor=cursor,
        )
        log_event(
            log,
            logging.INFO,
            "meter.calls_queried",
            result_count=len(records),
            has_more=next_cursor is not None,
        )
        return records, next_cursor
