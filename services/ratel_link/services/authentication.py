"""Authenticate a request's `Authorization: Bearer <key>` against the stored hashes (ADR 0007).

Every way of failing returns a `Rejected` with a reason. The reason is for the operational log
only, never for the caller, and never includes the key, the secret or a hash.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ratel_link.repositories.ports import ApiKeyRepository
from ratel_link.security.api_key_tokens import DECOY_HASH, hash_secret, parse_token


class RejectReason(StrEnum):
    MISSING_HEADER = "missing_header"
    WRONG_SCHEME = "wrong_scheme"
    MALFORMED_TOKEN = "malformed_token"  # noqa: S105
    UNKNOWN_ID = "unknown_id"
    BAD_SECRET = "bad_secret"  # noqa: S105
    REVOKED = "revoked"
    EXPIRED = "expired"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ApiPrincipal:
    """Who is calling: the calling system and which of its keys was used."""

    api_key_id: str
    generation: int


@dataclass(frozen=True, slots=True)
class Rejected:
    """Why a request was refused. For the operational log only, never for the caller.

    `api_key_id` is set only when the token parsed, so it is safe and length-limited by the
    token format.
    """

    reason: RejectReason
    api_key_id: str | None = None


def authenticate(
    authorization: str | None, repository: ApiKeyRepository, now: datetime
) -> ApiPrincipal | Rejected:
    if not authorization:
        return Rejected(RejectReason.MISSING_HEADER)
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return Rejected(RejectReason.WRONG_SCHEME)
    parsed = parse_token(credentials)
    if parsed is None:
        return Rejected(RejectReason.MALFORMED_TOKEN)
    api_key_id, secret = parsed

    presented = hash_secret(secret).encode()
    record = repository.get(api_key_id)
    if record is None:
        hmac.compare_digest(presented, DECOY_HASH)
        return Rejected(RejectReason.UNKNOWN_ID, api_key_id)

    # Compare against every generation, with no early exit, so timing does not reveal which
    # generation (if any) matched. Revoked and expired ones are included only to report why.
    matches = [hmac.compare_digest(presented, g.secret_hash.encode()) for g in record.generations]
    if not matches:
        hmac.compare_digest(presented, DECOY_HASH)
    matched = next((g for g, ok in zip(record.generations, matches, strict=True) if ok), None)

    if matched is None:
        return Rejected(RejectReason.BAD_SECRET, api_key_id)
    if record.status != "active":
        return Rejected(RejectReason.DISABLED, api_key_id)
    if matched.revoked_at is not None:
        return Rejected(RejectReason.REVOKED, api_key_id)
    if matched.expires_at <= now:
        return Rejected(RejectReason.EXPIRED, api_key_id)
    return ApiPrincipal(api_key_id, matched.generation)
