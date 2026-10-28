"""What RatelDesk's lists and a line's history show (M-26). Read-only: nothing here changes data."""

from __future__ import annotations

from dataclasses import dataclass

from app.bss_lines.domain.state_machine import LineState
from app.bss_lines.repositories.desk_ports import (
    CustomerRow,
    DeskReadRepository,
    HistoryRow,
    LineRow,
)

KYC_STATUSES = ("pending", "verified", "rejected")


@dataclass(frozen=True)
class CustomerPage:
    customers: list[CustomerRow]
    total: int
    counts: dict[str, int]


@dataclass(frozen=True)
class LinePage:
    lines: list[LineRow]
    total: int
    counts: dict[str, int]


@dataclass(frozen=True)
class HistoryPage:
    entries: list[HistoryRow]
    total: int


def offset_of(page: int, page_size: int) -> int:
    """Rows to skip for a 1-based `page`."""
    return (page - 1) * page_size


def with_all(found: dict[str, int], names: list[str]) -> dict[str, int]:
    """One number per name (zero when none), plus `all`: the tabs a list screen shows."""
    counts = {name: found.get(name, 0) for name in names}
    return {"all": sum(found.values()), **counts}


def list_customers(
    repo: DeskReadRepository, *, q: str, kyc_status: str | None, page: int, page_size: int
) -> CustomerPage:
    rows, total, found = repo.list_customers(
        q=q.strip(), kyc_status=kyc_status, offset=offset_of(page, page_size), limit=page_size
    )
    return CustomerPage(rows, total, with_all(found, list(KYC_STATUSES)))


def list_lines(
    repo: DeskReadRepository, *, q: str, state: str | None, page: int, page_size: int
) -> LinePage:
    rows, total, found = repo.list_lines(
        q=q.strip(), state=state, offset=offset_of(page, page_size), limit=page_size
    )
    return LinePage(rows, total, with_all(found, [s.value for s in LineState]))


def line_history(
    repo: DeskReadRepository, line_id: int, *, page: int, page_size: int
) -> HistoryPage | None:
    """The audit trail, newest first. None if there is no such line."""
    found = repo.line_history(line_id, offset=offset_of(page, page_size), limit=page_size)
    return None if found is None else HistoryPage(*found)
