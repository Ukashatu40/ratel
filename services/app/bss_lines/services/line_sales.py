"""Selling a SIM: attach a customer, a SIM, a number and a plan as a line (M-26).

A SIM and a number are each taken once, even by simultaneous requests: each is claimed by one
database statement that only one caller can win, and the claims and the new line are one
transaction, so a failure part-way leaves nothing taken. The line starts in `awaiting_activation`;
activating it (RatelLink, KYC check) is a separate step in `activation.py`.

A repeated create with the same Idempotency-Key returns the first line. If the request differs
from it, it is refused (`IdempotencyMismatch`).

TODO(PRD): what a `blocked` customer may buy is not decided, so it is not enforced here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.bss_lines.repositories.desk_ports import (
    CustomerRepository,
    LineRecord,
    LineSalesRepository,
    ReplayRepository,
)
from app.bss_lines.services.customers import IdempotencyMismatch

SCOPE = "line"


class UnknownCustomerOrPlan(Exception):
    """No such customer, or no such plan. Nothing was taken."""


class PlanNotOnSale(Exception):
    """The plan is retired. Nothing was taken."""


class NotAvailable(Exception):
    """The SIM or the number is not free. Nothing was taken. Carries no value."""


@dataclass(frozen=True)
class NewLine:
    customer_id: int
    iccid: str
    msisdn: str
    plan_id: int


def create_line(
    customers: CustomerRepository,
    sales: LineSalesRepository,
    replay: ReplayRepository,
    data: NewLine,
    idempotency_key: str | None,
) -> tuple[LineRecord, bool]:
    """(the line, whether this was a repeat of an earlier create)."""
    if idempotency_key is not None:
        earlier = _earlier(sales, replay, data, idempotency_key)
        if earlier is not None:
            return earlier, True
    if customers.get_customer(data.customer_id) is None:
        raise UnknownCustomerOrPlan
    plan = sales.get_plan(data.plan_id)
    if plan is None:
        raise UnknownCustomerOrPlan
    if plan.state != "on_sale":
        raise PlanNotOnSale
    sim = sales.take_sim(data.iccid)
    if sim is None or not sales.take_number(data.msisdn):
        if idempotency_key is not None:
            # A retry that raced the first call waited for it, then found the SIM taken: it is the
            # same sale, so answer with the first line instead of a refusal.
            earlier = _earlier(sales, replay, data, idempotency_key)
            if earlier is not None:
                return earlier, True
        raise NotAvailable  # the caller's transaction is rolled back, so a SIM taken is given back
    line = sales.add_line(
        customer_id=data.customer_id,
        iccid=sim.iccid,
        imsi=sim.imsi,
        msisdn=data.msisdn,
        plan_id=data.plan_id,
    )
    if idempotency_key is not None:
        replay.remember(SCOPE, idempotency_key, line.line_id)
    return line, False


def _earlier(
    sales: LineSalesRepository, replay: ReplayRepository, data: NewLine, key: str
) -> LineRecord | None:
    line_id = replay.created_by(SCOPE, key)
    if line_id is None:
        return None
    existing = sales.get_line(line_id)
    same = existing is not None and (
        (existing.customer_id, existing.iccid, existing.msisdn, existing.plan_id)
        == (data.customer_id, data.iccid, data.msisdn, data.plan_id)
    )
    if not same:
        raise IdempotencyMismatch
    return existing


def get_line(sales: LineSalesRepository, line_id: int) -> LineRecord | None:
    return sales.get_line(line_id)
