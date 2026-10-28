"""Signing staff in and out, and checking a session on every request.

What makes this safe to run on a network that thieves and curious colleagues can both reach:
- A password is only ever compared against its scrypt hash, and the time spent is the same for an
  unknown email, a locked account and a wrong password, so the answer says nothing about which.
- Five wrong passwords in a row lock an account for fifteen minutes. The count is kept under a row
  lock, so simultaneous guesses cannot slip past it.
- A session is a random 256-bit token. Only its SHA-256 is stored; the token itself is in the
  browser's cookie and nowhere else. It ends after eight hours, or thirty minutes without use, or
  when the account is disabled or its password is reset.
- A refusal is **returned**, never raised: the failure count has to be saved, and an exception
  would roll the transaction back and lose it.

Nothing here logs an email, a password or a token.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.bss_lines.domain.staff import (
    LOCKOUT,
    MAX_FAILED_LOGINS,
    SESSION_IDLE_LIMIT,
    SESSION_MAX_AGE,
    SESSION_TOUCH_EVERY,
    Role,
    check_password_policy,
    hash_session_token,
    new_session_token,
    normalise_email,
)
from app.bss_lines.repositories.desk_ports import StaffRecord, StaffRepository
from common.logging import log_event
from common.passwords import decoy_hash, hash_password, verify_password

log = logging.getLogger("ratel.bss.lines.staff")


@dataclass(frozen=True)
class SignedIn:
    token: str  # goes in the cookie, once
    staff: StaffRecord
    max_age_seconds: int


def sign_in(staff: StaffRepository, email: str, password: str, now: datetime) -> SignedIn | None:
    """A session for these credentials, or None. None never says why."""
    try:
        normalised = normalise_email(email)
    except ValueError:
        verify_password(password, decoy_hash())  # the same time as any other refusal
        return None
    record = staff.by_email(normalised, lock=True)
    if record is None:
        verify_password(password, decoy_hash())
        return None

    locked = record.locked_until is not None and record.locked_until > now
    correct = verify_password(password, record.password_hash)  # always spend the time
    if locked or not record.active or not correct:
        if record.active and not locked and not correct:
            _count_failure(staff, record, now)
        return None

    if record.failed_logins or record.locked_until is not None:
        staff.clear_failures(record.staff_id)
    token = new_session_token()
    staff.add_session(record.staff_id, hash_session_token(token), now + SESSION_MAX_AGE, now)
    log_event(log, logging.INFO, "staff.signed_in", staff_id=record.staff_id)
    return SignedIn(token, record, int(SESSION_MAX_AGE.total_seconds()))


def _count_failure(staff: StaffRepository, record: StaffRecord, now: datetime) -> None:
    failures = record.failed_logins + 1
    if failures >= MAX_FAILED_LOGINS:
        staff.record_failure(record.staff_id, 0, now + LOCKOUT)
        log_event(log, logging.WARNING, "staff.locked_out", staff_id=record.staff_id)
    else:
        staff.record_failure(record.staff_id, failures, None)
        log_event(log, logging.INFO, "staff.sign_in_failed", staff_id=record.staff_id)


def authenticate(staff: StaffRepository, token: str, now: datetime) -> StaffRecord | None:
    """The signed-in staff member for this cookie value, or None. Ends a stale session."""
    if not token or len(token) > 200:
        return None
    token_hash = hash_session_token(token)
    found = staff.session_by_hash(token_hash)
    if found is None:
        return None
    session, record = found
    if (
        not record.active
        or session.expires_at <= now
        or now - session.last_seen_at > SESSION_IDLE_LIMIT
    ):
        staff.delete_session(token_hash)
        return None
    if now - session.last_seen_at >= SESSION_TOUCH_EVERY:
        staff.touch_session(session.session_id, now)
    return record


def sign_out(staff: StaffRepository, token: str) -> None:
    if token and len(token) <= 200:
        staff.delete_session(hash_session_token(token))


def create_staff(
    staff: StaffRepository, *, email: str, name: str, role: str, password: str
) -> StaffRecord:
    """A new account. ValueError says what is wrong (never the password); the CLI shows it."""
    normalised = normalise_email(email)
    if not name.strip() or len(name) > 120:
        raise ValueError("the name must be 1 to 120 characters")
    check_password_policy(password)
    return staff.add_staff(
        email=normalised,
        name=name.strip(),
        role=Role(role).value,
        password_hash=hash_password(password),
    )


def reset_password(staff: StaffRepository, email: str, password: str) -> bool:
    """Set a new password and end the account's sessions. False if there is no such account."""
    check_password_policy(password)
    record = staff.by_email(normalise_email(email), lock=True)
    if record is None:
        return False
    staff.set_password_hash(record.staff_id, hash_password(password))
    staff.delete_sessions_of(record.staff_id)
    log_event(log, logging.WARNING, "staff.password_reset", staff_id=record.staff_id)
    return True


def set_active(staff: StaffRepository, email: str, active: bool) -> bool:
    """Enable or disable an account (disabling ends its sessions). False if there is none."""
    record = staff.by_email(normalise_email(email), lock=True)
    if record is None:
        return False
    staff.set_active(record.staff_id, active)
    if not active:
        staff.delete_sessions_of(record.staff_id)
    log_event(log, logging.WARNING, "staff.active_changed", staff_id=record.staff_id, active=active)
    return True
