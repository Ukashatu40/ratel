"""The days RatelDesk's money figures are counted in.

A day runs midnight to midnight in Lagos (UTC+1, no daylight saving), because finance reads
the books by the local calendar. Everything stored and sent stays UTC; only the boundary and the
`YYYY-MM-DD` label are Lagos. TODO(finance): confirm the boundary (contracts/openapi.yaml,
`bss_wallet_summary`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

LAGOS = timezone(timedelta(hours=1), "Africa/Lagos")


@dataclass(frozen=True)
class Day:
    label: str  # YYYY-MM-DD, the Lagos date
    start: datetime  # UTC, inclusive
    end: datetime  # UTC, exclusive


def last_days(now: datetime, count: int) -> list[Day]:
    """The `count` days ending with the one `now` falls in, oldest first."""
    if now.tzinfo is None:
        raise ValueError("naive datetime rejected: time must be timezone-aware")
    today = now.astimezone(LAGOS).replace(hour=0, minute=0, second=0, microsecond=0)
    days = []
    for back in range(count - 1, -1, -1):
        start = today - timedelta(days=back)
        days.append(
            Day(
                label=start.strftime("%Y-%m-%d"),
                start=start.astimezone(UTC),
                end=(start + timedelta(days=1)).astimezone(UTC),
            )
        )
    return days
