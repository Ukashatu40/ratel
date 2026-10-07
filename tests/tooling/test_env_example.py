"""`.env.example` must load into both Settings classes, document every setting, hold placeholders
only, and match docs/ENVIRONMENTS.md. A new setting without a documented example fails here."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from dotenv import dotenv_values

from app.config import Settings as AppSettings
from ratel_link.config import Settings as LinkSettings

ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = {k: v or "" for k, v in dotenv_values(ROOT / ".env.example").items()}
ENVIRONMENTS_MD = (ROOT / "docs" / "ENVIRONMENTS.md").read_text()


@pytest.fixture
def example_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in ENV_EXAMPLE.items():
        monkeypatch.setenv(name, value)


def test_example_loads_into_the_ratellink_settings(example_env: None) -> None:
    s = LinkSettings()
    assert s.ratel_env == "local"
    assert s.ratel_link_key_id == "1"
    assert (
        s.ratel_link_api_key_max_age_days,
        s.ratel_link_api_key_rotation_overlap_days,
        s.ratel_link_api_key_expiry_warn_days,
    ) == (90, 7, 14)


def test_example_loads_into_the_app_settings(example_env: None) -> None:
    s = AppSettings()
    assert s.ratel_env == "local"
    assert s.ratel_link_api_key is not None


@pytest.mark.parametrize("settings", [LinkSettings, AppSettings], ids=["ratel_link", "app"])
def test_every_setting_is_documented_in_the_example_and_in_environments_md(
    settings: type,
) -> None:
    for field in settings.model_fields:  # type: ignore[attr-defined]
        name = field.upper()
        assert name in ENV_EXAMPLE, f"{name} is missing from .env.example"
        assert f"`{name}`" in ENVIRONMENTS_MD, f"{name} is missing from docs/ENVIRONMENTS.md"


def test_the_example_holds_placeholders_only() -> None:
    assert not any("rlk_" in v for v in ENV_EXAMPLE.values()), "an API key is in .env.example"
    for name, value in ENV_EXAMPLE.items():
        if re.search(r"KEY|SECRET|PASSWORD|TOKEN", name) and not name.endswith(
            ("_FILE", "_ID", "_DAYS")
        ):
            assert value == "CHANGE_ME", f"{name} must be the placeholder CHANGE_ME"
    # The encryption key is a path to a file outside the repo, never a value.
    assert ENV_EXAMPLE["RATEL_LINK_KEY_FILE"].startswith("/path/outside/repo/")
