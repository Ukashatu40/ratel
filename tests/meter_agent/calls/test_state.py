"""What call mode remembers: written atomically, owner-only; a damaged file starts over."""

from __future__ import annotations

from pathlib import Path

from meter_agent.calls import CallState, OpenCall, StateStore


def test_the_state_survives_a_restart(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "s")
    store.save(
        CallState(41, 12, {"c1": OpenCall("c1", "2348000000001", "2348000000002", 100, 106)})
    )
    loaded = StateStore(tmp_path / "s").load()  # a new object, as after a restart
    assert (loaded.acc_id, loaded.missed_id) == (41, 12)
    assert loaded.open_calls == {"c1": OpenCall("c1", "2348000000001", "2348000000002", 100, 106)}


def test_a_first_run_starts_from_zero(tmp_path: Path) -> None:
    assert StateStore(tmp_path / "s").load() == CallState()


def test_the_folder_and_the_file_are_owner_only(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "s")
    store.save(CallState(1, 1, {}))
    assert (tmp_path / "s").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "s" / "call-state.json").stat().st_mode & 0o777 == 0o600


def test_a_damaged_file_is_set_aside_and_the_agent_starts_from_zero(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "s")
    (tmp_path / "s" / "call-state.json").write_text("{not json")
    assert store.load() == CallState()
    assert (tmp_path / "s" / "call-state.damaged").exists()
    store.save(CallState(5, 5, {}))  # and it can be written again
    assert store.load().acc_id == 5


def test_no_temporary_file_is_left_behind(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "s")
    for n in range(3):
        store.save(CallState(n, n, {}))
    assert [p.name for p in (tmp_path / "s").iterdir()] == ["call-state.json"]
