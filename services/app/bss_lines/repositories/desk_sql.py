"""SQLAlchemy implementations of the interfaces in `desk_ports.py`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Customer, Line, Number, Plan, Sim
from app.bss_lines.models.replay import IdempotentCreate
from app.bss_lines.models.staff import StaffSession, StaffUser
from app.bss_lines.repositories.desk_ports import (
    CustomerRecord,
    DuplicateCreate,
    DuplicateStaff,
    LineRecord,
    PlanRecord,
    SessionRecord,
    SimRecord,
    StaffRecord,
)


def _utc(moment: datetime) -> datetime:
    """SQLite hands back naive times; they were stored as UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _staff(row: StaffUser) -> StaffRecord:
    return StaffRecord(
        staff_id=row.staff_id,
        email=row.email,
        name=row.name,
        role=row.role,
        password_hash=row.password_hash,
        active=row.active,
        failed_logins=row.failed_logins,
        locked_until=None if row.locked_until is None else _utc(row.locked_until),
    )


class SqlStaffRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_staff(self, *, email: str, name: str, role: str, password_hash: str) -> StaffRecord:
        row = StaffUser(
            email=email,
            name=name,
            role=role,
            password_hash=password_hash,
            active=True,
            failed_logins=0,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            if self.by_email(email) is None:
                raise
            raise DuplicateStaff from exc
        return _staff(row)

    def by_email(self, email: str, *, lock: bool = False) -> StaffRecord | None:
        statement = select(StaffUser).where(StaffUser.email == email)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        row = self._session.execute(statement).scalar_one_or_none()
        return None if row is None else _staff(row)

    def by_id(self, staff_id: int) -> StaffRecord | None:
        row = self._session.get(StaffUser, staff_id)
        return None if row is None else _staff(row)

    def all_staff(self) -> list[StaffRecord]:
        rows = self._session.scalars(select(StaffUser).order_by(StaffUser.staff_id))
        return [_staff(row) for row in rows]

    def record_failure(self, staff_id: int, failures: int, locked_until: datetime | None) -> None:
        self._session.execute(
            update(StaffUser)
            .where(StaffUser.staff_id == staff_id)
            .values(failed_logins=failures, locked_until=locked_until)
        )

    def clear_failures(self, staff_id: int) -> None:
        self.record_failure(staff_id, 0, None)

    def set_password_hash(self, staff_id: int, password_hash: str) -> None:
        self._session.execute(
            update(StaffUser)
            .where(StaffUser.staff_id == staff_id)
            .values(password_hash=password_hash, failed_logins=0, locked_until=None)
        )

    def set_active(self, staff_id: int, active: bool) -> None:
        self._session.execute(
            update(StaffUser).where(StaffUser.staff_id == staff_id).values(active=active)
        )

    def add_session(
        self, staff_id: int, token_hash: str, expires_at: datetime, now: datetime
    ) -> None:
        self._session.add(
            StaffSession(
                token_hash=token_hash, staff_id=staff_id, expires_at=expires_at, last_seen_at=now
            )
        )
        self._session.flush()

    def session_by_hash(self, token_hash: str) -> tuple[SessionRecord, StaffRecord] | None:
        row = self._session.execute(
            select(StaffSession, StaffUser)
            .join(StaffUser, StaffUser.staff_id == StaffSession.staff_id)
            .where(StaffSession.token_hash == token_hash)
        ).first()
        if row is None:
            return None
        session, staff = row
        record = SessionRecord(
            session_id=session.session_id,
            staff_id=session.staff_id,
            expires_at=_utc(session.expires_at),
            last_seen_at=_utc(session.last_seen_at),
        )
        return record, _staff(staff)

    def touch_session(self, session_id: int, now: datetime) -> None:
        self._session.execute(
            update(StaffSession)
            .where(StaffSession.session_id == session_id)
            .values(last_seen_at=now)
        )

    def delete_session(self, token_hash: str) -> None:
        self._session.execute(delete(StaffSession).where(StaffSession.token_hash == token_hash))

    def delete_sessions_of(self, staff_id: int) -> None:
        self._session.execute(delete(StaffSession).where(StaffSession.staff_id == staff_id))

    def delete_expired_sessions(self, now: datetime) -> int:
        result = self._session.execute(delete(StaffSession).where(StaffSession.expires_at < now))
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _customer(row: Customer) -> CustomerRecord:
    return CustomerRecord(
        customer_id=row.customer_id,
        name=row.name,
        phone=row.phone,
        email=row.email,
        id_type=row.id_type,
        id_number=row.id_number,
        address=row.address,
        kyc_status=row.kyc_status,
        blocked=row.blocked,
    )


class SqlCustomerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

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
    ) -> CustomerRecord:
        row = Customer(
            name=name,
            phone=phone,
            email=email,
            id_type=id_type,
            id_number=id_number,
            address=address,
            kyc_status=kyc_status,
            blocked=False,
        )
        self._session.add(row)
        self._session.flush()
        return _customer(row)

    def get_customer(self, customer_id: int) -> CustomerRecord | None:
        row = self._session.get(Customer, customer_id)
        return None if row is None else _customer(row)


class SqlReplayRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def created_by(self, scope: str, key: str) -> int | None:
        return self._session.scalar(
            select(IdempotentCreate.resource_id).where(
                IdempotentCreate.scope == scope, IdempotentCreate.key == key
            )
        )

    def remember(self, scope: str, key: str, resource_id: int) -> None:
        try:
            with self._session.begin_nested():
                self._session.add(IdempotentCreate(scope=scope, key=key, resource_id=resource_id))
                self._session.flush()
        except IntegrityError as exc:
            raise DuplicateCreate from exc


class SqlCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def plans_on_sale(self) -> list[PlanRecord]:
        rows = self._session.scalars(
            select(Plan).where(Plan.state == "on_sale").order_by(Plan.plan_id)
        )
        return [
            PlanRecord(
                plan_id=p.plan_id,
                name=p.name,
                price_kobo=p.price_kobo,
                validity_days=p.validity_days,
                data_bytes=p.data_bytes,
                speed_ul_mbps=p.speed_ul_mbps,
                speed_dl_mbps=p.speed_dl_mbps,
                slow_ul_mbps=p.slow_ul_mbps,
                slow_dl_mbps=p.slow_dl_mbps,
                channels=p.channels,
                on_exhaustion=p.on_exhaustion,
                state=p.state,
            )
            for p in rows
        ]

    def free_sims(self, limit: int) -> list[SimRecord]:
        rows = self._session.scalars(
            select(Sim).where(Sim.state == "in_stock").order_by(Sim.iccid).limit(limit)
        )
        return [SimRecord(s.iccid, s.imsi, s.batch, s.state) for s in rows]

    def free_numbers(self, limit: int) -> list[str]:
        rows = self._session.scalars(
            select(Number.msisdn)
            .where(Number.state == "available")
            .order_by(Number.msisdn)
            .limit(limit)
        )
        return list(rows)


def _line(row: Line) -> LineRecord:
    return LineRecord(
        line_id=row.line_id,
        customer_id=row.customer_id,
        iccid=row.iccid,
        imsi=row.imsi,
        msisdn=row.msisdn,
        plan_id=row.plan_id,
        state=row.state,
        state_before_suspension=row.state_before_suspension,
        expires_at=None if row.expires_at is None else _utc(row.expires_at),
    )


class SqlLineSalesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_plan(self, plan_id: int) -> PlanRecord | None:
        p = self._session.get(Plan, plan_id)
        if p is None:
            return None
        return PlanRecord(
            plan_id=p.plan_id,
            name=p.name,
            price_kobo=p.price_kobo,
            validity_days=p.validity_days,
            data_bytes=p.data_bytes,
            speed_ul_mbps=p.speed_ul_mbps,
            speed_dl_mbps=p.speed_dl_mbps,
            slow_ul_mbps=p.slow_ul_mbps,
            slow_dl_mbps=p.slow_dl_mbps,
            channels=p.channels,
            on_exhaustion=p.on_exhaustion,
            state=p.state,
        )

    def take_sim(self, iccid: str) -> SimRecord | None:
        # One statement: the database lets exactly one of two simultaneous callers see the row.
        # Raw SQL, as in services/stock.py: a SIM's state is not a line's, and the line-state
        # rule refuses any `.values(state=...)` it cannot attribute.
        row = self._session.execute(
            text(
                "UPDATE sim SET state = 'in_use', updated_at = now() "
                "WHERE iccid = :iccid AND state = 'in_stock' RETURNING iccid, imsi, batch"
            ),
            {"iccid": iccid},
        ).first()
        return None if row is None else SimRecord(row.iccid, row.imsi, row.batch, "in_use")

    def take_number(self, msisdn: str) -> bool:
        row = self._session.execute(
            text(
                "UPDATE number SET state = 'in_use', updated_at = now() "
                "WHERE msisdn = :msisdn AND state = 'available' RETURNING msisdn"
            ),
            {"msisdn": msisdn},
        ).first()
        return row is not None

    def add_line(
        self, *, customer_id: int, iccid: str, imsi: str, msisdn: str, plan_id: int
    ) -> LineRecord:
        row = Line(
            customer_id=customer_id,
            iccid=iccid,
            imsi=imsi,
            msisdn=msisdn,
            plan_id=plan_id,
            state="awaiting_activation",
        )
        self._session.add(row)
        self._session.flush()
        return _line(row)

    def get_line(self, line_id: int) -> LineRecord | None:
        row = self._session.get(Line, line_id)
        return None if row is None else _line(row)
