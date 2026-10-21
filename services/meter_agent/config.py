"""Configuration settings for the RatelMeter agent (core-up / voice)."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Agent settings loaded from environment or defaults."""

    model_config = SettingsConfigDict(
        env_prefix="METER_AGENT_",
        case_sensitive=False,
    )

    mode: str = "data"  # "data" on core-up, "call" on voice
    ratel_link_base_url: str = "http://127.0.0.1:4010"
    ratel_link_api_key: SecretStr = SecretStr("test-only-not-a-real-key")
    meter_api_base_url: str = "http://127.0.0.1:18082"
    api_key: SecretStr = SecretStr("test-only-not-a-real-key")
    spool_dir: Path = Path("/var/spool/ratel-meter")
    snapshot_path: Path | None = None
    interval_seconds: int = 300
    log_level: str = "INFO"
