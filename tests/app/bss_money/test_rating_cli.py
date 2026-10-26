"""The rating job's exit code is what a timer sees: 0 fine, 1 a line failed, 2 could not run."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Line
from app.bss_money.models.rating import UsageRating
from app.bss_money.rating_cli import main
from app.db import Base
from tests.app.bss_money.rating_data import add_bucket, add_usage, seed_line


def _database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, key: bool = True) -> str:
    url = f"sqlite+pysqlite:///{tmp_path / 'bss.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s, s.begin():
        line = seed_line(s)
        # Valid for as long as this test will ever run: the CLI judges against the real clock.
        add_bucket(s, line, 1_000, expires=datetime(2100, 1, 1, tzinfo=UTC))
        add_usage(s, line, 3, 4)
    engine.dispose()
    monkeypatch.setenv("DATABASE_URL", url)
    if key:
        monkeypatch.setenv("RATEL_LINK_API_KEY", "placeholder-key")
    else:
        monkeypatch.delenv("RATEL_LINK_API_KEY", raising=False)
    return url


def test_exit_0_and_the_usage_is_rated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = _database(tmp_path, monkeypatch)

    assert main([]) == 0

    engine = create_engine(url)
    with Session(engine) as s:
        assert s.scalar(select(UsageRating.deducted_bytes)) == 7
        assert s.scalar(select(Line.state)) == "active"  # 993 bytes are left
    engine.dispose()


def test_exit_2_without_a_ratellink_key_and_nothing_is_rated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    url = _database(tmp_path, monkeypatch, key=False)

    assert main([]) == 2

    engine = create_engine(url)
    with Session(engine) as s:
        assert s.scalar(select(UsageRating.usage_record_id)) is None
    engine.dispose()


def test_exit_2_when_the_database_cannot_be_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'missing' / 'x.db'}")
    monkeypatch.setenv("RATEL_LINK_API_KEY", "placeholder-key")

    assert main([]) == 2
    assert "missing" not in capsys.readouterr().err  # no path, host or user in the output
