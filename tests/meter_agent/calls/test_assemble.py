"""Joining rows into call records: every case the lab produced on 2026-10-30 and 2026-11-02."""

from __future__ import annotations

import pytest

from meter_agent.calls import CallRow, OpenCall, assemble, normalise_msisdn, reason_for

T = 1_794_700_000
NOW = T + 10_000
A, B = "2348000000001", "08000000002"  # as dialled


def row(table: str, row_id: int, method: str, code: int, call: str, *, time: int, start: int = 0,
        frm: str = A, to: str = B) -> CallRow:  # fmt: skip
    return CallRow(table, row_id, method, code, call, "tag", frm, to, time, start)


def run(rows: list[CallRow], open_calls: dict[str, OpenCall] | None = None, **kw: int):
    return assemble(rows, open_calls or {}, now=kw.pop("now", NOW), open_max_seconds=21_600, **kw)


def test_an_answered_call_with_a_hang_up_is_one_completed_record_from_both_legs() -> None:
    rows = [
        row("acc", 1, "INVITE", 200, "c1", time=T + 6, start=T),
        row("acc", 2, "INVITE", 200, "c1", time=T + 6, start=T),  # the second leg
        row("acc", 3, "BYE", 200, "c1", time=T + 66, start=T + 66),
        row("acc", 4, "BYE", 200, "c1", time=T + 66, start=T + 66),
    ]
    done = run(rows)
    assert done.finished == [
        {
            "call_id": "c1",
            "from_msisdn": A,
            "to_msisdn": "2348000000002",  # 0 and ten digits, put in the stored form
            "started_at": T,
            "answered_at": T + 6,
            "ended_at": T + 66,
            "end_reason": "completed",
        }
    ]
    assert done.open_calls == {} and done.acc_id == 4


def test_the_first_hang_up_decides_when_the_call_ended() -> None:
    rows = [
        row("acc", 1, "INVITE", 200, "c1", time=T + 6, start=T),
        row("acc", 2, "BYE", 200, "c1", time=T + 60),
        row("acc", 3, "BYE", 200, "c1", time=T + 61),  # the other phone's, a second later
    ]
    assert run(rows).finished[0]["ended_at"] == T + 60


def test_an_answered_call_stays_open_until_its_bye_arrives_in_a_later_pass() -> None:
    first = run([row("acc", 1, "INVITE", 200, "c1", time=T + 6, start=T)])
    assert first.finished == [] and set(first.open_calls) == {"c1"}
    second = run(
        [row("acc", 2, "BYE", 200, "c1", time=T + 66)], first.open_calls, acc_id=first.acc_id
    )
    assert [r["end_reason"] for r in second.finished] == ["completed"]
    assert second.finished[0]["started_at"] == T and second.finished[0]["answered_at"] == T + 6
    assert second.open_calls == {}


def test_an_answered_call_with_no_bye_is_dropped_after_the_limit_and_never_posted() -> None:
    start = run([row("acc", 1, "INVITE", 200, "c1", time=T + 6, start=T)], now=T + 100)
    later = run([], start.open_calls, now=T + 6 + 21_601)
    assert later.finished == [] and later.open_calls == {} and later.stale_dropped == 1
    kept = run([], start.open_calls, now=T + 6 + 21_599)
    assert set(kept.open_calls) == {"c1"} and kept.stale_dropped == 0


def test_a_bye_for_a_call_never_seen_answered_is_counted_and_ignored() -> None:
    done = run([row("acc", 5, "BYE", 200, "ghost", time=T)])
    assert done.finished == [] and done.orphan_byes == 1


