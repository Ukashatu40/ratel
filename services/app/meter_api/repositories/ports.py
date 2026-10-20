"""Repository interface for storing and querying usage records.

Services depend only on this protocol, not on SQLAlchemy or PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from ..domain import UsageRecord


class UsageRepository(Protocol):
    def upsert_records(self, records: Sequence[UsageRecord]) -> int:
        """Upsert a batch of usage records.

        Keyed on (imsi, period_start). If a record for the same key already exists,
        its period_end, bytes_up, bytes_down, and updated_at are updated.
        Returns the number of records upserted.
        """
        ...

    def query_usage(
        self,
        from_time: datetime,
        to_time: datetime,
        imsi: str | None = None,
        limit: int = 5000,
        cursor: str | None = None,
    ) -> tuple[list[UsageRecord], str | None]:
        """Query usage records within [from_time, to_time].

        Returns a page of at most `limit` records and an optional `next_cursor`.
        If no more records exist, `next_cursor` is None.
        """
        ...
