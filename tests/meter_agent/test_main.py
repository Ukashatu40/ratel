"""Unit tests for meter_agent main and agent loop (M-09)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from services.meter_agent.config import Settings
from services.meter_agent.main import create_agent, create_counter_reader, main


def test_create_counter_reader_with_snapshot_file(tmp_path: Path) -> None:
    snap = tmp_path / "snap.json"
    snap.write_text('{"entries": []}')
    settings = Settings(snapshot_path=snap)
    reader = create_counter_reader(settings)
    assert reader.read() == {}


def test_create_agent_wiring(tmp_path: Path) -> None:
    settings = Settings(
        spool_dir=tmp_path / "test_spool",
        interval_seconds=60,
    )
    agent = create_agent(settings)
    assert agent is not None
    # Running once against empty snapshot produces 0 posts and 0 spools
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
