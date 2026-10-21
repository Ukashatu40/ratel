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
    # No default for either key: a missing key must stop the agent, not send a made-up one.
    ratel_link_api_key: SecretStr
    meter_api_base_url: str = "http://127.0.0.1:18082"
    api_key: SecretStr
    spool_dir: Path = Path("/var/spool/ratel-meter")
    # Read counters from a recorded file instead of running nft (tests and replays only).
    snapshot_path: Path | None = None
    # The counting table that deploy/core-up/ratel-meter.nft loads, and how to read it.
    nft_path: Path = Path("/usr/sbin/nft")
    nft_family: str = "inet"
    nft_table: str = "ratel_meter"
    nft_up_set: str = "up"
    nft_down_set: str = "down"
    nft_timeout_seconds: float = 10.0
    interval_seconds: int = 300
    log_level: str = "INFO"
