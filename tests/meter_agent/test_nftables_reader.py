"""The live reader: it runs nft, and every way that can go wrong is an error, never zero usage."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from services.meter_agent.counters import (
    CounterReadError,
    CounterUnavailableError,
    MalformedSnapshotError,
    NftablesCounterReader,
)

REAL_TABLE = (Path(__file__).parent / "fixtures/nft_table_core_up.json").read_text()


class FakeRun:
    """Stands in for subprocess.run and remembers how it was called."""

    def __init__(self, stdout: str = "", returncode: int = 0, raises: Exception | None = None):
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((argv, kwargs))
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "")


def test_it_runs_one_fixed_nft_command_without_a_shell_and_parses_the_answer() -> None:
    run = FakeRun(REAL_TABLE)
    reader = NftablesCounterReader(runner=run, table="ratel_meter")
    readings = reader.read()

    assert readings["192.0.2.2"].bytes_up_total == 102800
    [(argv, kwargs)] = run.calls
    assert argv == ["/usr/sbin/nft", "-j", "list", "table", "inet", "ratel_meter"]
    assert kwargs.get("shell", False) is False
    assert kwargs["timeout"] == 10.0 and kwargs["check"] is False


def test_a_nonzero_exit_is_an_error_not_an_empty_result() -> None:
    reader = NftablesCounterReader(runner=FakeRun(returncode=1))
    with pytest.raises(CounterUnavailableError, match="status 1"):
        reader.read()


@pytest.mark.parametrize(
    "exc",
    [FileNotFoundError(), PermissionError(), subprocess.TimeoutExpired("nft", 10)],
    ids=["missing", "not-allowed", "timeout"],
)
def test_nft_missing_forbidden_or_hanging_is_an_error(exc: Exception) -> None:
    with pytest.raises(CounterUnavailableError):
        NftablesCounterReader(runner=FakeRun(raises=exc)).read()


@pytest.mark.parametrize("stdout", ["", "not json", "{}", '{"nftables": []}'])
def test_output_that_is_not_the_counting_table_is_an_error(stdout: str) -> None:
    with pytest.raises(MalformedSnapshotError):
        NftablesCounterReader(runner=FakeRun(stdout)).read()


def test_both_failures_are_counter_read_errors_so_the_agent_handles_them_alike() -> None:
    assert issubclass(CounterUnavailableError, CounterReadError)
    assert issubclass(MalformedSnapshotError, CounterReadError)


def test_a_custom_set_name_is_used() -> None:
    doc = REAL_TABLE.replace('"name":"up"', '"name":"ue_up"').replace(
        '"name":"down"', '"name":"ue_down"'
    )
    readings = NftablesCounterReader(runner=FakeRun(doc), up_set="ue_up", down_set="ue_down").read()
    assert readings["192.0.2.2"].bytes_up_total == 102800


@pytest.mark.parametrize(
    "kwargs",
    [
        {"family": "bridge"},
        {"table": "x; rm -rf /"},
        {"table": "has space"},
        {"table": ""},
        {"up_set": "-j"},
        {"down_set": "a.b"},
        {"timeout_seconds": 0},
    ],
)
def test_names_that_could_alter_the_command_are_refused_at_start(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        NftablesCounterReader(**kwargs)


def test_no_address_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG")
    NftablesCounterReader(runner=FakeRun(REAL_TABLE)).read()
    assert caplog.records
    assert all("192.0.2" not in r.getMessage() for r in caplog.records)