@pytest.mark.parametrize(
    ("codes", "reason"),
    [
        ([487], "cancelled"),  # the caller gave up, also after a 3 minute ring
        ([603], "declined"),
        ([486], "not_answered"),  # busy, or a phone that refuses with the busy code
        ([408, 500], "unavailable"),  # airplane mode: both rows, same second
        ([500], "unavailable"),
        ([404], "unavailable"),
        ([480], "unavailable"),
        ([503], "failed"),
        ([487, 408], "cancelled"),
    ],
)
def test_a_call_never_answered_takes_its_reason_from_the_codes_of_its_failed_rows(
    codes: list[int], reason: str
) -> None:
    rows = [
        row("missed", i + 1, "INVITE", code, "c9", time=T + 3, start=T)
        for i, code in enumerate(codes)
    ]
    [record] = run(rows).finished
    assert record["end_reason"] == reason and record["answered_at"] is None
    assert record["started_at"] == T and record["ended_at"] == T + 3
    assert reason_for(set(codes)) == reason


def test_a_failed_branch_of_a_call_that_was_answered_does_not_undo_the_answer() -> None:
    rows = [
        row("acc", 1, "INVITE", 200, "c1", time=T + 6, start=T),
        row("missed", 1, "INVITE", 487, "c1", time=T + 6, start=T),  # the other fork, cancelled
        row("acc", 2, "BYE", 200, "c1", time=T + 66),
    ]
    [record] = run(rows).finished
    assert record["end_reason"] == "completed"


def test_a_row_from_before_start_ts_was_recorded_uses_its_own_time() -> None:
    [record] = run([row("missed", 1, "INVITE", 603, "old", time=T + 11, start=0)]).finished
    assert record["started_at"] == T + 11


def test_the_ring_time_survives_in_started_at() -> None:
    [record] = run([row("missed", 1, "INVITE", 487, "long", time=T + 180, start=T)]).finished
    assert record["ended_at"] - record["started_at"] == 180


def test_the_numbers_come_from_the_first_invite_and_are_put_in_the_stored_form() -> None:
    rows = [
        row(
            "acc",
            1,
            "INVITE",
            200,
            "c1",
            time=T + 6,
            start=T,
            frm="2348000000001",
            to="08000000002",
        ),
        row("acc", 2, "BYE", 200, "c1", time=T + 60, frm="2348000000002", to="08000000001"),
    ]
    [record] = run(rows).finished
    assert (record["from_msisdn"], record["to_msisdn"]) == ("2348000000001", "2348000000002")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("08000000002", "2348000000002"),
        ("2348000000002", "2348000000002"),
        ("+2348000000002", "2348000000002"),
        ("+234 800 000 0002", "2348000000002"),
        ("2348000000002;phone-context=ims.example", "2348000000002"),
        ("", "unknown"),
        ("   ", "unknown"),
        ("112", "112"),  # matches no rule: kept as it came, the call is not dropped
        ("*123#", "*123#"),
        ("x" * 50, "x" * 32),
    ],
)
def test_numbers_are_normalised_or_kept_as_they_came(raw: str, expected: str) -> None:
    assert normalise_msisdn(raw) == expected


def test_the_watermarks_only_move_forward() -> None:
    rows = [
        row("acc", 9, "INVITE", 200, "c1", time=T),
        row("missed", 4, "INVITE", 486, "c2", time=T),
    ]
    done = run(rows, acc_id=20, missed_id=2)
    assert (done.acc_id, done.missed_id) == (20, 4)
    assert (run([]).acc_id, run([]).missed_id) == (0, 0)


def test_rows_arriving_out_of_order_give_the_same_records() -> None:
    rows = [
        row("acc", 1, "INVITE", 200, "c1", time=T + 6, start=T),
        row("acc", 2, "BYE", 200, "c1", time=T + 66),
        row("missed", 1, "INVITE", 603, "c2", time=T + 11, start=T),
    ]
    assert run(rows).finished == run(list(reversed(rows))).finished


def test_a_row_never_shows_a_number_or_a_call_id_in_its_repr() -> None:
    text = repr(row("acc", 1, "INVITE", 200, "secret-call-id", time=T, frm="2348000000999"))
    assert "secret-call-id" not in text and "2348000000999" not in text
