"""RatelDesk's money screens (contract `bss_get_line_wallet`, `bss_list_ledger`,
`bss_wallet_summary`, `bss_get_line_usage`, `bss_dashboard`). Read-only.

Every route needs a signed-in staff member (`bss_lines/api/deps.py`). Money is whole kobo. Nothing
here writes: the ledger is appended to by the system only, and a correction is a new entry.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel

from app.bss_lines.api.deps import now_utc, require
from app.bss_lines.api.desk_reads import LineCountsOut
from app.bss_lines.domain.staff import Permission
from app.bss_lines.repositories.desk_ports import StaffRecord
from app.bss_money.repositories.ports import DeskReadScope, LedgerRow, LineUsageRow
from app.bss_money.services import desk_reads
from app.meter_api.repositories.sql import MAX_TIMESTAMP_EPOCH
from common.errors import ApiError
from common.timeutil import from_epoch, to_epoch

router = APIRouter(prefix="/v1")

Reader = Annotated[StaffRecord, Depends(require(Permission.READ))]
LineId = Annotated[int, Path(ge=1)]
PageNumber = Annotated[int, Query(ge=1)]
# TODO(contract): the largest page RatelDesk needs. 200 is a placeholder.
PageSize = Annotated[int, Query(ge=1, le=200)]
Epoch = Annotated[int, Query(ge=0)]


class LineWalletOut(BaseModel):
    line_id: int
    balance_kobo: int
    ledger_sum_kobo: int


class LedgerEntryOut(BaseModel):
    entry_id: int
    line_id: int
    msisdn: str
    amount_kobo: int
    kind: str
    reference: str
    created_at: int


class LedgerPageOut(BaseModel):
    entries: list[LedgerEntryOut]
    total: int
    counts: dict[str, int]


class DailyMoneyOut(BaseModel):
    date: str
    in_kobo: int
    out_kobo: int


class WalletSummaryOut(BaseModel):
    total_balance_kobo: int
    wallets_with_balance: int
    entries_today: int
    daily: list[DailyMoneyOut]


class LineUsageRecordOut(BaseModel):
    period_start: int
    period_end: int
    bytes_up: int
    bytes_down: int
    rated: bool


class LineUsageListOut(BaseModel):
    records: list[LineUsageRecordOut]
    next_cursor: str | None


class AttentionItemOut(BaseModel):
    issue: str
    customer_id: int
    line_id: int | None
    customer_name: str
    msisdn: str | None
    since: int


class TopupDayOut(BaseModel):
    date: str
    amount_kobo: int


class DashboardOut(BaseModel):
    line_counts: LineCountsOut
    kyc_pending: int
    topups_today_kobo: int
    topups_yesterday_kobo: int
    topups_last_7_days: list[TopupDayOut]
    attention: list[AttentionItemOut]


def _scope(request: Request) -> DeskReadScope:
    scope: DeskReadScope = request.app.state.desk_read_scope
    return scope


def _no_such_line() -> ApiError:
    return ApiError(404, "not_found", "No such line.")


def _entry(row: LedgerRow) -> LedgerEntryOut:
    return LedgerEntryOut(
        entry_id=row.entry_id,
        line_id=row.line_id,
        msisdn=row.msisdn,
        amount_kobo=row.amount_kobo,
        kind=row.kind,
        reference=row.reference,
        created_at=to_epoch(row.created_at),
    )


def _usage(row: LineUsageRow) -> LineUsageRecordOut:
    return LineUsageRecordOut(
        period_start=to_epoch(row.period_start),
        period_end=to_epoch(row.period_end),
        bytes_up=row.bytes_up,
        bytes_down=row.bytes_down,
        rated=row.rated,
    )


@router.get("/lines/{line_id}/wallet", response_model=LineWalletOut)
def get_line_wallet(request: Request, line_id: LineId, _staff: Reader) -> LineWalletOut:
    with _scope(request)() as reads:
        if reads.money.line_imsi(line_id) is None:
            raise _no_such_line()
        balance, ledger_sum = reads.money.wallet_figures(line_id)
    return LineWalletOut(line_id=line_id, balance_kobo=balance, ledger_sum_kobo=ledger_sum)


@router.get("/lines/{line_id}/usage", response_model=LineUsageListOut)
def get_line_usage(
    request: Request,
    line_id: LineId,
    _staff: Reader,
    from_: Annotated[Epoch, Query(alias="from")],
    to: Epoch,
    cursor: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
) -> LineUsageListOut:
    with _scope(request)() as reads:
        imsi = reads.money.line_imsi(line_id)
        if imsi is None:
            raise _no_such_line()
        try:
            page = desk_reads.line_usage(
                reads.money,
                imsi,
                start=from_epoch(min(from_, MAX_TIMESTAMP_EPOCH)),
                end=from_epoch(min(to, MAX_TIMESTAMP_EPOCH)),
                cursor=cursor,
            )
        except desk_reads.BadCursor:
            raise ApiError(422, "validation_error", "Invalid request. Fields: cursor") from None
    return LineUsageListOut(records=[_usage(r) for r in page.records], next_cursor=page.next_cursor)


@router.get("/ledger", response_model=LedgerPageOut)
def list_ledger(
    request: Request,
    _staff: Reader,
    kind: Annotated[str | None, Query(min_length=1, max_length=30)] = None,
    line_id: Annotated[int | None, Query(ge=1)] = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> LedgerPageOut:
    with _scope(request)() as reads:
        found = desk_reads.ledger(
            reads.money, line_id=line_id, kind=kind, page=page, page_size=page_size
        )
    return LedgerPageOut(
        entries=[_entry(e) for e in found.entries], total=found.total, counts=found.counts
    )


@router.get("/wallet/summary", response_model=WalletSummaryOut)
def get_wallet_summary(request: Request, _staff: Reader) -> WalletSummaryOut:
    with _scope(request)() as reads:
        found = desk_reads.wallet_summary(reads.money, now_utc(request))
    return WalletSummaryOut(
        total_balance_kobo=found.total_balance_kobo,
        wallets_with_balance=found.wallets_with_balance,
        entries_today=found.entries_today,
        daily=[DailyMoneyOut(**vars(d)) for d in found.daily],
    )


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(request: Request, _staff: Reader) -> DashboardOut:
    with _scope(request)() as reads:
        found = desk_reads.dashboard(reads.lines, reads.money, now_utc(request))
    return DashboardOut(
        line_counts=LineCountsOut(**found.line_counts),
        kyc_pending=found.kyc_pending,
        topups_today_kobo=found.topups_today_kobo,
        topups_yesterday_kobo=found.topups_yesterday_kobo,
        topups_last_7_days=[TopupDayOut(**vars(d)) for d in found.topups_last_7_days],
        attention=[
            AttentionItemOut(
                issue=a.issue,
                customer_id=a.customer_id,
                line_id=a.line_id,
                customer_name=a.customer_name,
                msisdn=a.msisdn,
                since=to_epoch(a.since),
            )
            for a in found.attention
        ],
    )
