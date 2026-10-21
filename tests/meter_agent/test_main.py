"""Unit tests for meter_agent main and agent loop (M-09)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr, ValidationError

from services.meter_agent.config import Settings
from services.meter_agent.counters import (
    CounterReadError,
    NftablesCounterReader,
    SnapshotCounterReader,
)
from services.meter_agent.main import create_agent, create_counter_reader, main


def _settings(tmp_path: Path, **extra: object) -> Settings:
    return Settings(
        ratel_link_api_key=SecretStr("not-a-real-key-link"),
        api_key=SecretStr("not-a-real-key-meter"),
        spool_dir=tmp_path / "spool",
        interval_seconds=60,
        **extra,  # type: ignore[arg-type]
    )


def test_create_counter_reader_with_snapshot_file(tmp_path: Path) -> None:
    snap = tmp_path / "snap.json"
    snap.write_text('{"nftables": [{"set": {"name": "up"}}, {"set": {"name": "down"}}]}')
    reader = create_counter_reader(_settings(tmp_path, snapshot_path=snap))
    assert isinstance(reader, SnapshotCounterReader)
    assert reader.read() == {}


def test_without_a_snapshot_the_reader_is_the_live_nft_reader(tmp_path: Path) -> None:
    reader = create_counter_reader(_settings(tmp_path, nft_table="ratel_meter"))
    assert isinstance(reader, NftablesCounterReader)


def test_a_missing_key_stops_the_agent_from_starting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("METER_AGENT_API_KEY", "METER_AGENT_RATEL_LINK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None)  # type: ignore[call-arg]
    missing = {e["loc"][0] for e in caught.value.errors()}
    assert missing == {"api_key", "ratel_link_api_key"}


def test_an_unreadable_counter_fails_the_tick_and_posts_nothing(tmp_path: Path) -> None:
    # No snapshot and no nft in this sandbox path: reading must fail loudly, not report "no usage".
    agent = create_agent(_settings(tmp_path, nft_path=tmp_path / "no-such-nft"))
    with pytest.raises(CounterReadError):
        agent.run_once()


def test_main_once_flag(tmp_path: Path) -> None:
    with (
        patch("services.meter_agent.main.Settings") as mock_settings_cls,
        patch("services.meter_agent.main.create_agent") as mock_create_agent,
    ):
        mock_settings = MagicMock()
        mock_settings.mode = "data"
        mock_settings.log_level = "INFO"
        mock_settings.interval_seconds = 300
        mock_settings_cls.return_value = mock_settings

        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        exit_code = main(["--once", "--mode", "data"])
        assert exit_code == 0
        mock_agent.run_once.assert_called_once()
