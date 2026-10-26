"""A PIN is kept only as a salted, slow hash."""

from __future__ import annotations

import pytest

from app.bss_money.domain.pins import decoy_hash, hash_pin, verify_pin

PIN = "12345678901231"


def test_the_right_pin_verifies_and_a_wrong_one_does_not() -> None:
    stored = hash_pin(PIN)
    assert verify_pin(PIN, stored)
    assert not verify_pin("12345678901248", stored)
    assert not verify_pin("", stored)


def test_the_hash_does_not_contain_the_pin_in_any_form() -> None:
    stored = hash_pin(PIN)
    assert PIN not in stored
    assert PIN[:8] not in stored
    assert stored.startswith("scrypt$")


def test_the_same_pin_hashes_differently_each_time() -> None:
    assert hash_pin(PIN) != hash_pin(PIN)


def test_the_hash_fits_the_column() -> None:
    assert len(hash_pin(PIN)) <= 200


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "not a hash",
        "scrypt$16384$8$1$AAAA",  # too few parts
        "bcrypt$16384$8$1$AAAA$AAAA",  # another scheme
        "scrypt$x$8$1$AAAA$AAAA",  # not a number
        "scrypt$16384$8$1$!!!$AAAA",  # not base64
        "scrypt$16384$8$1$$",  # empty salt and hash
    ],
)
def test_anything_that_is_not_a_stored_hash_never_verifies(stored: str) -> None:
    assert not verify_pin(PIN, stored)


def test_a_stored_hash_cannot_make_one_check_cost_the_earth() -> None:
    import base64

    salt, digest = base64.b64encode(b"s" * 16).decode(), base64.b64encode(b"h" * 32).decode()
    huge = f"scrypt${2**30}$8$1${salt}${digest}"
    assert not verify_pin(PIN, huge)  # refused at once, not computed


def test_the_decoy_is_a_real_hash_no_pin_of_ours_matches() -> None:
    assert decoy_hash().startswith("scrypt$")
    assert not verify_pin(PIN, decoy_hash())
