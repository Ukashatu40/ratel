"""Staff who use RatelDesk: roles, what each role may do, and the rules around signing in.

Pure: no database, no clock, no network. Decision 11 (staff roles and authentication) was open;
these are the project lead's choices of 2026-10-27 for the first release, each marked TODO(PRD)
where the PRD may change it:

- Two roles, as PRODUCT_RULES.md decided on 2026-10-23: `agent` (customer care) and `admin`.
- A session lasts 8 hours at most and ends after 30 minutes without use.
- Five wrong passwords in a row lock the account for 15 minutes.
- A password is at least 12 characters.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta
from enum import StrEnum

SESSION_MAX_AGE = timedelta(hours=8)
SESSION_IDLE_LIMIT = timedelta(minutes=30)
SESSION_TOUCH_EVERY = timedelta(minutes=1)  # last_seen is written at most this often
MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)
MIN_PASSWORD_LENGTH = 12
COOKIE_NAME = "ratel_desk"

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


class Role(StrEnum):
    AGENT = "agent"
    ADMIN = "admin"


class Permission(StrEnum):
    READ = "read"  # customers, lines, plans, stock
    CREATE_CUSTOMER = "create_customer"
    VERIFY_KYC = "verify_kyc"  # create a customer whose KYC is already verified
    CREATE_LINE = "create_line"
    ACTIVATE_LINE = "activate_line"
    SUSPEND_LINE = "suspend_line"
    TERMINATE_LINE = "terminate_line"


# TODO(PRD): who may do what. Customer care sells and looks after lines; only an admin vouches for
# an identity or ends a line for good.
_AGENT = frozenset(
    {
        Permission.READ,
        Permission.CREATE_CUSTOMER,
        Permission.CREATE_LINE,
        Permission.ACTIVATE_LINE,
        Permission.SUSPEND_LINE,
    }
)
PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.AGENT: _AGENT,
    Role.ADMIN: _AGENT | {Permission.VERIFY_KYC, Permission.TERMINATE_LINE},
}


def may(role: Role, permission: Permission) -> bool:
    return permission in PERMISSIONS[role]


def normalise_email(email: str) -> str:
    """Lower case, trimmed. ValueError if it cannot be an address."""
    value = email.strip().lower()
    if not _EMAIL.match(value):
        raise ValueError("not an email address")
    return value


def check_password_policy(password: str) -> None:
    """ValueError saying what is wrong (never the password)."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"a password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > 256:
        raise ValueError("a password must be at most 256 characters")
    if len(set(password)) < 5:
        raise ValueError("a password must not be made of a few repeated characters")


def new_session_token() -> str:
    """The value that goes in the cookie. It exists nowhere else: only its hash is stored."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """SHA-256 is enough here: the token is 256 random bits, not a guessable password."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
