"""What a line's status is: stored state, or `provisioned` when only the keys exist."""

from datetime import UTC, datetime

import pytest

from ratel_link.domain.line_state import LineState, LineView
from ratel_link.domain.sim_keys import SimKeyDocument
from ratel_link.services.line_status import LineStatusService
from tests.ratel_link.fakes import InMemoryLineStateRepository, InMemorySimKeyRepository
from tests.synthetic import SYNTHETIC_IMSI, SYNTHETIC_IMSI_2

NOW = datetime(2026, 10, 11, tzinfo=UTC)


def _env() -> tuple[LineStatusService, InMemoryLineStateRepository, InMemorySimKeyRepository]:
    lines, sims = InMemoryLineStateRepository(), InMemorySimKeyRepository()
    return LineStatusService(lines, sims), lines, sims


def _keys(imsi: str) -> SimKeyDocument:
    envelope = {"v": 1, "alg": "AES-256-GCM", "kid": "1", "nonce": "n", "ct": "c"}
    return SimKeyDocument(imsi=imsi, ki=envelope, opc=envelope, created_at=NOW)


def test_an_unknown_line_is_none() -> None:
    service, _, _ = _env()
    assert service.get(SYNTHETIC_IMSI) is None


def test_stored_keys_without_service_are_provisioned() -> None:
    service, _, sims = _env()
    sims.insert_if_absent(_keys(SYNTHETIC_IMSI))
    assert service.get(SYNTHETIC_IMSI) == LineView.provisioned()


def test_a_stored_state_wins_over_the_provisioned_default() -> None:
    service, lines, sims = _env()
    sims.insert_if_absent(_keys(SYNTHETIC_IMSI))
    lines.put(LineState(SYNTHETIC_IMSI, "active", NOW, ue_ip="10.45.0.2", apns=("internet",)))
    view = service.get(SYNTHETIC_IMSI)
    assert view is not None and (view.status, view.ue_ip) == ("active", "10.45.0.2")


def test_a_state_without_stored_keys_is_still_reported() -> None:
    service, lines, _ = _env()
    lines.put(LineState(SYNTHETIC_IMSI, "barred", NOW))
    view = service.get(SYNTHETIC_IMSI)
    assert view is not None and view.status == "barred"


def test_lines_do_not_see_each_other() -> None:
    service, lines, _ = _env()
    lines.put(LineState(SYNTHETIC_IMSI, "active", NOW))
    assert service.get(SYNTHETIC_IMSI_2) is None


@pytest.mark.parametrize(
    "bad", ["", "abc", "62100000000000", "6210000000000012", "62100000000000a"]
)
def test_a_malformed_imsi_is_refused_before_any_lookup(bad: str) -> None:
    service, _, _ = _env()
    with pytest.raises(ValueError):
        service.get(bad)


def test_asking_never_reads_the_keys() -> None:
    service, _, sims = _env()
    sims.insert_if_absent(_keys(SYNTHETIC_IMSI))
    sims.get = lambda imsi: pytest.fail("the status check must not read key documents")  # type: ignore[method-assign]
    assert service.get(SYNTHETIC_IMSI) == LineView.provisioned()
