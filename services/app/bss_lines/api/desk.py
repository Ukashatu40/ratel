"""RatelDesk's operations: customers, plans, stock, and lines (M-26, contract RatelBSS).

Every route needs a signed-in staff member (`api/deps.py`), checked before anything else, and the
role must allow the action (`domain/staff.py`). Customer and KYC data never leave RatelBSS.

A refusal that must keep a record is not raised here; nothing in this module needs that, so the
transaction rolls back on any error, which is what a half-finished sale needs.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.bss_lines.api.deps import get_db, require
from app.bss_lines.domain.staff import Permission, Role
from app.bss_lines.repositories.desk_ports import (
    CustomerRecord,
    DuplicateCreate,
    LineRecord,
    PlanRecord,
    SimRecord,
    StaffRecord,
)
from app.bss_lines.repositories.desk_sql import (
    SqlCatalogRepository,
    SqlCustomerRepository,
    SqlLineSalesRepository,
    SqlReplayRepository,
)
from app.bss_lines.services import catalog, customers, line_sales
from common.errors import ApiError
from common.timeutil import to_epoch

router = APIRouter(prefix="/v1")

Db = Annotated[Session, Depends(get_db)]
IdempotencyKey = Annotated[
    str | None, Header(alias="Idempotency-Key", min_length=1, max_length=120)
]
ID = Annotated[int, Path(ge=1)]
Limit = Annotated[int, Query(ge=1, le=5000)]


class CreateCustomerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=20)
    # A shape check only (no new dependency); the address is confirmed by use, not by parsing.
    email: str = Field(min_length=3, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
    id_type: str = Field(min_length=1, max_length=20)
    id_number: str = Field(min_length=1, max_length=20, repr=False)
    address: str = Field(min_length=1, max_length=500)
    kyc_status: str = Field(pattern="^(pending|verified|rejected)$")


class CustomerOut(BaseModel):
    customer_id: int
    name: str
    phone: str
    email: str
    id_type: str
    id_number: str
    address: str
    kyc_status: str
    blocked: bool


class PlanOut(BaseModel):
    plan_id: int
    name: str
    price_kobo: int
    validity_days: int
    data_bytes: int
    speed_ul_mbps: float
    speed_dl_mbps: float
    slow_ul_mbps: float | None
    slow_dl_mbps: float | None
    channels: str
    on_exhaustion: str
    state: str


class SimOut(BaseModel):
    iccid: str
    imsi: str
    batch: str
    state: str


class CreateLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(ge=1)
    iccid: str = Field(min_length=1, max_length=20)
    msisdn: str = Field(pattern=r"^234[0-9]{10}$")
    plan_id: int = Field(ge=1)


class LineOut(BaseModel):
    line_id: int
    customer_id: int
    iccid: str
    imsi: str
    msisdn: str
    plan_id: int
    state: str
    state_before_suspension: str | None
    expires_at: int | None


def _customer_out(c: CustomerRecord) -> CustomerOut:
    return CustomerOut(**vars(c))


def _plan_out(p: PlanRecord) -> PlanOut:
    return PlanOut(**vars(p))


def _sim_out(s: SimRecord) -> SimOut:
    return SimOut(**vars(s))


def line_out(line: LineRecord) -> LineOut:
    return LineOut(
        line_id=line.line_id,
        customer_id=line.customer_id,
        iccid=line.iccid,
        imsi=line.imsi,
        msisdn=line.msisdn,
        plan_id=line.plan_id,
        state=line.state,
        state_before_suspension=line.state_before_suspension,
        expires_at=None if line.expires_at is None else to_epoch(line.expires_at),
    )


def _retry() -> ApiError:
    return ApiError(
        409, "conflict", "The same Idempotency-Key is being used by another call. Retry."
    )


def _key_reused() -> ApiError:
    return ApiError(409, "conflict", "This Idempotency-Key was used for a different request.")


@router.post("/customers", status_code=201, response_model=CustomerOut)
def create_customer(
    body: CreateCustomerRequest,
    staff: Annotated[StaffRecord, Depends(require(Permission.CREATE_CUSTOMER))],
    session: Db,
    idempotency_key: IdempotencyKey = None,
) -> CustomerOut:
    """Register a customer. A repeat with the same Idempotency-Key returns the first one."""
    try:
        created, _repeat = customers.create_customer(
            SqlCustomerRepository(session),
            SqlReplayRepository(session),
            Role(staff.role),
            customers.NewCustomer(**body.model_dump()),
            idempotency_key,
            f"staff:{staff.staff_id}",
        )
    except customers.NotAllowed:
        raise ApiError(
            403, "forbidden", "Only an admin may register a customer as verified."
        ) from None
    except customers.IdempotencyMismatch:
        raise _key_reused() from None
    except DuplicateCreate:
        raise _retry() from None
    return _customer_out(created)


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: ID,
    _staff: Annotated[StaffRecord, Depends(require(Permission.READ))],
    session: Db,
) -> CustomerOut:
    customer = customers.get_customer(SqlCustomerRepository(session), customer_id)
    if customer is None:
        raise ApiError(404, "not_found", "No such customer.")
    return _customer_out(customer)


class PlanList(BaseModel):
    plans: list[PlanOut]


class SimList(BaseModel):
    sims: list[SimOut]


class NumberOut(BaseModel):
    msisdn: str
    state: str = "available"


class NumberList(BaseModel):
    numbers: list[NumberOut]


@router.get("/plans", response_model=PlanList)
def list_plans(
    _staff: Annotated[StaffRecord, Depends(require(Permission.READ))], session: Db
) -> PlanList:
    plans = catalog.plans_on_sale(SqlCatalogRepository(session))
    return PlanList(plans=[_plan_out(p) for p in plans])


@router.get("/stock/sims", response_model=SimList)
def list_stock_sims(
    _staff: Annotated[StaffRecord, Depends(require(Permission.READ))],
    session: Db,
    limit: Limit = 100,
) -> SimList:
    sims = catalog.free_sims(SqlCatalogRepository(session), limit)
    return SimList(sims=[_sim_out(s) for s in sims])


@router.get("/stock/numbers", response_model=NumberList)
def list_stock_numbers(
    _staff: Annotated[StaffRecord, Depends(require(Permission.READ))],
    session: Db,
    limit: Limit = 100,
) -> NumberList:
    numbers = catalog.free_numbers(SqlCatalogRepository(session), limit)
    return NumberList(numbers=[NumberOut(msisdn=n) for n in numbers])


@router.post("/lines", status_code=201, response_model=LineOut)
def create_line(
    body: CreateLineRequest,
    _staff: Annotated[StaffRecord, Depends(require(Permission.CREATE_LINE))],
    session: Db,
    idempotency_key: IdempotencyKey = None,
) -> LineOut:
    """Attach a customer, a SIM, a number and a plan. A repeat returns the first line."""
    try:
        line, _repeat = line_sales.create_line(
            SqlCustomerRepository(session),
            SqlLineSalesRepository(session),
            SqlReplayRepository(session),
            line_sales.NewLine(**body.model_dump()),
            idempotency_key,
        )
    except line_sales.UnknownCustomerOrPlan:
        raise ApiError(404, "not_found", "No such customer or plan.") from None
    except line_sales.PlanNotOnSale:
        raise ApiError(409, "conflict", "That plan is no longer on sale.") from None
    except line_sales.NotAvailable:
        raise ApiError(409, "conflict", "The SIM or the number is not available.") from None
    except customers.IdempotencyMismatch:
        raise _key_reused() from None
    except DuplicateCreate:
        raise _retry() from None
    return line_out(line)


@router.get("/lines/{line_id}", response_model=LineOut)
def get_line(
    line_id: ID,
    _staff: Annotated[StaffRecord, Depends(require(Permission.READ))],
    session: Db,
) -> LineOut:
    line = line_sales.get_line(SqlLineSalesRepository(session), line_id)
    if line is None:
        raise ApiError(404, "not_found", "No such line.")
    return line_out(line)
