"""Changing a line's data: only the internet session moves, and calling never does."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from ratel_link.domain.line_state import LineState
from ratel_link.domain.subscriber import SpeedError
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.data_mode import (
    DataModeService,
    NoActiveLineError,
    SubscriberMissingError,
)
from tests.ratel_link.fakes import (
    FakeClock,
    InMemoryAuditLogRepository,
    InMemoryLineStateRepository,
    InMemorySubscriberRepository,
)
from tests.ratel_link.services.test_line_activation import Env as ActivationEnv
from tests.synthetic import SYNTHETIC_IMSI, SYNTHETIC_IMSI_2

BY = "bss-app"


class Env:
    """An activated line (through the real activation service) plus the data service."""

    def __init__(self) -> None:
        self.base = ActivationEnv()
        self.base.activate()
        self.clock: FakeClock = self.base.clock
        self.service = DataModeService(
            self.base.subscribers,
            self.base.lines,
            AuditLog(self.base.audit, self.clock),
            self.clock,
        )

    @property
    def sessions(self) -> list[dict[str, Any]]:
        return self.base.subscribers.documents[SYNTHETIC_IMSI]["slice"][0]["session"]  # type: ignore[no-any-return]

    @property
    def state(self) -> LineState:
        return self.base.lines.states[SYNTHETIC_IMSI]

    def set(self, mode: str, ul: float | None = 1, dl: float | None = 2) -> None:
        self.service.set_mode(SYNTHETIC_IMSI, mode, ul, dl, BY)  # type: ignore[arg-type]


def test_slow_sets_the_internet_speed_in_the_session_and_at_the_top() -> None:
    env = Env()
    env.set("slow", 0.128, 0.256)
    expected = {"downlink": {"value": 256, "unit": 1}, "uplink": {"value": 128, "unit": 1}}
    assert env.sessions[0]["ambr"] == expected
    assert env.base.subscribers.documents[SYNTHETIC_IMSI]["ambr"] == expected
    assert env.state.data_mode == "slow" and (env.state.speed_ul_mbps, env.state.speed_dl_mbps) == (
        0.128,
        0.256,
    )


def test_the_voice_session_is_untouched_by_every_data_change() -> None:
    env = Env()
    voice = copy.deepcopy(env.sessions[1])
    env.set("slow", 0.1, 0.1)
    assert env.sessions[1] == voice
    env.set("off")
    assert env.sessions == [voice]
    env.set("full", 5, 10)
    assert env.sessions[1] == voice


def test_off_removes_only_the_internet_session() -> None:
    env = Env()
    env.set("off", None, None)
    assert [s["name"] for s in env.sessions] == ["ims"]
    assert env.state.data_mode == "off" and env.state.apns == ("ims",)


def test_turning_data_back_on_puts_the_internet_session_first_with_its_address() -> None:
    env = Env()
    env.set("off", None, None)
    env.set("full", 5, 10)
    assert [s["name"] for s in env.sessions] == ["internet", "ims"]
    assert env.sessions[0]["ue"] == {"ipv4": env.state.ue_ip}
    assert env.sessions[0]["ambr"]["downlink"] == {"value": 10, "unit": 2}
    assert env.state.apns == ("internet", "ims") and env.state.data_mode == "full"


def test_off_ignores_any_speeds() -> None:
    env = Env()
    env.set("off", 1.23456789, -5)  # not validated: off does not use them


def test_full_and_slow_need_both_speeds() -> None:
    env = Env()
    for mode in ("full", "slow"):
        with pytest.raises(SpeedError):
            env.set(mode, None, 1)
        with pytest.raises(SpeedError):
            env.set(mode, 1, None)
    assert env.sessions[0]["ambr"]["downlink"] == {"value": 10, "unit": 2}  # unchanged


def test_a_speed_that_cannot_be_written_whole_is_refused_and_nothing_changes() -> None:
    env = Env()
    before = repr(env.base.subscribers.documents)
    with pytest.raises(SpeedError):
        env.set("slow", 1.23456789, 1)
    assert repr(env.base.subscribers.documents) == before
    assert len(env.base.audit.entries) == 1


def test_repeating_a_change_records_and_audits_it_once() -> None:
    env = Env()
    env.set("slow", 0.5, 0.5)
    state, entries = env.state, len(env.base.audit.entries)
    env.clock.advance(seconds=30)
    env.set("slow", 0.5, 0.5)
    assert env.state == state and len(env.base.audit.entries) == entries == 2


def test_removing_the_internet_session_twice_is_harmless() -> None:
    env = Env()
    env.set("off", None, None)
    env.set("off", None, None)
    assert [s["name"] for s in env.sessions] == ["ims"]
    assert len(env.base.audit.entries) == 2  # activate, then the one real change


def test_every_change_is_audited_with_the_caller_and_the_before_and_after() -> None:
    env = Env()
    env.set("off", None, None)
    entry = env.base.audit.entries[-1]
    assert (entry["action"], entry["api_key_id"]) == ("line.data", BY)
    assert entry["before"]["data_mode"] == "full" and entry["after"]["data_mode"] == "off"
    assert entry["before"]["apns"] == ["internet", "ims"] and entry["after"]["apns"] == ["ims"]


def test_fields_the_hss_wrote_survive_a_data_change() -> None:
    env = Env()
    doc = env.base.subscribers.documents[SYNTHETIC_IMSI]
    doc["security"]["sqn"] = 42
    doc["imeisv"] = ["3540000000000001"]
    env.set("slow", 1, 1)
    env.set("off", None, None)
    env.set("full", 1, 1)
    assert doc["security"]["sqn"] == 42 and doc["imeisv"] == ["3540000000000001"]


def test_the_keys_are_never_read_by_a_data_change() -> None:
    env = Env()

    def forbidden(*_: Any, **__: Any) -> Any:
        raise AssertionError("a data change must not touch the keys")

    env.base.sims.get = forbidden  # type: ignore[method-assign]
    env.set("slow", 1, 1)


def test_a_line_that_was_never_activated_is_refused() -> None:
    env = Env()
    with pytest.raises(NoActiveLineError):
        env.service.set_mode(SYNTHETIC_IMSI_2, "slow", 1, 1, BY)


def test_a_line_that_is_not_active_is_refused() -> None:
    env = Env()
    env.base.lines.put(
        LineState(SYNTHETIC_IMSI_2, "barred", env.clock(), ue_ip="10.45.0.9", apns=("internet",))
    )
    with pytest.raises(NoActiveLineError):
        env.service.set_mode(SYNTHETIC_IMSI_2, "off", None, None, BY)


def test_a_missing_subscriber_document_is_reported_and_nothing_is_recorded() -> None:
    env = Env()
    entries, state = len(env.base.audit.entries), env.state
    del env.base.subscribers.documents[SYNTHETIC_IMSI]
    for mode in ("slow", "off"):
        with pytest.raises(SubscriberMissingError):
            env.set(mode, 1, 1)
    assert env.state == state and len(env.base.audit.entries) == entries


def test_a_standalone_service_works_on_fakes_alone() -> None:
    lines, subs = InMemoryLineStateRepository(), InMemorySubscriberRepository()
    service = DataModeService(subs, lines, AuditLog(InMemoryAuditLogRepository()))
    with pytest.raises(NoActiveLineError):
        service.set_mode(SYNTHETIC_IMSI, "off", None, None, BY)
