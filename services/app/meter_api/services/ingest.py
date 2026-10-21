"""Service for ingesting 300-second data usage records from the meter agent."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from common.logging import log_event

from ..domain import UsageRecord
from ..repositories.ports import UsageRepository

log = logging.getLogger("ratel.meter.ingest")


class IngestService:
    def __init__(self, repository: UsageRepository) -> None:
        self._repo = repository

    def ingest_batch(self, records: Sequence[UsageRecord]) -> int:
        if not records:
            return 0
        if len(records) > 5000:
            raise ValueError("Batch size exceeds 5000 records")

        # Validate each record before saving. Any failure rejects the whole batch.
        for rec in records:
            rec.validate()

        count = self._repo.upsert_records(records)
        # Log event with record count only. Never log IMSI or customer identity.
        log_event(log, logging.INFO, "meter.usage_ingested", record_count=count)
        return count
