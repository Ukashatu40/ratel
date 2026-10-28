"""Tests for signing staff in and out, lockout, and session checks."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bss_lines.domain.staff import (
    LOCKOUT,
    MAX_FAILED_LOGINS,
    SESSION_IDLE_LIMIT,
    SESSION_MAX_AGE,
    hash_session_token,
)
from app.bss_lines.models.staff import StaffSession
from app.bss_lines.repositories.desk_ports import DuplicateStaff
from app.bss_lines.repositories.desk_sql import SqlStaffRepository
from app.bss_lines.services import staff_auth
from app.db import Base

PASSWORD = "a synthetic long password"
EMAIL = "agent@example.test"
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cost of scrypt is a property of the hash, not of these rules: keep tests quick."""
    monkeypatch.setattr("common.passwords._N", 2**10)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def staff(session: Session) -> SqlStaffRepository:
    repo = SqlStaffRepository(session)
    staff_auth.create_staff(repo, email=EMAIL, name="Test Care", role="agent", password=PASSWORD)
    return repo


def test_the_right_credentials_give_a_session_that_authenticates(
    staff: SqlStaffRepository,
) -> None:
    signed_in = staff_auth.sign_in(staff, "  AGENT@example.test ", PASSWORD, T0)
    assert signed_in is not None
    assert signed_in.max_age_seconds == int(SESSION_MAX_AGE.total_seconds())
    who = staff_auth.authenticate(staff, signed_in.token, T0 + timedelta(minutes=5))
    assert who is not None and who.email == EMAIL and who.role == "agent"


def test_only_the_hash_of_the_token_is_stored(staff: SqlStaffRepository, session: Session) -> None:
    signed_in = staff_auth.sign_in(staff, EMAIL, PASSWORD, T0)
    assert signed_in is not None
    stored = session.scalars(select(StaffSession.token_hash)).all()
    assert stored == [hash_session_token(signed_in.token)]
    assert signed_in.token not in stored


def test_the_password_is_stored_only_as_a_hash(staff: SqlStaffRepository) -> None:
    record = staff.by_email(EMAIL)
    assert record is not None
    assert PASSWORD not in record.password_hash and record.password_hash.startswith("scrypt$")


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (EMAIL, "wrong password entirely"),
        ("nobody@example.test", PASSWORD),
        ("not an email", PASSWORD),
    ],
)
def test_every_refusal_is_the_same_none(
    staff: SqlStaffRepository, email: str, password: str
) -> None:
    assert staff_auth.sign_in(staff, email, password, T0) is None


@pytest.mark.parametrize("email", ["nobody@example.test", "not an email"])
def test_an_unknown_email_costs_the_same_hash_check(
    staff: SqlStaffRepository, monkeypatch: pytest.MonkeyPatch, email: str
) -> None:
    calls: list[str] = []
    real = staff_auth.verify_password
    monkeypatch.setattr(staff_auth, "verify_password", lambda p, s: calls.append(s) or real(p, s))
    assert staff_auth.sign_in(staff, email, PASSWORD, T0) is None
    assert len(calls) == 1  # a decoy hash was checked, so the time says nothing


def test_five_wrong_passwords_lock_the_account_even_for_the_right_one(
    staff: SqlStaffRepository,
) -> None:
    for _ in range(MAX_FAILED_LOGINS):
        assert staff_auth.sign_in(staff, EMAIL, "wrong password entirely", T0) is None
    assert staff_auth.sign_in(staff, EMAIL, PASSWORD, T0 + timedelta(minutes=1)) is None
    after = T0 + LOCKOUT + timedelta(seconds=1)
    assert staff_auth.sign_in(staff, EMAIL, PASSWORD, after) is not None


def test_four_wrong_passwords_do_not_lock_and_a_success_resets_the_count(
    staff: SqlStaffRepository,
) -> None:
    for _ in range(MAX_FAILED_LOGINS - 1):
        staff_auth.sign_in(staff, EMAIL, "wrong password entirely", T0)
    assert staff_auth.sign_in(staff, EMAIL, PASSWORD, T0) is not None
    record = staff.by_email(EMAIL)
    assert record is not None and record.failed_logins == 0
    for _ in range(MAX_FAILED_LOGINS - 1):  # the count started again from zero
        staff_auth.sign_in(staff, EMAIL, "wrong password entirely", T0)
    assert staff_auth.sign_in(staff, EMAIL, PASSWORD, T0) is not None


def test_guessing_during_a_lock_does_not_extend_it(staff: SqlStaffRepository) -> None:
    for _ in range(MAX_FAILED_LOGINS):
        staff_auth.sign_in(staff, EMAIL, "wrong password entirely", T0)
    for minute in range(1, 10):
        staff_auth.sign_in(staff, EMAIL, "wrong password entirely", T0 + timedelta(minutes=minute))
    assert staff_auth.sign_in(staff, EMAIL, PASSWORD, T0 + LOCKOUT + timedelta(seconds=1))


