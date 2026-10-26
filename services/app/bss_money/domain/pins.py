"""Storing a voucher PIN: only a salted, slow hash of it, never the PIN.

A PIN has about 43 bits of choice (13 random digits), far fewer than an API key, so a fast hash such
as SHA-256 would let someone who copied the table try every PIN in hours. scrypt (in the standard
library, no new dependency) makes each guess cost about 50 ms and 16 MB, which puts all 10^13 out
of reach. The parameters are stored with the hash, so they can be raised later without breaking old
cards. Each card has its own random salt, so equal PINs hash differently.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from functools import cache

_N, _R, _P = 2**14, 8, 1
_SALT_BYTES = 16
_KEY_BYTES = 32
_PREFIX = "scrypt"


def hash_pin(pin: str) -> str:
    """`scrypt$n$r$p$salt$hash` for this PIN, with a fresh random salt."""
    salt = secrets.token_bytes(_SALT_BYTES)
    return _format(_N, _R, _P, salt, _derive(pin, salt, _N, _R, _P))


def verify_pin(pin: str, stored: str) -> bool:
    """Is `pin` the one `stored` was made from? False for anything that is not a stored hash."""
    parsed = _parse(stored)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    return hmac.compare_digest(_derive(pin, salt, n, r, p), expected)


@cache
def decoy_hash() -> str:
    """A hash of a PIN nobody has, for spending the same time when the card does not exist."""
    return hash_pin("0" * 14)


def _derive(pin: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        pin.encode("ascii", errors="replace"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=_KEY_BYTES,
        maxmem=2**26,
    )


def _format(n: int, r: int, p: int, salt: bytes, digest: bytes) -> str:
    return f"{_PREFIX}${n}${r}${p}${_b64(salt)}${_b64(digest)}"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _parse(stored: str) -> tuple[int, int, int, bytes, bytes] | None:
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != _PREFIX:
        return None
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt, digest = (
            base64.b64decode(parts[4], validate=True),
            base64.b64decode(parts[5], validate=True),
        )
    except (ValueError, binascii.Error):
        return None
    if not (2**10 <= n <= 2**20 and 1 <= r <= 16 and 1 <= p <= 4 and salt and digest):
        return None  # refuse parameters that would make one check slow or huge
    return n, r, p, salt, digest
