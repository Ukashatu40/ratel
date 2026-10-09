"""Key administration: create a calling system, rotate, revoke, disable, warn before expiry.

Used by the admin CLI. A new key is returned to the caller once and never logged or stored
(docs/adr/0007).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from common.logging import log_event
from ratel_link.config import MAX_API_KEY_AGE_DAYS, Settings
from ratel_link.domain.api_keys import ApiKeyGeneration, ApiKeyRecord
from ratel_link.domain.identifiers import is_api_key_id
from ratel_link.repositories.ports import ApiKeyRepository
from ratel_link.security.api_key_tokens import generate_token

log = logging.getLogger("ratel.link.auth")


_SYSTEM_NAME_MAX = 64


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
