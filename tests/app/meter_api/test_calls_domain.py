"""The call record's rules (docs/call-record-agreement.md, sections 6 and 11). Synthetic data."""

from __future__ import annotations

import pytest

from app.meter_api.domain import END_REASONS, CallRecord

T = 1_794_700_000


def call(**changes: object) -> CallRecord:
    values: dict[str, object] = {
        "call_id": "call-1@example.invalid",
        "from_msisdn": "2340000000001",
        "to_msisdn": "2340000000002",
        "started_at": T,
        "answered_at": T + 6,
        "ended_at": T + 66,
        "end_reason": "completed",
    }
    return CallRecord(**{**values, **changes})  # type: ignore[arg-type]


def test_an_answered_call_that_ended_normally_is_valid() -> None:
    call().validate()


@pytest.mark.parametrize("reason", [r for r in END_REASONS if r != "completed"])
def test_a_call_that_was_never_answered_is_valid_with_any_other_reason(reason: str) -> None:
    call(answered_at=None, ended_at=T + 11, end_reason=reason).validate()


def test_the_reasons_are_the_agreements() -> None:
    assert END_REASONS == (
        "completed",
        "cancelled",
        "declined",
        "not_answered",
        "unavailable",
        "failed",
    )


@pytest.mark.parametrize(
    ("changes", "complaint"),
    [
        ({"end_reason": "busy"}, "end_reason"),
        ({"end_reason": "completed", "answered_at": None}, "completed exactly when"),
        ({"end_reason": "failed"}, "completed exactly when"),  # answered, but not "completed"
        ({"started_at": -1, "ended_at": 5}, "non-negative"),
        ({"call_id": ""}, "call_id"),
        ({"call_id": "has space"}, "call_id"),
        ({"call_id": "x" * 129}, "call_id"),
        ({"from_msisdn": ""}, "number"),
        ({"to_msisdn": "2340000000 02"}, "number"),
        ({"to_msisdn": "23400000000\u00a002"}, "number"),  # a non-breaking space is a space too
        ({"call_id": "caf\u00e9"}, "call_id"),  # visible ASCII only, as the contract says
        ({"to_msisdn": "2" * 33}, "number"),
    ],
)
def test_a_call_that_breaks_a_rule_is_refused(changes: dict[str, object], complaint: str) -> None:
    with pytest.raises(ValueError, match=complaint):
        call(**changes).validate()


def test_a_number_that_matched_no_rule_is_still_accepted_as_it_came() -> None:
    call(to_msisdn="+2340000000002").validate()  # the agreement: never drop the call


def test_the_error_never_repeats_a_number_or_a_call_id() -> None:
    with pytest.raises(ValueError) as caught:
        call(end_reason="busy").validate()
    for value in ("2340000000001", "2340000000002", "call-1@example.invalid"):
        assert value not in str(caught.value)


def test_a_call_whose_times_are_in_order_is_left_alone() -> None:
    record = call()
    assert record.normalised() is record


@pytest.mark.parametrize(
    ("changes", "answered", "ended"),
    [
        (
            {"ended_at": T - 5, "answered_at": None, "end_reason": "failed"},
            None,
            T,
        ),  # ends before it starts
        ({"answered_at": T - 1}, T, T + 66),  # answered before it began
        ({"answered_at": T + 99}, T + 66, T + 66),  # answered after it ended
        ({"ended_at": T - 5}, T, T),  # ends before it starts, and was answered
    ],
)
def test_times_out_of_order_are_put_in_order_not_refused(
    changes: dict[str, object], answered: int | None, ended: int
) -> None:
    record = call(**changes)
    record.validate()  # not refused
    fixed = record.normalised()
    assert (fixed.started_at, fixed.answered_at, fixed.ended_at) == (T, answered, ended)
    assert (fixed.call_id, fixed.from_msisdn, fixed.to_msisdn, fixed.end_reason) == (
        record.call_id, record.from_msisdn, record.to_msisdn, record.end_reason,
    )  # fmt: skip
