"""Service for querying data usage records with pagination."""

from __future__ import annotations

import logging

from common.logging import log_event
from common.timeutil import from_epoch

from ..domain import IMSI_PATTERN, UsageRecord
from ..repositories.ports import UsageRepository

log = logging.getLogger("ratel.meter.query")


MAX_TIMESTAMP_EPOCH = 253402300799


class QueryService:
    def __init__(self, repository: UsageRepository) -> None:
        self._repo = repository

    def get_usage(
        self,
        from_epoch_sec: int,
        to_epoch_sec: int,
        imsi: str | None = None,
        limit: int = 5000,
        cursor: str | None = None,
    ) -> tuple[list[UsageRecord], str | None]:
        if from_epoch_sec > to_epoch_sec:
            return [], None
        if imsi is not None and not IMSI_PATTERN.match(imsi):
            raise ValueError("Invalid IMSI format: must be 15 digits")
        if limit < 1 or limit > 5000:
            raise ValueError("Limit must be between 1 and 5000")

        from_time = from_epoch(min(from_epoch_sec, MAX_TIMESTAMP_EPOCH))
        to_time = from_epoch(min(to_epoch_sec, MAX_TIMESTAMP_EPOCH))

        records, next_cursor = self._repo.query_usage(
            from_time=from_time,
            to_time=to_time,
            imsi=imsi,
            limit=limit,
            cursor=cursor,
        )
        # Log event with record count only. Never log IMSI.
        log_event(
            log,
            logging.INFO,
            "meter.usage_queried",
            result_count=len(records),
            has_more=next_cursor is not None,
        )
        return records, next_cursor
