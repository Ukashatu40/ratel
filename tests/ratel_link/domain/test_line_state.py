"""A line's stored state and the view that is reported: no keys, UTC times, round trips."""

from datetime import UTC, datetime, timedelta, timezone

from ratel_link.domain.line_state import LineState, LineView
from tests.synthetic import SYNTHETIC_IMSI, SYNTHETIC_MSISDN

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def _state(**changes: object) -> LineState:
    fields: dict[str, object] = {
        "imsi": SYNTHETIC_IMSI,
        "status": "active",
        "updated_at": NOW,
        "msisdn": SYNTHETIC_MSISDN,
        "apns": ("internet", "ims"),
        "ue_ip": "10.45.0.2",
        "speed_ul_mbps": 5.0,
        "speed_dl_mbps": 20.0,
        "data_mode": "full",
    }
    fields.update(changes)
    return LineState(**fields)  # type: ignore[arg-type]


def test_a_state_survives_a_round_trip_through_its_document() -> None:
    state = _state()
    assert LineState.from_document(state.to_document()) == state


def test_the_document_holds_exactly_the_line_fields_and_no_key() -> None:
    assert set(_state().to_document()) == {
        "imsi",
        "status",
        "msisdn",
        "apns",
        "ue_ip",
        "speed_ul_mbps",
        "speed_dl_mbps",
        "data_mode",
        "updated_at",
    }


def test_a_naive_time_read_from_the_database_becomes_utc() -> None:
    doc = _state().to_document()
    doc["updated_at"] = NOW.replace(tzinfo=None)  # what a driver without tz_aware returns
    assert LineState.from_document(doc).updated_at == NOW


def test_a_time_in_another_zone_is_converted_to_utc() -> None:
    doc = _state().to_document()
    doc["updated_at"] = datetime(2026, 10, 11, 13, 0, tzinfo=timezone(timedelta(hours=1)))
    assert LineState.from_document(doc).updated_at == NOW


def test_a_document_with_only_the_required_fields_has_empty_defaults() -> None:
    state = LineState.from_document({"imsi": SYNTHETIC_IMSI, "status": "barred", "updated_at": NOW})
    assert (state.msisdn, state.apns, state.ue_ip, state.data_mode) == (None, (), None, None)


def test_a_provisioned_view_has_no_service_details() -> None:
    assert LineView.provisioned() == LineView(status="provisioned")


def test_the_view_has_no_data_mode_or_time() -> None:
    view = LineView.from_state(_state())
    assert view.status == "active" and view.apns == ("internet", "ims")
    assert not hasattr(view, "data_mode") and not hasattr(view, "updated_at")
