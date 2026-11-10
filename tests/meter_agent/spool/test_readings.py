"""The previous readings on disk: round trip, owner-only, and a bad file is never trusted."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from services.meter_agent.domain.records import Reading
from services.meter_agent.spool import MAX_AGE_SECONDS, ReadingStore

NOW = 1_794_700_000


def reading(ip: str = "10.45.128.2", up: int = 100, down: int = 900, at: int = NOW) -> Reading:
    return Reading(ip, up, down, at)


def test_readings_survive_a_new_store_on_the_same_folder(tmp_path: Path) -> None:
    saved = {"10.45.128.2": reading(), "10.45.0.4": reading("10.45.0.4", 5, 6, NOW - 300)}
    ReadingStore(tmp_path / "r").save(saved)
    assert ReadingStore(tmp_path / "r").load(NOW) == saved  # a new object, as after a restart


def test_a_first_run_starts_with_nothing(tmp_path: Path) -> None:
    assert ReadingStore(tmp_path / "r").load(NOW) == {}


def test_the_folder_and_file_are_owner_only(tmp_path: Path) -> None:
    store = ReadingStore(tmp_path / "r")
    store.save({"10.45.128.2": reading()})
    assert (tmp_path / "r").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "r" / "readings.json").stat().st_mode & 0o777 == 0o600


def test_no_temporary_file_is_left_behind(tmp_path: Path) -> None:
    store = ReadingStore(tmp_path / "r")
    for n in range(3):
        store.save({"10.45.128.2": reading(up=n)})
    assert [p.name for p in (tmp_path / "r").iterdir()] == ["readings.json"]


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '{"readings": []}',
        '{"readings": {"10.45.0.2": [1, 2]}}',  # a field is missing
        '{"readings": {"10.45.0.2": [1, -2, 3]}}',  # a negative count
        '{"readings": {"10.45.0.2": [1, "2", 3]}}',
        '{"readings": {"10.45.0.2": [true, 2, 3]}}',  # a boolean is not a count
    ],
)
def test_a_damaged_file_is_set_aside_and_the_agent_starts_from_a_baseline(
    tmp_path: Path, content: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    store = ReadingStore(tmp_path / "r")
    (tmp_path / "r" / "readings.json").write_text(content)
    assert store.load(NOW) == {}
    assert (tmp_path / "r" / "readings.damaged").exists()
    assert not (tmp_path / "r" / "readings.json").exists()
    assert "10.45" not in " ".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    store.save({"10.45.128.2": reading()})  # and it can be written again
    assert store.load(NOW) == {"10.45.128.2": reading()}


def test_readings_older_than_the_hold_on_an_address_are_not_resumed_from(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A released address is held 24 hours; a reading older than that could be charged to the
    wrong line once the address has moved on."""
    caplog.set_level(logging.DEBUG)
    store = ReadingStore(tmp_path / "r")
    fresh = reading("10.45.128.2", at=NOW - 600)
    old = reading("10.45.0.4", at=NOW - MAX_AGE_SECONDS - 1)
    store.save({fresh.ue_ip: fresh, old.ue_ip: old})
    assert store.load(NOW) == {fresh.ue_ip: fresh}
    assert any(r.getMessage() == "meter.readings.expired" for r in caplog.records)
    assert MAX_AGE_SECONDS < 24 * 3600


def test_the_file_holds_only_numbers_and_addresses(tmp_path: Path) -> None:
    store = ReadingStore(tmp_path / "r")
    store.save({"10.45.128.2": reading()})
    data = json.loads((tmp_path / "r" / "readings.json").read_text())
    assert data == {"readings": {"10.45.128.2": [100, 900, NOW]}}  # no IMSI, no number
