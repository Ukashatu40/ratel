"""Staff authentication for the BSS routes (M-26).

One bearer key per deployment, from Settings.bss_api_key. The key is compared
in constant time. A missing or wrong key is 401 before the route reads its body.

Roles are TODO(PRD): the principal names no role yet. When the PRD decides the
role model, this becomes a per-staff key with a role on it (see ratel_link's
api_key model for the shape).
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.bss_lines.api.deps import get_settings
from app.config import Settings


@dataclass(frozen=True)
class StaffPrincipal:
    """The caller of a state-changing route."""

    actor: str


def require_staff(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> StaffPrincipal:
    """Refuse the request unless it carries the configured bearer key."""
    configured = settings.bss_api_key_value
    if configured is None:
        raise HTTPException(status_code=503, detail="BSS API key is not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    presented = authorization[7:]
    if not hmac.compare_digest(presented.encode(), configured.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    return StaffPrincipal(actor="staff")
