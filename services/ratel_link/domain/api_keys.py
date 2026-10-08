"""API keys: a calling system and its key generations (docs/adr/0007). Pure, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

ApiKeyStatus = Literal["active", "disabled"]


def _utc(value: datetime) -> datetime:
    # A MongoDB client that is not tz_aware returns naive datetimes. They are always UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ApiKeyGeneration:
    """One key of a calling system. Only its one-way hash is kept, never the key."""

    generation: int
    secret_hash: str = field(repr=False)
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "secret_hash": self.secret_hash,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
        }

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> ApiKeyGeneration:
        revoked = doc["revoked_at"]
        return cls(
            generation=doc["generation"],
            secret_hash=doc["secret_hash"],
            created_at=_utc(doc["created_at"]),
            expires_at=_utc(doc["expires_at"]),
            revoked_at=None if revoked is None else _utc(revoked),
        )


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    """One calling system (for example `bss-app`) and its key generations."""

    api_key_id: str
    system_name: str
    status: ApiKeyStatus
    created_at: datetime
    generations: tuple[ApiKeyGeneration, ...] = ()

    def to_document(self) -> dict[str, Any]:
        return {
            "api_key_id": self.api_key_id,
            "system_name": self.system_name,
            "status": self.status,
            "generations": [g.to_document() for g in self.generations],
            "created_at": self.created_at,
        }

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> ApiKeyRecord:
        return cls(
            api_key_id=doc["api_key_id"],
            system_name=doc["system_name"],
            status=doc["status"],
            created_at=_utc(doc["created_at"]),
            generations=tuple(ApiKeyGeneration.from_document(g) for g in doc["generations"]),
        )
