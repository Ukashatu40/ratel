"""Repository interface for storing and querying usage records.

Services depend only on this protocol, not on SQLAlchemy or PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from ..domain import CallRecord, UsageRecord


class UsageRepository(Protocol):
    def upsert_records(self, records: Sequence[UsageRecord]) -> int:
        """Upsert a batch of usage records.

        Keyed on (imsi, period_start). If a record for the same key already exists,
        its period_end, bytes_up, bytes_down, and updated_at are updated.
        If the batch holds the same key twice, the later record wins.
        Returns the number of rows written (one per distinct key).
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

    def totals_by_imsi(self, from_time: datetime, to_time: datetime) -> dict[str, int]:
        """Bytes (up plus down) per IMSI for the records with `from_time <= period_start < to_time`.

        An IMSI with no record in the window is absent. Used to compare with the network's own
        counters (reconciliation, M-28).
        """
        ...


class CallRepository(Protocol):
    def upsert_calls(self, records: Sequence[CallRecord]) -> int:
        """Upsert a batch of call records, keyed on `call_id`.

        A call already stored is overwritten (the agent may post a call again once it has more to
        say, for example its end). If the batch holds the same `call_id` twice, the later wins.
        Returns the number of rows written (one per distinct `call_id`).
        """
        ...

    def query_calls(
        self,
        from_time: datetime,
        to_time: datetime,
        msisdn: str | None = None,
        limit: int = 5000,
        cursor: str | None = None,
    ) -> tuple[list[CallRecord], str | None]:
        """Calls with `from_time <= started_at <= to_time`, oldest first, at most `limit`.

        With `msisdn`, only calls that number made or received.
        """
        ...
