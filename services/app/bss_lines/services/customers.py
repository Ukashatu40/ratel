"""Registering a customer, and reading one back (M-26).

A customer holds personal data (a name, an email, a NIN). It is never logged, and never sent to
RatelLink or RatelMeter.

Who may verify identity: only an admin may create a customer whose KYC is already `verified`;
customer care creates them `pending` (or `rejected`) and an admin decides. TODO(PRD): the KYC
rules are compliance's, and a separate "verify" step may replace this.

A repeated create with the same Idempotency-Key returns the first customer. If the request differs
from that customer in any field, it is refused (`IdempotencyMismatch`): a key names one create.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.bss_lines.domain.staff import Permission, Role, may
from app.bss_lines.repositories.desk_ports import (
    CustomerRecord,
    CustomerRepository,
    DuplicateCreate,
    ReplayRepository,
)

SCOPE = "customer"


class NotAllowed(Exception):
    """The staff member's role does not allow this."""


class IdempotencyMismatch(Exception):
    """The Idempotency-Key was used for a different request."""


@dataclass(frozen=True)
class NewCustomer:
    name: str
    phone: str
    email: str
    id_type: str
    id_number: str
    address: str
    kyc_status: str


def create_customer(
    customers: CustomerRepository,
    replay: ReplayRepository,
    role: Role,
    data: NewCustomer,
    idempotency_key: str | None,
) -> tuple[CustomerRecord, bool]:
    """(the customer, whether this was a repeat of an earlier create)."""
    if data.kyc_status == "verified" and not may(role, Permission.VERIFY_KYC):
        raise NotAllowed
    if idempotency_key is not None:
        earlier = _earlier(customers, replay, data, idempotency_key)
        if earlier is not None:
            return earlier, True
    created = customers.add_customer(**vars(data))
    if idempotency_key is not None:
        try:
            replay.remember(SCOPE, idempotency_key, created.customer_id)
        except DuplicateCreate:
            # The same key raced us and won: its customer is the one. (This one is rolled back by
            # the caller's transaction, because the error is raised.)
            raise
    return created, False


def _earlier(
    customers: CustomerRepository, replay: ReplayRepository, data: NewCustomer, key: str
) -> CustomerRecord | None:
    customer_id = replay.created_by(SCOPE, key)
    if customer_id is None:
        return None
    existing = customers.get_customer(customer_id)
    if existing is None or any(
        getattr(existing, name) != value for name, value in vars(data).items()
    ):
        raise IdempotencyMismatch
    return existing


def get_customer(customers: CustomerRepository, customer_id: int) -> CustomerRecord | None:
    return customers.get_customer(customer_id)
