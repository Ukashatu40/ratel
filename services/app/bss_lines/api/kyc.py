"""An admin's KYC decision on a customer, and what has been done to a customer's record.

`POST /v1/customers/{customer_id}/kyc` (contract `bss_decide_kyc`) is for an admin only. Verifying
is what lets a line be activated. The reason is free text typed by staff and is stored in the
customer's history; like everything about a customer it is never logged.
`GET /v1/customers/{customer_id}/history` (`bss_get_customer_history`) reads that history.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.bss_lines.api.deps import get_db, require
from app.bss_lines.api.desk import CustomerOut
from app.bss_lines.domain.staff import Permission
from app.bss_lines.repositories.desk_ports import CustomerHistoryRow, StaffRecord
from app.bss_lines.repositories.desk_sql import SqlCustomerRepository, SqlDeskReadRepository
from app.bss_lines.services import customers, desk_reads
from common.errors import ApiError
from common.timeutil import to_epoch

router = APIRouter(prefix="/v1")

Db = Annotated[Session, Depends(get_db)]
CustomerId = Annotated[int, Path(ge=1)]


class KycDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["verified", "rejected"]
    reason: str = Field(min_length=1, max_length=200)


class CustomerHistoryEntryOut(BaseModel):
    at: int
    action: str
    actor: str
    reason: str


class CustomerHistoryOut(BaseModel):
    entries: list[CustomerHistoryEntryOut]
    total: int


def _entry(row: CustomerHistoryRow) -> CustomerHistoryEntryOut:
    return CustomerHistoryEntryOut(
        at=to_epoch(row.at), action=row.action, actor=row.actor, reason=row.reason
    )


@router.post("/customers/{customer_id}/kyc", response_model=CustomerOut)
def decide_kyc(
    customer_id: CustomerId,
    body: KycDecisionRequest,
    staff: Annotated[StaffRecord, Depends(require(Permission.VERIFY_KYC))],
    session: Db,
    # Accepted, as every changing call does; deciding what the customer already is changes nothing,
    # so a repeat is safe with or without it.
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=120)
    ] = None,
) -> CustomerOut:
    try:
        customer = customers.decide_kyc(
            SqlCustomerRepository(session),
            customer_id,
            status=body.status,
            reason=body.reason,
            actor=f"staff:{staff.staff_id}",
        )
    except customers.InvalidKycChange:
        raise ApiError(
            409, "conflict", "That customer's KYC cannot be moved there from where it is."
        ) from None
    if customer is None:
        raise ApiError(404, "not_found", "No such customer.")
    return CustomerOut(**vars(customer))


@router.get("/customers/{customer_id}/history", response_model=CustomerHistoryOut)
def get_customer_history(
    customer_id: CustomerId,
    _staff: Annotated[StaffRecord, Depends(require(Permission.READ))],
    session: Db,
    page: Annotated[int, Query(ge=1)] = 1,
    # TODO(contract): the largest page RatelDesk needs. 200 is a placeholder.
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
) -> CustomerHistoryOut:
    found = desk_reads.customer_history(
        SqlDeskReadRepository(session), customer_id, page=page, page_size=page_size
    )
    if found is None:
        raise ApiError(404, "not_found", "No such customer.")
    return CustomerHistoryOut(entries=[_entry(e) for e in found.entries], total=found.total)
