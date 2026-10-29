"""Tests for password hashing."""

from __future__ import annotations

from common.passwords import decoy_hash, hash_password, verify_password

PASSWORD = "a synthetic test password"


def test_the_right_password_verifies_and_a_wrong_one_does_not() -> None:
    stored = hash_password(PASSWORD)
    assert verify_password(PASSWORD, stored)
    assert not verify_password(PASSWORD + "x", stored)
    assert not verify_password("", stored)


def test_the_hash_never_contains_the_password_and_is_salted() -> None:
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert PASSWORD not in first
    assert first != second  # a fresh salt each time
    assert first.startswith("scrypt$")


def test_something_that_is_not_our_hash_never_verifies() -> None:
    for stored in ("", PASSWORD, "scrypt$", "md5$1$2$3$4$5", "scrypt$x$8$1$AA==$AA=="):
        assert not verify_password(PASSWORD, stored)


def test_parameters_that_would_make_a_check_huge_are_refused() -> None:
    stored = hash_password(PASSWORD)
    parts = stored.split("$")
    parts[1] = str(2**30)  # n far beyond what we ever write
    assert not verify_password(PASSWORD, "$".join(parts))


def test_a_very_long_password_is_handled_without_error() -> None:
    stored = hash_password("x" * 100_000)
    assert verify_password("x" * 100_000, stored)


def test_the_decoy_is_a_real_hash_that_matches_nothing_we_know() -> None:
    assert decoy_hash() == decoy_hash()  # made once
    assert not verify_password(PASSWORD, decoy_hash())
    assert not verify_password("", decoy_hash())
