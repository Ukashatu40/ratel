"""Tests for the staff rules: roles, passwords, emails, tokens."""

from __future__ import annotations

import pytest

from app.bss_lines.domain.staff import (
    PERMISSIONS,
    Permission,
    Role,
    check_password_policy,
    hash_session_token,
    may,
    new_session_token,
    normalise_email,
)


def test_every_role_and_permission_is_decided() -> None:
    assert set(PERMISSIONS) == set(Role)
    for role in Role:
        assert Permission.READ in PERMISSIONS[role]


def test_care_cannot_vouch_for_an_identity_or_end_a_line() -> None:
    assert not may(Role.AGENT, Permission.VERIFY_KYC)
    assert not may(Role.AGENT, Permission.TERMINATE_LINE)
    assert may(Role.ADMIN, Permission.VERIFY_KYC)
    assert may(Role.ADMIN, Permission.TERMINATE_LINE)


def test_admin_can_do_everything_care_can() -> None:
    assert PERMISSIONS[Role.AGENT] <= PERMISSIONS[Role.ADMIN]


def test_an_email_is_trimmed_and_lower_cased() -> None:
    assert normalise_email("  Agent@Example.TEST ") == "agent@example.test"


@pytest.mark.parametrize("bad", ["", "no-at-sign", "a@b", "a b@c.de", "@c.de", "a@@c.de"])
def test_a_bad_email_is_refused(bad: str) -> None:
    with pytest.raises(ValueError):
        normalise_email(bad)


def test_password_policy() -> None:
    check_password_policy("a long enough password")
    for bad in ("short", "a" * 20, "x" * 300):
        with pytest.raises(ValueError):
            check_password_policy(bad)


def test_the_policy_message_never_repeats_the_password() -> None:
    with pytest.raises(ValueError) as caught:
        check_password_policy("tooshort")
    assert "tooshort" not in str(caught.value)


def test_a_session_token_is_random_and_only_its_hash_is_kept() -> None:
    first, second = new_session_token(), new_session_token()
    assert first != second and len(first) >= 40
    assert hash_session_token(first) != first
    assert hash_session_token(first) == hash_session_token(first)
