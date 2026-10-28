"""RatelDesk's lists and a line's history (contract `bss_list_customers`, `bss_list_lines`,
`bss_get_line_history`). Read-only; every route needs a signed-in staff member (`api/deps.py`).

Lists are paged with `page` and `page_size`, newest first. A customer row has no NIN and no
address: a list is read in bulk.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.bss_lines.api.deps import get_db, require
from app.bss_lines.domain.staff import Permission
from app.bss_lines.repositories.desk_ports import CustomerRow, HistoryRow, LineRow, StaffRecord
from app.bss_lines.repositories.desk_sql import SqlDeskReadRepository
from app.bss_lines.services import desk_reads
from common.errors import ApiError
from common.timeutil import to_epoch

router = APIRouter(prefix="/v1")

Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[StaffRecord, Depends(require(Permission.READ))]
SearchText = Annotated[str, Query(max_length=100)]
PageNumber = Annotated[int, Query(ge=1)]
# TODO(contract): the largest page RatelDesk needs. 200 is a placeholder.
PageSize = Annotated[int, Query(ge=1, le=200)]
LineStateName = Literal[
    "awaiting_activation", "active", "out_of_data", "expired", "suspended", "terminated"
]


class CustomerRowOut(BaseModel):
    customer_id: int
    name: str
    phone: str
    email: str
    kyc_status: str
    blocked: bool
    lines_count: int


class CustomerCounts(BaseModel):
    all: int
    pending: int
    verified: int
    rejected: int


class CustomerListOut(BaseModel):
    customers: list[CustomerRowOut]
    total: int
    counts: CustomerCounts


class LineRowOut(BaseModel):
    line_id: int
    customer_id: int
    customer_name: str
    iccid: str
    imsi: str
    msisdn: str
    plan_id: int
    plan_name: str
    state: str
    expires_at: int | None


class LineCountsOut(BaseModel):
    all: int
    awaiting_activation: int
    active: int
    out_of_data: int
    expired: int
    suspended: int
    terminated: int


class LineListOut(BaseModel):
    lines: list[LineRowOut]
    total: int
    counts: LineCountsOut


class HistoryEntryOut(BaseModel):
    at: int
    from_state: str
    to_state: str
    actor: str
    reason: str


class LineHistoryOut(BaseModel):
    entries: list[HistoryEntryOut]
    total: int


def _customer(c: CustomerRow) -> CustomerRowOut:
    return CustomerRowOut(**vars(c))


def _line(row: LineRow) -> LineRowOut:
    return LineRowOut(
        **{**vars(row), "expires_at": None if row.expires_at is None else to_epoch(row.expires_at)}
    )


def _entry(row: HistoryRow) -> HistoryEntryOut:
    return HistoryEntryOut(
        at=to_epoch(row.at),
        from_state=row.from_state,
        to_state=row.to_state,
        actor=row.actor,
        reason=row.reason,
    )


@router.get("/customers", response_model=CustomerListOut)
def list_customers(
    _staff: Reader,
    session: Db,
    q: SearchText = "",
    kyc_status: Literal["pending", "verified", "rejected"] | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> CustomerListOut:
    found = desk_reads.list_customers(
        SqlDeskReadRepository(session), q=q, kyc_status=kyc_status, page=page, page_size=page_size
    )
    return CustomerListOut(
        customers=[_customer(c) for c in found.customers],
        total=found.total,
        counts=CustomerCounts(**found.counts),
    )


@router.get("/lines", response_model=LineListOut)
def list_lines(
    _staff: Reader,
    session: Db,
    q: SearchText = "",
    state: LineStateName | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> LineListOut:
    found = desk_reads.list_lines(
        SqlDeskReadRepository(session), q=q, state=state, page=page, page_size=page_size
    )
    return LineListOut(
        lines=[_line(r) for r in found.lines],
        total=found.total,
        counts=LineCountsOut(**found.counts),
    )


@router.get("/lines/{line_id}/history", response_model=LineHistoryOut)
def get_line_history(
    line_id: Annotated[int, Path(ge=1)],
    _staff: Reader,
    session: Db,
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> LineHistoryOut:
    found = desk_reads.line_history(
        SqlDeskReadRepository(session), line_id, page=page, page_size=page_size
    )
    if found is None:
        raise ApiError(404, "not_found", "No such line.")
    return LineHistoryOut(entries=[_entry(e) for e in found.entries], total=found.total)
