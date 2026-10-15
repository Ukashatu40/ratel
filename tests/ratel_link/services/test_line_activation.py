"""Activating a line: what is written, in what order, and what must not happen."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pydantic import SecretStr

from ratel_link.domain.ip_pool import IpPool, PoolExhaustedError
from ratel_link.domain.subscriber import SpeedError, VoiceTemplateError
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.ip_allocation import IpAllocator
from ratel_link.services.line_activation import (
    LineActivationService,
    UnknownSimError,
    VoiceUnavailableError,
)
from ratel_link.services.sim_keys import SimKeyStore
from tests.ratel_link.fakes import (
    FakeClock,
    InMemoryAuditLogRepository,
    InMemoryIpAllocationRepository,
    InMemoryLineStateRepository,
    InMemorySimKeyRepository,
    InMemorySubscriberRepository,
    InMemoryVoiceTemplate,
    StaticKeyProvider,
)
from tests.synthetic import (
    SYNTHETIC_IMS_SESSION,
    SYNTHETIC_IMSI,
    SYNTHETIC_IMSI_2,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_MSISDN,
    SYNTHETIC_MSISDN_2,
    SYNTHETIC_OPC_HEX,
)

BY = "bss-app"


class Env:
    def __init__(
        self, *, voice: bool = True, pool: str = "10.45.0.0/16", import_sims: bool = True
    ) -> None:
        self.clock = FakeClock()
        self.sims = InMemorySimKeyRepository()
        self.subscribers = InMemorySubscriberRepository()
        self.lines = InMemoryLineStateRepository()
        self.ips = InMemoryIpAllocationRepository()
        self.audit = InMemoryAuditLogRepository()
        self.template = InMemoryVoiceTemplate(SYNTHETIC_IMS_SESSION if voice else None)
        self.store = SimKeyStore(self.sims, StaticKeyProvider(), self.clock)
        self.service = LineActivationService(
            self.store,
            self.subscribers,
            self.lines,
            IpAllocator(self.ips, IpPool.from_cidr(pool), self.clock),
            self.template,
            AuditLog(self.audit, self.clock),
            self.clock,
        )
        if import_sims:
            for imsi in (SYNTHETIC_IMSI, SYNTHETIC_IMSI_2):
                self.store.put_if_absent(
                    imsi, SecretStr(SYNTHETIC_KI_HEX), SecretStr(SYNTHETIC_OPC_HEX)
                )

    def activate(self, imsi: str = SYNTHETIC_IMSI, **changes: Any) -> None:
        args: dict[str, Any] = {
            "msisdn": SYNTHETIC_MSISDN,
            "speed_ul_mbps": 5,
            "speed_dl_mbps": 10,
            "voice": True,
            "api_key_id": BY,
        }
        args.update(changes)
        self.service.activate(imsi, **args)

    def document(self, imsi: str = SYNTHETIC_IMSI) -> dict[str, Any]:
        return self.subscribers.documents[imsi]

    def nothing_written(self) -> bool:
        return not (
            self.subscribers.documents or self.lines.states or self.ips.by_ip or self.audit.entries
        )


def test_activation_writes_the_document_the_state_the_address_and_one_audit_entry() -> None:
    env = Env()
    env.activate()
    doc = env.document()
    assert doc["msisdn"] == [SYNTHETIC_MSISDN]
    assert doc["security"]["k"] == SYNTHETIC_KI_HEX.upper()
    assert [s["name"] for s in doc["slice"][0]["session"]] == ["internet", "ims"]
    assert doc["slice"][0]["session"][0]["ue"] == {"ipv4": "10.45.0.2"}

    state = env.lines.states[SYNTHETIC_IMSI]
    assert (state.status, state.ue_ip, state.apns, state.data_mode) == (
        "active",
        "10.45.0.2",
        ("internet", "ims"),
        "full",
    )
    assert (state.speed_ul_mbps, state.speed_dl_mbps) == (5, 10)
    (entry,) = env.audit.entries
    assert (entry["action"], entry["imsi"], entry["api_key_id"], entry["before"]) == (
        "line.activate",
        SYNTHETIC_IMSI,
        BY,
        None,
    )
    assert entry["after"]["status"] == "active"


def test_the_audit_entry_and_the_state_hold_no_key() -> None:
    env = Env()
    env.activate()
    text = repr(env.audit.entries) + repr(env.lines.states)
    for key in (SYNTHETIC_KI_HEX, SYNTHETIC_OPC_HEX):
        assert key not in text and key.upper() not in text


def test_a_line_without_stored_keys_is_refused_and_nothing_is_written() -> None:
    env = Env(import_sims=False)
    with pytest.raises(UnknownSimError):
        env.activate()
    assert env.nothing_written()


def test_a_bad_speed_is_refused_before_anything_is_written() -> None:
    env = Env()
    with pytest.raises(SpeedError):
        env.activate(speed_dl_mbps=1.23456789)
    assert env.nothing_written()


def test_voice_without_a_template_is_refused_before_an_address_is_taken() -> None:
    env = Env(voice=False)
    with pytest.raises(VoiceUnavailableError):
        env.activate(voice=True)
    assert env.nothing_written()


def test_an_unusable_template_file_counts_as_no_voice() -> None:
    env = Env()

    def broken() -> None:
        raise VoiceTemplateError("bad")

    env.template.ims_session = broken  # type: ignore[method-assign,assignment]
    with pytest.raises(VoiceUnavailableError):
        env.activate()
    assert env.nothing_written()


def test_a_line_without_voice_never_needs_the_template() -> None:
    env = Env(voice=False)
    env.activate(voice=False)
    assert [s["name"] for s in env.document()["slice"][0]["session"]] == ["internet"]
    assert env.lines.states[SYNTHETIC_IMSI].apns == ("internet",)


def test_the_voice_session_is_the_template_without_a_fixed_address() -> None:
    env = Env()
    env.activate()
    ims = env.document()["slice"][0]["session"][1]
    assert "ue" not in ims and ims["pcc_rule"] == SYNTHETIC_IMS_SESSION["pcc_rule"]


def test_a_full_pool_refuses_the_line_and_writes_nothing_for_it() -> None:
    env = Env(pool="10.45.0.0/30")  # one usable address: .0 network, .1 reserved, .3 broadcast
    env.activate()
    with pytest.raises(PoolExhaustedError):
        env.activate(SYNTHETIC_IMSI_2, msisdn=SYNTHETIC_MSISDN_2)
    assert SYNTHETIC_IMSI_2 not in env.subscribers.documents
    assert SYNTHETIC_IMSI_2 not in env.lines.states


def test_two_lines_get_different_addresses() -> None:
    env = Env()
    env.activate()
    env.activate(SYNTHETIC_IMSI_2, msisdn=SYNTHETIC_MSISDN_2)
    first = env.lines.states[SYNTHETIC_IMSI].ue_ip
    second = env.lines.states[SYNTHETIC_IMSI_2].ue_ip
    assert first != second


# --- repeating --------------------------------------------------------------------------------


def test_activating_again_with_the_same_settings_changes_nothing() -> None:
    env = Env()
    env.activate()
    document = repr(env.document())
    state, entries = env.lines.states[SYNTHETIC_IMSI], len(env.audit.entries)
    env.clock.advance(seconds=60)
    env.activate()
    assert repr(env.document()) == document
    assert env.lines.states[SYNTHETIC_IMSI] == state  # not even updated_at moves
    assert len(env.audit.entries) == entries == 1


def test_the_same_address_is_kept_across_repeats() -> None:
    env = Env()
    env.activate()
    first = env.lines.states[SYNTHETIC_IMSI].ue_ip
    env.activate()
    env.activate()
    assert env.lines.states[SYNTHETIC_IMSI].ue_ip == first
    assert len(env.ips.by_ip) == 1


def test_different_settings_update_the_owned_fields_and_audit_the_change() -> None:
    env = Env()
    env.activate()
    env.clock.advance(seconds=60)
    env.activate(msisdn=SYNTHETIC_MSISDN_2, speed_dl_mbps=20, voice=False)
    doc = env.document()
    assert doc["msisdn"] == [SYNTHETIC_MSISDN_2]
    assert [s["name"] for s in doc["slice"][0]["session"]] == ["internet"]
    assert doc["slice"][0]["session"][0]["ambr"]["downlink"] == {"value": 20, "unit": 2}
    first, second = env.audit.entries
    assert first["after"]["msisdn"] == second["before"]["msisdn"] == SYNTHETIC_MSISDN
    assert second["after"]["msisdn"] == SYNTHETIC_MSISDN_2


def test_fields_the_hss_wrote_survive_a_later_activation() -> None:
    env = Env()
    env.activate()
    doc = env.document()
    doc["security"]["sqn"] = 123456789012  # written by the HSS, an int64 in the real database
    doc["imeisv"] = ["3540000000000001"]
    doc["mme_host"] = ["mme.example"]
    doc["purge_flag"] = [{"x": 1}]
    env.activate(speed_dl_mbps=25)
    assert doc["security"]["sqn"] == 123456789012
    assert doc["imeisv"] == ["3540000000000001"]
    assert doc["mme_host"] == ["mme.example"]
    assert doc["purge_flag"] == [{"x": 1}]


def test_the_first_activation_creates_the_fields_the_hss_will_fill_as_empty() -> None:
    env = Env()
    env.activate()
    doc = env.document()
    assert (doc["imeisv"], doc["mme_host"], doc["mm_realm"], doc["purge_flag"]) == ([], [], [], [])
    assert "sqn" not in doc["security"]


def test_a_missing_document_is_rewritten_and_recorded_again() -> None:
    env = Env()
    env.activate()
    del env.subscribers.documents[SYNTHETIC_IMSI]  # someone deleted it in the core
    env.activate()
    assert SYNTHETIC_IMSI in env.subscribers.documents
    assert len(env.audit.entries) == 2


def test_reactivating_after_data_was_removed_puts_the_internet_session_back_first() -> None:
    env = Env()
    env.activate()
    env.subscribers.remove_internet(SYNTHETIC_IMSI)
    env.activate()
    assert [s["name"] for s in env.document()["slice"][0]["session"]] == ["internet", "ims"]


# --- logging ----------------------------------------------------------------------------------


def test_logs_name_the_outcome_and_the_caller_but_never_the_line_or_a_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    env = Env()
    env.activate()
    env.activate()
    events = [r.__dict__.get("event") for r in caplog.records]
    assert "line.activate.created" in events and "line.activate.unchanged" in events
    for record in caplog.records:
        text = repr(record.__dict__)
        for secret in (SYNTHETIC_IMSI, SYNTHETIC_MSISDN, SYNTHETIC_KI_HEX, SYNTHETIC_OPC_HEX):
            assert secret not in text and secret.upper() not in text
