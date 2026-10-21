"""API layer for the meter_api module.

Defines HTTP routes and schemas according to contracts/openapi.yaml.
"""

from __future__ import annotations

from .routes import router

__all__ = ["router"]
