"""Shared FastAPI dependencies for the bss_lines routes."""

from __future__ import annotations

from fastapi import Request

from app.config import Settings


def get_settings(request: Request) -> Settings:
    """Application settings, set on app.state by create_app."""
    return request.app.state.settings  # type: ignore[no-any-return]
