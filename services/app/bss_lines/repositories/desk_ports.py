"""Storage interfaces for what RatelDesk uses: staff, customers, the catalogue, repeated creates.

Kept apart from `ports.py` (the lines themselves). Services depend on these protocols, not on
SQLAlchemy; the implementations are in `desk_sql.py`. Everything works inside the caller's
transaction and never commits.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class DuplicateStaff(Exception):
    """An account with this email exists already. Nothing was changed."""


class DuplicateCreate(Exception):
    """This Idempotency-Key already created a record (a retry that raced the first call)."""


@dataclass(frozen=True)
class StaffRecord:
    staff_id: int
    email: str
    name: str
    role: str
    password_hash: str
    active: bool
    failed_logins: int
    locked_until: datetime | None


@dataclass(frozen=True)
class SessionRecord:
    session_id: int
    staff_id: int
    expires_at: datetime
    last_seen_at: datetime


class StaffRepository(Protocol):
    def add_staff(self, *, email: str, name: str, role: str, password_hash: str) -> StaffRecord:
        """Store a new account. Raises `DuplicateStaff` if the email is taken."""
        ...

    def by_email(self, email: str, *, lock: bool = False) -> StaffRecord | None:
        """The account with this (already normalised) email. `lock` holds it for the transaction."""
        ...

    def by_id(self, staff_id: int) -> StaffRecord | None: ...

    def all_staff(self) -> list[StaffRecord]: ...

    def record_failure(
        self, staff_id: int, failures: int, locked_until: datetime | None
    ) -> None: ...

    def clear_failures(self, staff_id: int) -> None: ...

    def set_password_hash(self, staff_id: int, password_hash: str) -> None: ...

    def set_active(self, staff_id: int, active: bool) -> None: ...

    def add_session(
        self, staff_id: int, token_hash: str, expires_at: datetime, now: datetime
    ) -> None: ...

    def session_by_hash(self, token_hash: str) -> tuple[SessionRecord, StaffRecord] | None: ...

    def touch_session(self, session_id: int, now: datetime) -> None: ...

    def delete_session(self, token_hash: str) -> None: ...

    def delete_sessions_of(self, staff_id: int) -> None: ...

    def delete_expired_sessions(self, now: datetime) -> int: ...


@dataclass(frozen=True)
class CustomerRecord:
    customer_id: int
    name: str
    phone: str
    email: str
    id_type: str
    id_number: str
    address: str
    kyc_status: str
    blocked: bool


class CustomerRepository(Protocol):
    def add_customer(
        self,
        *,
        name: str,
        phone: str,
        email: str,
        id_type: str,
        id_number: str,
        address: str,
        kyc_status: str,
    ) -> CustomerRecord: ...

    def get_customer(self, customer_id: int) -> CustomerRecord | None: ...


class ReplayRepository(Protocol):
    """Which Idempotency-Key created which record."""

    def created_by(self, scope: str, key: str) -> int | None:
        """The id of the record this key created, or None if it has not been used."""
        ...

    def remember(self, scope: str, key: str, resource_id: int) -> None:
        """Raises `DuplicateCreate` if the key was used in the meantime."""
        ...


@dataclass(frozen=True)
class PlanRecord:
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


@dataclass(frozen=True)
class SimRecord:
    iccid: str
    imsi: str
    batch: str
    state: str


class CatalogRepository(Protocol):
    def plans_on_sale(self) -> Sequence[PlanRecord]: ...

    def free_sims(self, limit: int) -> Sequence[SimRecord]: ...

    def free_numbers(self, limit: int) -> Sequence[str]: ...


@dataclass(frozen=True)
class LineRecord:
    line_id: int
    customer_id: int
    iccid: str
    imsi: str
    msisdn: str
    plan_id: int
    state: str
    state_before_suspension: str | None
    expires_at: datetime | None


class LineSalesRepository(Protocol):
    """What selling a SIM needs: the plan, taking stock, and writing the line."""

    def get_plan(self, plan_id: int) -> PlanRecord | None: ...

    def take_sim(self, iccid: str) -> SimRecord | None:
        """Atomically take a free SIM. None if it is not free (taken, retired or unknown)."""
        ...

    def take_number(self, msisdn: str) -> bool:
        """Atomically take a free number. False if it is not free (taken or unknown)."""
        ...

    def add_line(
        self, *, customer_id: int, iccid: str, imsi: str, msisdn: str, plan_id: int
    ) -> LineRecord:
        """A new line in `awaiting_activation`."""
        ...

    def get_line(self, line_id: int) -> LineRecord | None: ...
