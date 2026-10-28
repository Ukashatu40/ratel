"""Hashing a password for storage: salted scrypt from the standard library, nothing else.

scrypt is slow and memory-hard on purpose (about 100 ms and 32 MB per check at these settings), so
a stolen table of hashes cannot be tried at speed. The parameters are stored with each hash, so
they can be raised later without locking anyone out, and a stored value that is not one of ours
never verifies. Comparison is constant time.

Use `decoy_hash()` to spend the same time when there is no such user, so the time taken does not
tell a guesser which emails exist.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from functools import cache

_N, _R, _P = 2**15, 8, 1
_SALT_BYTES = 16
_KEY_BYTES = 32
_PREFIX = "scrypt"
_MAX_PASSWORD_BYTES = 1024  # nobody types more; refusing keeps one request from costing much


def hash_password(password: str) -> str:
    """`scrypt$n$r$p$salt$hash` for this password, with a fresh random salt."""
    salt = secrets.token_bytes(_SALT_BYTES)
    return _format(_N, _R, _P, salt, _derive(password, salt, _N, _R, _P))


def verify_password(password: str, stored: str) -> bool:
    """Is `password` the one `stored` was made from? False for anything that is not our hash."""
    parsed = _parse(stored)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    return hmac.compare_digest(_derive(password, salt, n, r, p), expected)


@cache
def decoy_hash() -> str:
    """A hash of a password nobody has, for spending the same time when the user does not exist."""
    return hash_password(secrets.token_urlsafe(16))


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    raw = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return hashlib.scrypt(raw, salt=salt, n=n, r=r, p=p, dklen=_KEY_BYTES, maxmem=2**27)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _format(n: int, r: int, p: int, salt: bytes, digest: bytes) -> str:
    return f"{_PREFIX}${n}${r}${p}${_b64(salt)}${_b64(digest)}"


def _parse(stored: str) -> tuple[int, int, int, bytes, bytes] | None:
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != _PREFIX:
        return None
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = base64.b64decode(parts[4], validate=True)
        digest = base64.b64decode(parts[5], validate=True)
    except (ValueError, binascii.Error):
        return None
    if not (2**10 <= n <= 2**20 and 1 <= r <= 16 and 1 <= p <= 4 and salt and digest):
        return None  # refuse parameters that would make one check slow or huge
    return n, r, p, salt, digest
