"""The rating function on synthetic records: table-driven edge cases, then properties that must
hold for any input. No database, no clock: the moment to judge at is passed in."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.bss_money.domain.allowance import Bucket, SourceKind
from app.bss_money.domain.plans import OnExhaustion, Plan
from app.bss_money.domain.rating import DataDecision, UsageRecord, rate

T0 = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)
NOW = T0 + timedelta(hours=6)  # the moment the job judges at, after the records below


def _plan(on_exhaustion: OnExhaustion = OnExhaustion.SLOW) -> Plan:
    slow = on_exhaustion is OnExhaustion.SLOW
    return Plan(
        plan_id=1,
        name="Synthetic",
        price_kobo=100_000,
        validity_days=30,
        data_bytes=1_000,
        speed_ul_mbps=5,
        speed_dl_mbps=10,
        channels=("app",),
        on_exhaustion=on_exhaustion,
        slow_ul_mbps=0.25 if slow else None,
        slow_dl_mbps=0.5 if slow else None,
    )


def _bucket(
    bucket_id: int, total: int, *, used: int = 0, start: datetime = T0, days: int = 30
) -> Bucket:
    return Bucket(
        bucket_id,
        SourceKind.BUNDLE,
        bucket_id,
        total,
        used,
        start,
        start + timedelta(days=days),
    )


def _record(record_id: str, minutes: int, up: int, down: int) -> UsageRecord:
    return UsageRecord(record_id, T0 + timedelta(minutes=minutes), up, down)


# --- the edge cases the issue names -------------------------------------------------------------


@pytest.mark.parametrize(
    ("used_before", "usage", "remaining", "uncovered", "exhausted"),
    [
        (0, 0, 1_000, 0, False),  # nothing used
        (0, 400, 600, 0, False),  # part used
        (0, 999, 1, 0, False),  # one byte left
        (0, 1_000, 0, 0, True),  # exactly zero: out of data, nothing over
        (0, 1_001, 0, 1, True),  # one byte over
        (990, 10, 0, 0, True),  # exactly zero, starting from a used bucket
        (990, 11, 0, 1, True),  # one byte over, starting from a used bucket
        (0, 5_000, 0, 4_000, True),  # far over
    ],
)
def test_one_bucket_edge_cases(
    used_before: int, usage: int, remaining: int, uncovered: int, exhausted: bool
) -> None:
    records = [_record("r1", 10, usage // 2, usage - usage // 2)]
    result = rate(records, [_bucket(1, 1_000, used=used_before)], _plan(), NOW)
    assert (result.remaining_bytes, result.uncovered_bytes, result.exhausted) == (
        remaining,
        uncovered,
        exhausted,
    )
    assert result.ratings[0].deducted_bytes + result.ratings[0].uncovered_bytes == usage


@pytest.mark.parametrize(
    ("on_exhaustion", "decision", "slow"),
    [
        (OnExhaustion.SLOW, DataDecision.SLOW, (0.25, 0.5)),
        (OnExhaustion.STOP, DataDecision.CUT, (None, None)),
    ],
)
def test_when_nothing_is_left_the_plan_decides(
    on_exhaustion: OnExhaustion, decision: DataDecision, slow: tuple[float | None, float | None]
) -> None:
    result = rate([_record("r1", 5, 600, 400)], [_bucket(1, 1_000)], _plan(on_exhaustion), NOW)
    assert result.decision is decision
    assert (result.slow_ul_mbps, result.slow_dl_mbps) == slow


def test_while_data_remains_the_line_stays_at_full_speed_whatever_the_plan() -> None:
    for on_exhaustion in OnExhaustion:
        result = rate([_record("r1", 5, 1, 1)], [_bucket(1, 1_000)], _plan(on_exhaustion), NOW)
        assert result.decision is DataDecision.STAY
        assert (result.slow_ul_mbps, result.slow_dl_mbps) == (None, None)
        assert not result.exhausted


# --- several buckets: soonest expiry first ------------------------------------------------------


def test_usage_comes_out_of_the_bucket_that_expires_soonest() -> None:
    late = _bucket(1, 100, days=20)
    soon = _bucket(2, 100, days=5)
    middle = _bucket(3, 100, days=10)
    # Given in a scrambled order on purpose.
    result = rate([_record("r1", 5, 100, 50)], [late, soon, middle], _plan(), NOW)
    used = {b.bucket_id: b.data_bytes_used for b in result.buckets}
    assert used == {2: 100, 3: 50, 1: 0}  # 5 days first, then 10; the 20-day bucket untouched
    assert [b.bucket_id for b in result.buckets] == [2, 3, 1]  # in the order they are used
    assert result.remaining_bytes == 150


def test_one_record_spills_over_into_the_next_bucket() -> None:
    result = rate(
        [_record("r1", 5, 0, 250)],
        [_bucket(1, 100, days=3), _bucket(2, 100, days=6), _bucket(3, 100, days=9)],
        _plan(),
        NOW,
    )
    assert [b.data_bytes_used for b in result.buckets] == [100, 100, 50]
    assert result.ratings[0].deducted_bytes == 250 and result.uncovered_bytes == 0


def test_several_bundles_running_out_together_leave_the_excess_uncovered() -> None:
    result = rate(
        [_record("r1", 5, 0, 301)],
        [_bucket(1, 100), _bucket(2, 100, days=40), _bucket(3, 100, days=50)],
        _plan(),
        NOW,
    )
    assert result.remaining_bytes == 0 and result.exhausted
    assert result.uncovered_bytes == 1


def test_equal_expiry_breaks_the_tie_the_same_way_every_time() -> None:
    a, b = _bucket(1, 100), _bucket(2, 100)  # same start, same expiry
    forward = rate([_record("r1", 5, 0, 50)], [a, b], _plan(), NOW)
    backward = rate([_record("r1", 5, 0, 50)], [b, a], _plan(), NOW)
    assert forward == backward
    assert {x.bucket_id: x.data_bytes_used for x in forward.buckets} == {1: 50, 2: 0}


# --- time: which buckets a record may use, and what is lost -------------------------------------


def test_a_bucket_that_has_not_started_is_not_used() -> None:
    future = _bucket(1, 1_000, start=T0 + timedelta(days=1))
    result = rate([_record("r1", 5, 0, 100)], [future], _plan(), NOW)
    assert result.uncovered_bytes == 100
    assert result.buckets[0].data_bytes_used == 0


def test_a_record_at_the_exact_expiry_moment_falls_to_the_next_bucket() -> None:
    expiring = _bucket(1, 1_000, days=1)  # valid_to = T0 + 1 day
    next_one = _bucket(2, 1_000, days=30)
    at_expiry = UsageRecord("r1", expiring.valid_to, 0, 100)
    just_before = UsageRecord("r2", expiring.valid_to - timedelta(seconds=1), 0, 100)
    result = rate([at_expiry, just_before], [expiring, next_one], _plan(), expiring.valid_to)
    used = {b.bucket_id: b.data_bytes_used for b in result.buckets}
    assert used == {1: 100, 2: 100}  # only the earlier record could use the expiring bucket


def test_a_record_at_the_exact_start_moment_may_use_the_bucket() -> None:
    result = rate([UsageRecord("r1", T0, 0, 10)], [_bucket(1, 100)], _plan(), NOW)
    assert result.buckets[0].data_bytes_used == 10


def test_data_left_in_an_expired_bucket_is_lost() -> None:
    expired = _bucket(1, 1_000, used=100, days=1)  # 900 left, expired well before NOW
    live = _bucket(2, 200, start=T0 + timedelta(days=1), days=30)
    result = rate([], [expired, live], _plan(), T0 + timedelta(days=2))
    assert result.remaining_bytes == 200  # the 900 in the expired bucket do not count


def test_nothing_remaining_but_expired_leftovers_is_exhausted() -> None:
    expired = _bucket(1, 1_000, days=1)
    result = rate([], [expired], _plan(), T0 + timedelta(days=2))
    assert result.remaining_bytes == 0 and result.exhausted
    assert result.decision is DataDecision.SLOW


def test_before_any_bucket_starts_nothing_is_usable_yet() -> None:
    result = rate([], [_bucket(1, 1_000, start=T0 + timedelta(days=1))], _plan(), T0)
    assert result.remaining_bytes == 0


# --- it never raises on empty or unsorted input -------------------------------------------------


def test_empty_input_gives_a_result_and_not_an_error() -> None:
    nothing = rate([], [], _plan(), NOW)
    assert (nothing.remaining_bytes, nothing.ratings, nothing.buckets) == (0, (), ())
    assert nothing.exhausted and nothing.decision is DataDecision.SLOW


def test_buckets_with_no_usage_are_left_as_they_were() -> None:
    result = rate([], [_bucket(1, 1_000, used=250)], _plan(), NOW)
    assert result.remaining_bytes == 750 and result.buckets[0].data_bytes_used == 250


def test_usage_with_no_buckets_is_all_uncovered() -> None:
    result = rate([_record("r1", 5, 10, 20)], [], _plan(), NOW)
    assert result.uncovered_bytes == 30 and result.ratings[0].deducted_bytes == 0


def test_a_record_of_zero_bytes_is_fine() -> None:
    result = rate([_record("r1", 5, 0, 0)], [_bucket(1, 100)], _plan(), NOW)
    assert result.ratings[0].deducted_bytes == 0 and result.remaining_bytes == 100


def test_records_in_any_order_give_the_same_result() -> None:
    records = [_record(f"r{i}", i * 5, 30, 20) for i in range(12)]
    buckets = [_bucket(1, 200, days=2), _bucket(2, 250, days=9), _bucket(3, 120, days=4)]
    expected = rate(records, buckets, _plan(), NOW)
    rng = random.Random(7)  # noqa: S311  (repeatable test data, not security)
    for _ in range(25):
        rng.shuffle(records)
        rng.shuffle(buckets)
        assert rate(records, buckets, _plan(), NOW) == expected


# --- replays ------------------------------------------------------------------------------------


def test_rating_the_same_input_twice_gives_the_same_result_and_changes_no_input() -> None:
    records = [_record("r1", 5, 10, 20), _record("r2", 10, 30, 40)]
    buckets = [_bucket(1, 1_000)]
    first = rate(records, buckets, _plan(), NOW)
    second = rate(records, buckets, _plan(), NOW)
    assert first == second
    assert buckets[0].data_bytes_used == 0  # the input bucket was not changed


def test_a_record_that_appears_twice_counts_once() -> None:
    once = rate([_record("r1", 5, 10, 20)], [_bucket(1, 1_000)], _plan(), NOW)
    twice = rate(
        [_record("r1", 5, 10, 20), _record("r1", 5, 10, 20)], [_bucket(1, 1_000)], _plan(), NOW
    )
    assert twice == once


def test_a_bucket_listed_twice_counts_once() -> None:
    once = rate([_record("r1", 5, 0, 50)], [_bucket(1, 100)], _plan(), NOW)
    twice = rate([_record("r1", 5, 0, 50)], [_bucket(1, 100), _bucket(1, 100)], _plan(), NOW)
    assert twice == once


# --- types and strictness -----------------------------------------------------------------------


def test_every_byte_count_in_the_result_is_a_whole_number() -> None:
    result = rate([_record("r1", 5, 10, 20)], [_bucket(1, 1_000)], _plan(), NOW)
    counts = [result.remaining_bytes, result.uncovered_bytes]
    counts += [b.data_bytes_used for b in result.buckets]
    counts += [x for r in result.ratings for x in (r.deducted_bytes, r.uncovered_bytes)]
    assert all(type(c) is int for c in counts)


def test_a_naive_time_is_refused_everywhere() -> None:
    naive = datetime(2026, 10, 19, 12, 0)  # noqa: DTZ001  (naive on purpose)
    with pytest.raises(ValueError, match="timezone-aware"):
        rate([], [], _plan(), naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        UsageRecord("r1", naive, 1, 1)


@pytest.mark.parametrize(("up", "down"), [(-1, 0), (0, -1)])
def test_negative_usage_is_refused(up: int, down: int) -> None:
    with pytest.raises(ValueError, match="negative"):
        UsageRecord("r1", T0, up, down)


# --- properties: for any input ------------------------------------------------------------------

bucket_specs = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=5_000),  # total
        st.integers(min_value=0, max_value=5_000),  # used (clamped below)
        st.integers(min_value=0, max_value=20),  # start offset, in days
        st.integers(min_value=1, max_value=30),  # validity, in days
    ),
    max_size=6,
)
record_specs = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=25 * 24 * 60),  # minutes after T0
        st.integers(min_value=0, max_value=3_000),
        st.integers(min_value=0, max_value=3_000),
    ),
    max_size=25,
)


def _build(specs: list[tuple[int, int, int, int]]) -> list[Bucket]:
    return [
        _bucket(i + 1, total, used=min(used, total), start=T0 + timedelta(days=offset), days=days)
        for i, (total, used, offset, days) in enumerate(specs)
    ]


def _records(specs: list[tuple[int, int, int]]) -> list[UsageRecord]:
    return [_record(f"r{i}", minutes, up, down) for i, (minutes, up, down) in enumerate(specs)]


@settings(max_examples=150, deadline=None)
@given(bucket_specs, record_specs, st.integers(min_value=0, max_value=40 * 24 * 60))
def test_nothing_is_created_or_lost_and_no_bucket_goes_over(
    specs: list[tuple[int, int, int, int]],
    rspecs: list[tuple[int, int, int]],
    as_of_minutes: int,
) -> None:
    buckets, records = _build(specs), _records(rspecs)
    result = rate(records, buckets, _plan(), T0 + timedelta(minutes=as_of_minutes))

    total_usage = sum(r.total_bytes for r in records)
    assert sum(r.deducted_bytes + r.uncovered_bytes for r in result.ratings) == total_usage

    taken = sum(b.data_bytes_used for b in result.buckets) - sum(b.data_bytes_used for b in buckets)
    assert taken == sum(r.deducted_bytes for r in result.ratings)

    assert all(0 <= b.data_bytes_used <= b.data_bytes_total for b in result.buckets)
    assert result.remaining_bytes >= 0
    assert result.exhausted == (result.remaining_bytes == 0)


@settings(max_examples=100, deadline=None)
@given(bucket_specs, record_specs, st.randoms(use_true_random=False))
def test_the_result_never_depends_on_the_order_of_the_input(
    specs: list[tuple[int, int, int, int]],
    rspecs: list[tuple[int, int, int]],
    rng: random.Random,
) -> None:
    buckets, records = _build(specs), _records(rspecs)
    expected = rate(records, buckets, _plan(), NOW)
    shuffled_buckets, shuffled_records = list(buckets), list(records)
    rng.shuffle(shuffled_buckets)
    rng.shuffle(shuffled_records)
    assert rate(shuffled_records, shuffled_buckets, _plan(), NOW) == expected


def _one_byte_at_a_time(
    records: list[UsageRecord], buckets: list[Bucket]
) -> tuple[dict[int, int], int]:
    """A deliberately naive reference: move each byte alone, from the soonest-expiring bucket that
    is valid at the record's time and still has room. Slow, obviously right, used only to check
    the real function."""
    used = {b.bucket_id: b.data_bytes_used for b in buckets}
    in_order = sorted(buckets, key=lambda b: (b.valid_to, b.valid_from, b.bucket_id))
    uncovered = 0
    for record in sorted(records, key=lambda r: (r.period_start, r.record_id)):
        for _ in range(record.total_bytes):
            for bucket in in_order:
                if (
                    bucket.is_valid_at(record.period_start)
                    and used[bucket.bucket_id] < bucket.data_bytes_total
                ):
                    used[bucket.bucket_id] += 1
                    break
            else:
                uncovered += 1
    return used, uncovered


small_bucket_specs = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=200),  # total
        st.integers(min_value=0, max_value=200),  # used (clamped below)
        st.integers(min_value=0, max_value=20),  # start offset, in days
        st.integers(min_value=1, max_value=30),  # validity, in days
    ),
    max_size=6,
)
small_record_specs = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=25 * 24 * 60),
        st.integers(min_value=0, max_value=80),
        st.integers(min_value=0, max_value=80),
    ),
    max_size=20,
)


@settings(max_examples=150, deadline=None)
@given(small_bucket_specs, small_record_specs)
def test_it_agrees_with_a_naive_byte_at_a_time_reference(
    specs: list[tuple[int, int, int, int]], rspecs: list[tuple[int, int, int]]
) -> None:
    buckets, records = _build(specs), _records(rspecs)
    result = rate(records, buckets, _plan(), NOW)
    expected_used, expected_uncovered = _one_byte_at_a_time(records, buckets)
    assert {b.bucket_id: b.data_bytes_used for b in result.buckets} == expected_used
    assert result.uncovered_bytes == expected_uncovered
