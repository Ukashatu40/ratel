"""API-key authentication and key administration for RatelLink (docs/adr/0007).

One key per calling system, sent as `Authorization: Bearer <key>`. A key looks like
`rlk_<api_key_id>.<secret>`: the id names the calling system and is not secret, the secret is 256
random bits. Only a one-way hash of the secret is stored, never the key.

Every way of failing returns the same 401 to the caller. The specific reason goes to the
operational log only, and never includes the token, the secret or a hash.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from fastapi import Request
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from common.errors import ApiError
from common.logging import bind_log_context, log_event
from ratel_link.config import MAX_API_KEY_AGE_DAYS, Settings
from ratel_link.models import API_KEY_ID_PATTERN, ApiKeyGeneration, ApiKeyRecord, is_api_key_id
from ratel_link.repositories import ApiKeyRepository

log = logging.getLogger("ratel.link.auth")

TOKEN_PREFIX = "rlk_"  # noqa: S105  (a public marker for secret scanners, not a credential)
_SECRET_LENGTH = 43  # characters of secrets.token_urlsafe(32): 256 bits
_TOKEN_RE = re.compile(TOKEN_PREFIX + "(" + API_KEY_ID_PATTERN + r")\.([A-Za-z0-9_-]{43})")
_HASH_DOMAIN = b"ratel-link-api-key-v1|"
_SYSTEM_NAME_MAX = 64
_PRINCIPAL_SCOPE_KEY = "ratel_link.principal"


def hash_secret(secret: str) -> str:
    """SHA-256 over a domain prefix and the secret. The secret is 256-bit random, so a slow
    password hash would add latency and an attack surface without adding security (ADR 0007)."""
    return hashlib.sha256(_HASH_DOMAIN + secret.encode()).hexdigest()


# Compared against for an unknown api_key_id, so that path does the same work as a real check.
_DUMMY_HASH = hash_secret("0" * _SECRET_LENGTH).encode()


def generate_token(api_key_id: str) -> tuple[str, str]:
    """A new key and the hash to store. The key is shown once and never stored."""
    secret = secrets.token_urlsafe(32)
    return f"{TOKEN_PREFIX}{api_key_id}.{secret}", hash_secret(secret)


# --- verification -------------------------------------------------------------------------------


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
    parsed = _TOKEN_RE.fullmatch(credentials)
    if parsed is None:
        return Rejected(RejectReason.MALFORMED_TOKEN)
    api_key_id, secret = parsed.groups()

    presented = hash_secret(secret).encode()
    record = repository.get(api_key_id)
    if record is None:
        hmac.compare_digest(presented, _DUMMY_HASH)
        return Rejected(RejectReason.UNKNOWN_ID, api_key_id)

    # Compare against every generation, with no early exit, so timing does not reveal which
    # generation (if any) matched. Revoked and expired ones are included only to report why.
    matches = [hmac.compare_digest(presented, g.secret_hash.encode()) for g in record.generations]
    if not matches:
        hmac.compare_digest(presented, _DUMMY_HASH)
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


# --- key administration (used by admin_cli) -----------------------------------------------------


class ApiKeyError(Exception):
    """An administration request that cannot be done. The message is safe to print."""


@dataclass(frozen=True, slots=True)
class KeyPolicy:
    max_age_days: int = MAX_API_KEY_AGE_DAYS
    overlap_days: int = 7
    warn_days: int = 14

    @classmethod
    def from_settings(cls, settings: Settings) -> KeyPolicy:
        return cls(
            settings.ratel_link_api_key_max_age_days,
            settings.ratel_link_api_key_rotation_overlap_days,
            settings.ratel_link_api_key_expiry_warn_days,
        )


@dataclass(frozen=True, slots=True)
class ExpiringKey:
    api_key_id: str
    generation: int
    days_left: int


def _is_live(g: ApiKeyGeneration, now: datetime) -> bool:
    return g.revoked_at is None and g.expires_at > now


def _issue(
    api_key_id: str, number: int, now: datetime, policy: KeyPolicy
) -> tuple[ApiKeyGeneration, str]:
    # The Build Plan's 90-day rotation rule is enforced here as well as in Settings, so no caller
    # can create a key that lives longer.
    if not 1 <= policy.max_age_days <= MAX_API_KEY_AGE_DAYS:
        raise ApiKeyError(f"an API key cannot be valid for more than {MAX_API_KEY_AGE_DAYS} days")
    token, secret_hash = generate_token(api_key_id)
    expires_at = now + timedelta(days=policy.max_age_days)
    return ApiKeyGeneration(number, secret_hash, created_at=now, expires_at=expires_at), token


def _system(repository: ApiKeyRepository, api_key_id: str) -> ApiKeyRecord:
    record = repository.get(api_key_id)
    if record is None:
        raise ApiKeyError(f"no calling system with api_key_id {api_key_id}")
    return record


def create_system(
    repository: ApiKeyRepository,
    api_key_id: str,
    system_name: str,
    now: datetime,
    policy: KeyPolicy,
) -> str:
    """Register a calling system with its first key. Returns the key, to be shown once."""
    if not is_api_key_id(api_key_id):
        raise ApiKeyError(
            "api_key_id must be 3 to 32 characters: lowercase letters, digits and hyphens, "
            "starting with a letter"
        )
    name = system_name.strip()
    if not name or len(name) > _SYSTEM_NAME_MAX:
        raise ApiKeyError(f"the system name must be 1 to {_SYSTEM_NAME_MAX} characters")
    generation, token = _issue(api_key_id, 1, now, policy)
    if not repository.insert(ApiKeyRecord(api_key_id, name, "active", now, (generation,))):
        raise ApiKeyError(f"a calling system with api_key_id {api_key_id} already exists")
    log_event(log, logging.INFO, "api_key.created", api_key_id=api_key_id, api_key_generation=1)
    return token


def rotate(repository: ApiKeyRepository, api_key_id: str, now: datetime, policy: KeyPolicy) -> str:
    """Add a new key. The current one keeps working for at most `overlap_days`, then stops.

    At most two keys of a system are valid at any time. Returns the new key, shown once.
    """
    record = _system(repository, api_key_id)
    if record.status != "active":
        raise ApiKeyError(f"{api_key_id} is disabled")
    live = [g for g in record.generations if _is_live(g, now)]
    if len(live) >= 2:
        raise ApiKeyError(
            f"{api_key_id} already has two valid keys: revoke one, or wait for the overlap to end"
        )
    cutoff = now + timedelta(days=policy.overlap_days)
    older = tuple(
        replace(g, expires_at=min(g.expires_at, cutoff)) if _is_live(g, now) else g
        for g in record.generations
    )
    number = max((g.generation for g in record.generations), default=0) + 1
    generation, token = _issue(api_key_id, number, now, policy)
    repository.replace(replace(record, generations=(*older, generation)))
    log_event(
        log, logging.INFO, "api_key.rotated", api_key_id=api_key_id, api_key_generation=number
    )
    return token


def revoke(repository: ApiKeyRepository, api_key_id: str, generation: int, now: datetime) -> None:
    """End one key immediately. Revoking a revoked key changes nothing."""
    record = _system(repository, api_key_id)
    if not any(g.generation == generation for g in record.generations):
        raise ApiKeyError(f"{api_key_id} has no generation {generation}")
    updated = tuple(
        replace(g, revoked_at=now) if g.generation == generation and g.revoked_at is None else g
        for g in record.generations
    )
    repository.replace(replace(record, generations=updated))
    log_event(
        log, logging.INFO, "api_key.revoked", api_key_id=api_key_id, api_key_generation=generation
    )


def disable(repository: ApiKeyRepository, api_key_id: str) -> None:
    """Stop every key of a calling system. The system and its history stay for the audit trail."""
    record = _system(repository, api_key_id)
    repository.replace(replace(record, status="disabled"))
    log_event(log, logging.INFO, "api_key.disabled", api_key_id=api_key_id)


def find_expiring(
    repository: ApiKeyRepository, now: datetime, policy: KeyPolicy
) -> list[ExpiringKey]:
    """Valid keys of active systems that expire within `warn_days`."""
    horizon = timedelta(days=policy.warn_days)
    return [
        ExpiringKey(r.api_key_id, g.generation, (g.expires_at - now).days)
        for r in repository.list_all()
        if r.status == "active"
        for g in r.generations
        if _is_live(g, now) and g.expires_at - now <= horizon
    ]


def log_expiring(
    repository: ApiKeyRepository, now: datetime, policy: KeyPolicy
) -> list[ExpiringKey]:
    expiring = find_expiring(repository, now, policy)
    for key in expiring:
        log_event(
            log,
            logging.WARNING,
            "api_key.expiring",
            api_key_id=key.api_key_id,
            api_key_generation=key.generation,
            days_left=key.days_left,
        )
    return expiring


# --- the FastAPI dependency ---------------------------------------------------------------------


def _unauthorized() -> ApiError:
    # One response for every failure, so a caller learns nothing about why.
    return ApiError(
        401, "unauthorized", "Invalid or missing API key.", headers={"WWW-Authenticate": "Bearer"}
    )


async def require_api_key(request: Request) -> ApiPrincipal:
    """Reject the request with 401 unless it carries a valid `Authorization: Bearer <key>`.

    Put on the /v1 router (main.new_v1_router), so every route added there is protected by
    default. Reads the repository and clock from `app.state`. The lookup is blocking, so it runs
    in a thread. The result is kept in the request's ASGI scope, so asking twice costs one lookup.
    The scope belongs to this one request by definition, unlike `request.state`, which a server
    could in principle share.
    """
    cached = request.scope.get(_PRINCIPAL_SCOPE_KEY)
    if isinstance(cached, ApiPrincipal):
        return cached
    state = request.app.state
    result = await run_in_threadpool(
        authenticate, request.headers.get("authorization"), state.api_keys, state.clock()
    )
    if isinstance(result, Rejected):
        fields: dict[str, str] = {"reason": result.reason.value}
        if result.api_key_id is not None:
            fields["api_key_id"] = result.api_key_id
        log_event(log, logging.WARNING, "auth.rejected", **fields)
        raise _unauthorized()
    request.scope[_PRINCIPAL_SCOPE_KEY] = result
    bind_log_context(api_key_id=result.api_key_id, api_key_generation=result.generation)
    return result


class AuthFirstRoute(APIRoute):
    """Authenticate before FastAPI reads or validates the request body.

    A router-level dependency alone runs after the body has been parsed, so an unauthenticated
    request with malformed JSON would get 422 instead of 401, and the server would read a body it
    should have refused. This runs the same check first. The dependency stays as well.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def authenticate_first(request: Request) -> Response:
            await require_api_key(request)
            return await handler(request)

        return authenticate_first
