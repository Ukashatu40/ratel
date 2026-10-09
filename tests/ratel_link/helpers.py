"""Helpers shared by the RatelLink tests: a repository with a clock, and a registered system."""

from __future__ import annotations

from typing import Any

from ratel_link.services.api_key_admin import KeyPolicy, create_system
from ratel_link.services.authentication import authenticate
from tests.ratel_link.fakes import FakeClock, InMemoryApiKeyRepository

POLICY = KeyPolicy()  # 90 days, 7 days overlap, 14 days warning


def setup_repo() -> tuple[InMemoryApiKeyRepository, FakeClock]:
    return InMemoryApiKeyRepository(), FakeClock()


def register_system(
    repo: InMemoryApiKeyRepository, clock: FakeClock, api_key_id: str = "bss-app"
) -> str:
    """Create a calling system and return its first key."""
    return create_system(repo, api_key_id, "RatelBSS", clock(), POLICY)


def authenticate_with(token: str, repo: InMemoryApiKeyRepository, clock: FakeClock) -> Any:
    return authenticate(f"Bearer {token}", repo, clock())
