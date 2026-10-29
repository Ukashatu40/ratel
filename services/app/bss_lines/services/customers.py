"""Registering a customer, and reading one back (M-26).

A customer holds personal data (a name, an email, a NIN). It is never logged, and never sent to
RatelLink or RatelMeter.

Who may verify identity: only an admin may create a customer whose KYC is already `verified`, or
decide a customer's KYC afterwards; customer care creates them `pending` (or `rejected`).
TODO(PRD): the KYC rules are compliance's (decision 2); the moves allowed below are the project
lead's choice for the first release.

Every registration and every decision is written to the customer's history with who and why.

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


class InvalidKycChange(Exception):
    """The customer's KYC cannot move from where it is to where it was asked to go."""


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
    actor: str,
) -> tuple[CustomerRecord, bool]:
    """(the customer, whether this was a repeat of an earlier create)."""
    if data.kyc_status == "verified" and not may(role, Permission.VERIFY_KYC):
        raise NotAllowed
    if idempotency_key is not None:
        earlier = _earlier(customers, replay, data, idempotency_key)
        if earlier is not None:
            return earlier, True
    created = customers.add_customer(**vars(data))
    customers.add_audit(
        created.customer_id,
        action="registered",
        actor=actor,
        reason=f"registered with KYC {data.kyc_status}",
    )
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


# Where a decision may take a customer. Pending is decided once; a rejected customer may be
# verified later (new documents). Taking a verified customer back to rejected would leave their
# active lines without a rule, so it is refused until compliance says what happens to them.
# TODO(PRD, decision 2): revoking a verification.
_KYC_MOVES = {("pending", "verified"), ("pending", "rejected"), ("rejected", "verified")}
KYC_ACTIONS = {"verified": "kyc_verified", "rejected": "kyc_rejected"}


def decide_kyc(
    customers: CustomerRepository, customer_id: int, *, status: str, reason: str, actor: str
) -> CustomerRecord | None:
    """Verify or reject a customer. None if there is no such customer.

    Deciding what the customer already is changes nothing and writes nothing, so a repeat is safe.
    """
    current = customers.get_customer_for_update(customer_id)
    if current is None:
        return None
    if current.kyc_status == status:
        return current
    if (current.kyc_status, status) not in _KYC_MOVES:
        raise InvalidKycChange
    updated = customers.set_kyc_status(customer_id, status)
    customers.add_audit(customer_id, action=KYC_ACTIONS[status], actor=actor, reason=reason)
    return updated