def test_a_disabled_account_cannot_sign_in_and_loses_its_sessions(
    staff: SqlStaffRepository,
) -> None:
    signed_in = staff_auth.sign_in(staff, EMAIL, PASSWORD, T0)
    assert signed_in is not None
    assert staff_auth.set_active(staff, EMAIL, False)
    assert staff_auth.authenticate(staff, signed_in.token, T0) is None
    assert staff_auth.sign_in(staff, EMAIL, PASSWORD, T0) is None
    assert staff_auth.set_active(staff, EMAIL, True)
    assert staff_auth.sign_in(staff, EMAIL, PASSWORD, T0) is not None


def test_a_session_ends_after_the_maximum_age_even_if_in_use(staff: SqlStaffRepository) -> None:
    signed_in = staff_auth.sign_in(staff, EMAIL, PASSWORD, T0)
    assert signed_in is not None
    moment = T0
    while moment + timedelta(minutes=20) < T0 + SESSION_MAX_AGE:
        moment += timedelta(minutes=20)  # always inside the idle limit
        assert staff_auth.authenticate(staff, signed_in.token, moment) is not None
    assert staff_auth.authenticate(staff, signed_in.token, T0 + SESSION_MAX_AGE) is None


def test_a_session_ends_after_the_idle_limit(staff: SqlStaffRepository) -> None:
    signed_in = staff_auth.sign_in(staff, EMAIL, PASSWORD, T0)
    assert signed_in is not None
    late = T0 + SESSION_IDLE_LIMIT + timedelta(seconds=1)
    assert staff_auth.authenticate(staff, signed_in.token, late) is None
    # and it is gone, not merely refused: coming back inside the window does not revive it
    assert staff_auth.authenticate(staff, signed_in.token, T0 + timedelta(minutes=1)) is None


def test_use_keeps_a_session_alive(staff: SqlStaffRepository) -> None:
    signed_in = staff_auth.sign_in(staff, EMAIL, PASSWORD, T0)
    assert signed_in is not None
    for minutes in (20, 40, 60, 80):
        moment = T0 + timedelta(minutes=minutes)
        assert staff_auth.authenticate(staff, signed_in.token, moment) is not None


@pytest.mark.parametrize("token", ["", "x", "x" * 201, "not-a-real-token"])
def test_a_token_we_did_not_issue_is_refused(staff: SqlStaffRepository, token: str) -> None:
    assert staff_auth.authenticate(staff, token, T0) is None


def test_sign_out_ends_that_session_only(staff: SqlStaffRepository) -> None:
    first = staff_auth.sign_in(staff, EMAIL, PASSWORD, T0)
    second = staff_auth.sign_in(staff, EMAIL, PASSWORD, T0)
    assert first is not None and second is not None
    staff_auth.sign_out(staff, first.token)
    assert staff_auth.authenticate(staff, first.token, T0) is None
    assert staff_auth.authenticate(staff, second.token, T0) is not None
    staff_auth.sign_out(staff, "")  # harmless
    staff_auth.sign_out(staff, "never issued")


def test_a_password_reset_ends_every_session_and_clears_a_lock(
    staff: SqlStaffRepository,
) -> None:
    signed_in = staff_auth.sign_in(staff, EMAIL, PASSWORD, T0)
    assert signed_in is not None
    for _ in range(MAX_FAILED_LOGINS):
        staff_auth.sign_in(staff, EMAIL, "wrong password entirely", T0)
    assert staff_auth.reset_password(staff, EMAIL, "a different long password")
    assert staff_auth.authenticate(staff, signed_in.token, T0) is None
    assert staff_auth.sign_in(staff, EMAIL, PASSWORD, T0) is None
    assert staff_auth.sign_in(staff, EMAIL, "a different long password", T0) is not None
    assert not staff_auth.reset_password(staff, "nobody@example.test", "a different long password")


def test_creating_an_account_checks_everything(staff: SqlStaffRepository) -> None:
    with pytest.raises(DuplicateStaff):
        staff_auth.create_staff(
            staff, email=EMAIL.upper(), name="Again", role="agent", password=PASSWORD
        )
    for kwargs in (
        {"email": "bad", "name": "n", "role": "agent", "password": PASSWORD},
        {"email": "a@b.cd", "name": " ", "role": "agent", "password": PASSWORD},
        {"email": "a@b.cd", "name": "n", "role": "root", "password": PASSWORD},
        {"email": "a@b.cd", "name": "n", "role": "agent", "password": "short"},
    ):
        with pytest.raises(ValueError):
            staff_auth.create_staff(staff, **kwargs)  # type: ignore[arg-type]


def test_nothing_is_logged_that_identifies_a_person_or_a_secret(
    staff: SqlStaffRepository, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    signed_in = staff_auth.sign_in(staff, EMAIL, PASSWORD, T0)
    assert signed_in is not None
    for _ in range(MAX_FAILED_LOGINS):
        staff_auth.sign_in(staff, EMAIL, "wrong password entirely", T0)
    staff_auth.reset_password(staff, EMAIL, "a different long password")
    logged = caplog.text + "".join(str(getattr(r, "__dict__", "")) for r in caplog.records)
    for secret in (EMAIL, PASSWORD, "wrong password entirely", signed_in.token, "a different long"):
        assert secret not in logged
