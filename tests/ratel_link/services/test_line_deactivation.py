"""Deactivating a line: the document goes, the keys and the held address stay with RatelLink."""

from __future__ import annotations

import logging

import pytest

from ratel_link.domain.ip_pool import IpPool
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.ip_allocation import IpAllocator
from ratel_link.services.line_activation import UnknownSimError
from ratel_link.services.line_deactivation import LineDeactivationService
from tests.ratel_link.services.test_line_activation import BY
from tests.ratel_link.services.test_line_activation import Env as ActivationEnv
from tests.synthetic import (
    SYNTHETIC_IMSI,
    SYNTHETIC_IMSI_2,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_MSISDN_2,
    SYNTHETIC_OPC_HEX,
)

SYNTHETIC_IMSI_UNKNOWN = "621000000000099"

REASON = "customer asked to cancel"


class Env:
    """An activated line (through the real activation service) plus the deactivation service."""

    def __init__(self, *, activate: bool = True) -> None:
        self.base = ActivationEnv()
        if activate:
            self.base.activate()
        self.service = LineDeactivationService(
            self.base.sims,
            self.base.subscribers,
            self.base.lines,
            IpAllocator(self.base.ips, IpPool.from_cidr("10.45.0.0/16"), self.base.clock),
            AuditLog(self.base.audit, self.base.clock),
            self.base.clock,
        )

    def deactivate(self, imsi: str = SYNTHETIC_IMSI) -> None:
        self.service.deactivate(imsi, REASON, BY)


def test_deactivation_deletes_the_document_and_puts_the_line_back_to_provisioned() -> None:
    env = Env()
    env.deactivate()
    assert SYNTHETIC_IMSI not in env.base.subscribers.documents
    state = env.base.lines.states[SYNTHETIC_IMSI]
    assert state.status == "provisioned"
    assert (state.msisdn, state.ue_ip, state.apns, state.data_mode) == (None, None, (), None)
    assert (state.speed_ul_mbps, state.speed_dl_mbps) == (None, None)


def test_only_the_deactivated_lines_document_is_deleted() -> None:
    env = Env()
    env.base.activate(SYNTHETIC_IMSI_2, msisdn=SYNTHETIC_MSISDN_2)
    env.deactivate()
    assert list(env.base.subscribers.documents) == [SYNTHETIC_IMSI_2]
    assert env.base.lines.states[SYNTHETIC_IMSI_2].status == "active"


def test_the_stored_keys_are_kept_so_the_line_can_be_activated_again() -> None:
    env = Env()
    env.deactivate()
    assert env.base.sims.exists(SYNTHETIC_IMSI)
    env.base.activate()
    doc = env.base.document()
    assert doc["security"]["k"] == SYNTHETIC_KI_HEX.upper()
    assert doc["security"]["opc"] == SYNTHETIC_OPC_HEX.upper()
    assert env.base.lines.states[SYNTHETIC_IMSI].status == "active"


def test_the_address_is_released_and_the_same_line_gets_it_back() -> None:
    env = Env()
    first = env.base.lines.states[SYNTHETIC_IMSI].ue_ip
    env.deactivate()
    held = env.base.ips.find_by_imsi(SYNTHETIC_IMSI)
    assert held is not None and held.state == "released" and held.ue_ip == first
    env.base.activate()
    assert env.base.lines.states[SYNTHETIC_IMSI].ue_ip == first


def test_another_line_does_not_get_the_address_while_it_is_held() -> None:
    env = Env()
    first = env.base.lines.states[SYNTHETIC_IMSI].ue_ip
    env.deactivate()
    env.base.activate(SYNTHETIC_IMSI_2, msisdn=SYNTHETIC_MSISDN_2)
    assert env.base.lines.states[SYNTHETIC_IMSI_2].ue_ip != first


def test_one_audit_entry_records_before_after_and_the_reason() -> None:
    env = Env()
    env.deactivate()
    entry = env.base.audit.entries[-1]
    assert (entry["action"], entry["imsi"], entry["api_key_id"]) == (
        "line.deactivate",
        SYNTHETIC_IMSI,
        BY,
    )
    assert entry["before"]["status"] == "active" and entry["before"]["ue_ip"] == "10.45.0.2"
    assert entry["after"]["status"] == "provisioned" and entry["after"]["reason"] == REASON
    assert len(env.base.audit.entries) == 2  # the activation and this


def test_deactivating_twice_changes_and_records_nothing_the_second_time() -> None:
    env = Env()
    env.deactivate()
    audit, state = list(env.base.audit.entries), env.base.lines.states[SYNTHETIC_IMSI]
    env.deactivate()
    assert env.base.audit.entries == audit
    assert env.base.lines.states[SYNTHETIC_IMSI] == state


def test_a_sim_that_was_never_activated_is_a_quiet_no_op() -> None:
    env = Env(activate=False)
    env.deactivate()
    assert env.base.lines.states == {} and env.base.audit.entries == []
    assert env.base.subscribers.documents == {}


def test_an_unknown_sim_is_refused_and_nothing_is_written() -> None:
    env = Env(activate=False)
    with pytest.raises(UnknownSimError):
        env.service.deactivate(SYNTHETIC_IMSI_UNKNOWN, REASON, BY)
    assert env.base.lines.states == {} and env.base.audit.entries == []


def test_a_document_left_behind_is_removed_on_the_next_call() -> None:
    env = Env()
    env.deactivate()
    # drift: something wrote the document again without RatelLink recording it
    env.base.subscribers.documents[SYNTHETIC_IMSI] = {"imsi": SYNTHETIC_IMSI}
    env.deactivate()
    assert SYNTHETIC_IMSI not in env.base.subscribers.documents


def test_a_failed_request_can_be_sent_again() -> None:
    """The document is gone but the state still says active: the repeat finishes the job."""
    env = Env()
    env.base.subscribers.remove_line(SYNTHETIC_IMSI)
    env.deactivate()
    assert env.base.lines.states[SYNTHETIC_IMSI].status == "provisioned"
    assert env.base.audit.entries[-1]["action"] == "line.deactivate"


def test_the_entry_and_the_state_hold_no_key() -> None:
    env = Env()
    env.deactivate()
    text = repr(env.base.audit.entries) + repr(env.base.lines.states)
    for key in (SYNTHETIC_KI_HEX, SYNTHETIC_OPC_HEX):
        assert key not in text and key.upper() not in text


def test_the_log_carries_no_imsi_and_no_reason(caplog: pytest.LogCaptureFixture) -> None:
    env = Env()
    with caplog.at_level(logging.DEBUG):
        env.deactivate()
    text = caplog.text
    assert SYNTHETIC_IMSI not in text and REASON not in text
    assert "line.deactivate.done" in text
