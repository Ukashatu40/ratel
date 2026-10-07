"""Request models and document shapes for RatelLink's own MongoDB collections.

Ki and OPc are `SecretStr` everywhere they are held in memory: their repr, str and JSON forms
are masked. The decrypted `SimKeys` object has no serialisation path and a redacted repr.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypedDict

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr

from ratel_link.crypto import Envelope

IMSI_PATTERN = r"^[0-9]{15}$"  # same pattern as the contract's Imsi schema
_IMSI_RE = re.compile(IMSI_PATTERN)

# ASSUMPTION, to be confirmed by the project lead and the network team (DECISIONS_PENDING.md):
# Ki and OPc are 128-bit values written as exactly 32 hexadecimal characters. The contract leaves
# the format as TODO. This is the one place that says so.
KEY_HEX_PATTERN = r"[0-9a-fA-F]{32}"
_KEY_HEX_RE = re.compile(KEY_HEX_PATTERN)


# Stable internal id of a calling system, for example `bss-app`. Not secret. A token such as
# `rlk_bss-app.<secret>` does not match, so one cannot be passed off as an id by mistake.
API_KEY_ID_PATTERN = r"[a-z][a-z0-9-]{2,31}"
_API_KEY_ID_RE = re.compile(API_KEY_ID_PATTERN)


def is_api_key_id(value: object) -> bool:
    return isinstance(value, str) and _API_KEY_ID_RE.fullmatch(value) is not None


def is_imsi(value: object) -> bool:
    return isinstance(value, str) and _IMSI_RE.fullmatch(value) is not None


def check_key_hex(value: SecretStr) -> SecretStr:
    """Validate a Ki or OPc value. The message never contains the value."""
    if not _KEY_HEX_RE.fullmatch(value.get_secret_value()):
        raise ValueError("must be exactly 32 hexadecimal characters")
    return value


KeyHex = Annotated[SecretStr, AfterValidator(check_key_hex)]


class SimImport(BaseModel):
    """Body of POST /v1/sims (contract: SimImport)."""

    # hide_input_in_errors: a validation error must never echo a rejected Ki or OPc.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    imsi: str = Field(pattern=IMSI_PATTERN)
    ki: KeyHex
    opc: KeyHex


@dataclass(frozen=True, slots=True)
class SimKeys:
    """Decrypted keys for one SIM. Hold briefly, never log, never return from an endpoint."""

    imsi: str
    ki: SecretStr
    opc: SecretStr

    def __repr__(self) -> str:
        return "SimKeys(imsi=<set>, ki=<redacted>, opc=<redacted>)"

    __str__ = __repr__


class AuditEntry(TypedDict):
    """The `audit_log` collection (Build Plan: at, api_key_id, action, imsi, before, after)."""

    at: datetime
    api_key_id: str
    action: str
    imsi: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class SimKeyDocument(TypedDict):
    """The `sim_key` collection. `amf` is an open contract TODO and is deliberately not stored."""

    imsi: str
    ki: Envelope
    opc: Envelope
    created_at: datetime


# --- API keys (docs/adr/0007) -------------------------------------------------------------------

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
