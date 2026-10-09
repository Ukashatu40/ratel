"""API key format, generation and hashing (docs/adr/0007).

A key looks like `rlk_<api_key_id>.<secret>`: the id names the calling system and is not
secret, the secret is 256 random bits. Only a one-way hash of the secret is ever stored.
"""

from __future__ import annotations

import hashlib
import re
import secrets

from ratel_link.domain.identifiers import API_KEY_ID_PATTERN

TOKEN_PREFIX = "rlk_"  # noqa: S105  (a public marker for secret scanners, not a credential)


_SECRET_LENGTH = 43  # characters of secrets.token_urlsafe(32): 256 bits


_TOKEN_RE = re.compile(TOKEN_PREFIX + "(" + API_KEY_ID_PATTERN + r")\.([A-Za-z0-9_-]{43})")


_HASH_DOMAIN = b"ratel-link-api-key-v1|"


def hash_secret(secret: str) -> str:
    """SHA-256 over a domain prefix and the secret. The secret is 256-bit random, so a slow
    password hash would add latency and an attack surface without adding security (ADR 0007)."""
    return hashlib.sha256(_HASH_DOMAIN + secret.encode()).hexdigest()


# Compared against for an unknown api_key_id, so that path does the same work as a real check.
DECOY_HASH = hash_secret("0" * _SECRET_LENGTH).encode()


def generate_token(api_key_id: str) -> tuple[str, str]:
    """A new key and the hash to store. The key is shown once and never stored."""
    secret = secrets.token_urlsafe(32)
    return f"{TOKEN_PREFIX}{api_key_id}.{secret}", hash_secret(secret)


def parse_token(credentials: str) -> tuple[str, str] | None:
    """`(api_key_id, secret)` if the text is a well-formed key, otherwise None."""
    match = _TOKEN_RE.fullmatch(credentials)
    return None if match is None else (match.group(1), match.group(2))
