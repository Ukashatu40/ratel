"""Money is whole kobo, never floating point."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

# Strict: rejects 1.5, 1.0 and "100". Use for request/response fields named *_kobo.
Kobo = Annotated[int, Field(strict=True)]
NonNegativeKobo = Annotated[int, Field(strict=True, ge=0)]


def kobo(value: int) -> int:
    """Validate a kobo amount at a boundary (for example a provider callback)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"kobo must be an int, got {type(value).__name__}")
    return value
