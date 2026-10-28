"""What RatelDesk's money screens show: a line's wallet, the ledger, usage, totals, the front page.

Read-only. The ledger is append-only and nothing here changes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.bss_lines.domain.state_machine import LineState
from app.bss_lines.repositories.desk_ports import AttentionRow, DeskReadRepository
from app.bss_lines.services.desk_reads import KYC_STATUSES, offset_of, with_all  # noqa: F401
from app.bss_money.domain.days import last_days
from app.bss_money.repositories.ports import (
    LedgerRow,
    LineUsageRow,
    MoneyReadRepository,
)

ATTENTION_LIMIT = 20
USAGE_PAGE = 500


@dataclass(frozen=True)
class LedgerPage:
    entries: list[LedgerRow]
    total: int
    counts: dict[str, int]


@dataclass(frozen=True)
class DayMoney:
    date: str
    in_kobo: int
    out_kobo: int


@dataclass(frozen=True)
class WalletSummary:
    total_balance_kobo: int
    wallets_with_balance: int
    entries_today: int
    daily: list[DayMoney]


@dataclass(frozen=True)
class DayTopups:
    date: str
    amount_kobo: int


@dataclass(frozen=True)
class Dashboard:
    line_counts: dict[str, int]
    kyc_pending: int
    topups_today_kobo: int
    topups_yesterday_kobo: int
    topups_last_7_days: list[DayTopups]
    attention: list[AttentionRow]


@dataclass(frozen=True)
class UsagePage:
    records: list[LineUsageRow]
    next_cursor: str | None


class BadCursor(ValueError):
    """The cursor is not one this service gave out."""


def ledger(
    money: MoneyReadRepository, *, line_id: int | None, kind: str | None, page: int, page_size: int
) -> LedgerPage:
    rows, total = money.ledger_page(
        line_id=line_id, kind=kind, offset=offset_of(page, page_size), limit=page_size
    )
    found = money.ledger_kind_counts(line_id)
    return LedgerPage(rows, total, {"all": sum(found.values()), **found})


def wallet_summary(money: MoneyReadRepository, now: datetime) -> WalletSummary:
    days = last_days(now, 7)
    daily = []
    for day in days:
        moved = money.moved_between(day.start, day.end)
        daily.append(DayMoney(day.label, moved.in_kobo, moved.out_kobo))
    total, holding = money.wallet_totals()
    today = money.moved_between(days[-1].start, days[-1].end)
    return WalletSummary(total, holding, today.entries, daily)


def dashboard(lines: DeskReadRepository, money: MoneyReadRepository, now: datetime) -> Dashboard:
    days = last_days(now, 7)
    topups = [DayTopups(d.label, money.topped_up_between(d.start, d.end)) for d in days]
    waiting = lines.attention(ATTENTION_LIMIT)
    waiting.sort(key=lambda item: item.since)
    return Dashboard(
        line_counts=with_all(lines.line_state_counts(), [s.value for s in LineState]),
        kyc_pending=lines.kyc_pending_count(),
        topups_today_kobo=topups[-1].amount_kobo,
        topups_yesterday_kobo=topups[-2].amount_kobo,
        topups_last_7_days=topups,
        attention=waiting[:ATTENTION_LIMIT],
    )


def _decode(cursor: str) -> datetime:
    try:
        return datetime.fromtimestamp(int(cursor), tz=UTC)
    except (ValueError, OverflowError, OSError):
        raise BadCursor from None


def line_usage(
    money: MoneyReadRepository,
    imsi: str,
    *,
    start: datetime,
    end: datetime,
    cursor: str | None,
) -> UsagePage:
    """A line's usage records, newest first. The cursor is the last `period_start` given out."""
    before = None if cursor is None else _decode(cursor)
    rows = money.line_usage(imsi, start=start, end=end, before=before, limit=USAGE_PAGE + 1)
    more = len(rows) > USAGE_PAGE
    page = rows[:USAGE_PAGE]
    next_cursor = str(int(page[-1].period_start.timestamp())) if more else None
    return UsagePage(page, next_cursor)
