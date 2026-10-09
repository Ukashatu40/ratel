"""SIM keys: the stored (encrypted) shape, the decrypted holder, and the format rule for Ki/OPc.

Pure: no I/O, no FastAPI, no database driver, no crypto library (docs/adr/0008).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

from pydantic import SecretStr


class Envelope(TypedDict):
    v: int
    alg: str
    kid: str
    nonce: str
    ct: str


# ASSUMPTION, to be confirmed by the project lead and the network team (DECISIONS_PENDING.md):
# Ki and OPc are 128-bit values written as exactly 32 hexadecimal characters. The contract leaves
# the format as TODO. This is the one place that says so.
KEY_HEX_PATTERN = r"[0-9a-fA-F]{32}"


_KEY_HEX_RE = re.compile(KEY_HEX_PATTERN)


def check_key_hex(value: SecretStr) -> SecretStr:
    """Validate a Ki or OPc value. The message never contains the value."""
    if not _KEY_HEX_RE.fullmatch(value.get_secret_value()):
        raise ValueError("must be exactly 32 hexadecimal characters")
    return value


@dataclass(frozen=True, slots=True)
class SimKeys:
    """Decrypted keys for one SIM. Hold briefly, never log, never return from an endpoint."""

    imsi: str
    ki: SecretStr
    opc: SecretStr

    def __repr__(self) -> str:
        return "SimKeys(imsi=<set>, ki=<redacted>, opc=<redacted>)"

    __str__ = __repr__


class SimKeyDocument(TypedDict):
    """The `sim_key` collection. `amf` is an open contract TODO and is deliberately not stored."""

    imsi: str
    ki: Envelope
    opc: Envelope
    created_at: datetime
