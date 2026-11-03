"""Call mode's wiring: its settings, its key, the path it posts to, and the entry point."""

from __future__ import annotations

import stat
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from services.meter_agent.calls import CallAgent
from services.meter_agent.config import CallSettings
from services.meter_agent.ingest import HttpMeterPoster
from services.meter_agent.main import create_call_agent, main


def _script(tmp_path: Path, body: str) -> str:
    path = tmp_path / "export"
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def _settings(tmp_path: Path, **extra: object) -> CallSettings:
    return CallSettings(
        api_key=SecretStr("not-a-real-key-meter"),
        spool_dir=tmp_path / "spool",
        call_export_command=_script(tmp_path, "exit 0"),
        **extra,  # type: ignore[arg-type]
    )


def test_call_mode_needs_the_meter_key_and_no_ratellink_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("METER_AGENT_API_KEY", "METER_AGENT_RATEL_LINK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValidationError) as caught:
        CallSettings(_env_file=None)  # type: ignore[call-arg]
    assert {e["loc"][0] for e in caught.value.errors()} == {
        "api_key"
    }  # a made-up key is never sent
    monkeypatch.setenv("METER_AGENT_API_KEY", "not-a-real-key-meter")
    assert CallSettings(_env_file=None).call_interval_seconds == 60  # type: ignore[call-arg]


def test_the_defaults_are_the_agreed_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METER_AGENT_API_KEY", "not-a-real-key-meter")
    s = CallSettings(_env_file=None)  # type: ignore[call-arg]
    assert (s.call_interval_seconds, s.call_settle_seconds, s.call_open_max_seconds) == (
        60,
        10,
        21_600,
    )
    assert s.call_export_command == "/usr/bin/sudo -n /usr/local/sbin/ratel-call-export"


def test_the_call_agent_keeps_its_batches_apart_from_usage_batches(tmp_path: Path) -> None:
    agent = create_call_agent(_settings(tmp_path))
    assert isinstance(agent, CallAgent)
    assert (tmp_path / "spool" / "calls").is_dir() and (tmp_path / "spool" / "calls-state").is_dir()


def test_the_poster_posts_call_records_to_the_calls_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    poster = HttpMeterPoster(
        "http://api.example.invalid", "not-a-real-key", client=client, path="/v1/calls"
    )
    assert poster({"records": [{"call_id": "c1"}]}) is True
    assert (
        seen[0].url.path == "/v1/calls"
        and seen[0].headers["authorization"] == "Bearer not-a-real-key"
    )
    assert (
        HttpMeterPoster("http://api.example.invalid", "k", client=client)([{"imsi": "x"}]) is True
    )
    assert seen[1].url.path == "/v1/usage"  # data mode is unchanged


def test_once_in_call_mode_exits_non_zero_when_the_export_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("METER_AGENT_API_KEY", "not-a-real-key-meter")
    monkeypatch.setenv("METER_AGENT_SPOOL_DIR", str(tmp_path / "spool"))
    monkeypatch.setenv("METER_AGENT_CALL_EXPORT_COMMAND", _script(tmp_path, "exit 1"))
    assert main(["--mode", "call", "--once"]) == 1


def test_once_in_call_mode_exits_zero_when_there_is_nothing_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("METER_AGENT_API_KEY", "not-a-real-key-meter")
    monkeypatch.setenv("METER_AGENT_SPOOL_DIR", str(tmp_path / "spool"))
    monkeypatch.setenv("METER_AGENT_CALL_EXPORT_COMMAND", _script(tmp_path, "exit 0"))
    assert main(["--mode", "call", "--once"]) == 0
