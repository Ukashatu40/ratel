"""What a line needs, judged from its allowance: table-driven, on synthetic buckets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.bss_lines.domain.state_machine import LineState
from app.bss_money.domain.allowance import Bucket, SourceKind
from app.bss_money.domain.exhaustion import ServiceAction, action_for

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def bucket(
    total: int = 1_000,
    used: int = 0,
    *,
    starts: datetime = NOW - DAY,
    expires: datetime = NOW + DAY,
    n: int = 1,
) -> Bucket:
    return Bucket(n, SourceKind.PLAN, 1, total, used, starts, expires)


A, OOD = LineState.ACTIVE, LineState.OUT_OF_DATA
NONE, OUT, EXPIRE = ServiceAction.NONE, ServiceAction.OUT_OF_DATA, ServiceAction.EXPIRE

CASES = [
    ("allowance left", A, [bucket(used=999)], NONE),
    ("exactly zero left", A, [bucket(used=1_000)], OUT),
    ("zero left in one, some in another", A, [bucket(used=1_000), bucket(n=2)], NONE),
    ("zero left in all", A, [bucket(used=1_000), bucket(used=500, total=500, n=2)], OUT),
    ("already out of data and still empty", OOD, [bucket(used=1_000)], NONE),
    ("out of data but topped up: restoring is the purchase's job", OOD, [bucket()], NONE),
    ("only bucket expired", A, [bucket(starts=NOW - 31 * DAY, expires=NOW - DAY)], EXPIRE),
    (
        "only bucket expired, was out of data",
        OOD,
        [bucket(starts=NOW - 31 * DAY, expires=NOW - DAY, used=1_000)],
        EXPIRE,
    ),
    ("expires exactly now", A, [bucket(expires=NOW)], EXPIRE),
    (
        "expired and renewed",
        A,
        [bucket(starts=NOW - 31 * DAY, expires=NOW - DAY), bucket(n=2)],
        NONE,
    ),
    (
        "expired, renewal not started yet",
        A,
        [
            bucket(starts=NOW - 31 * DAY, expires=NOW - DAY),
            bucket(starts=NOW + DAY, expires=NOW + 30 * DAY, n=2),
        ],
        NONE,
    ),
    (
        "expired, renewal valid but used up",
        A,
        [bucket(starts=NOW - 31 * DAY, expires=NOW - DAY), bucket(used=1_000, n=2)],
        OUT,
    ),
    ("a bucket of zero bytes, valid", A, [bucket(total=0)], OUT),
    ("no allowance ever", A, [], NONE),
    ("no allowance ever, out of data", OOD, [], NONE),
]


@pytest.mark.parametrize(("name", "state", "buckets", "expected"), CASES, ids=[c[0] for c in CASES])
def test_the_action_for_a_line(
    name: str, state: LineState, buckets: list[Bucket], expected: ServiceAction
) -> None:
    assert action_for(state, buckets, NOW) is expected


@pytest.mark.parametrize(
    "state",
    [
        LineState.AWAITING_ACTIVATION,
        LineState.SUSPENDED,
        LineState.EXPIRED,
        LineState.TERMINATED,
    ],
)
def test_a_line_that_is_not_in_service_is_never_touched(state: LineState) -> None:
    spent = bucket(used=1_000)
    old = bucket(starts=NOW - 31 * DAY, expires=NOW - DAY)
    assert action_for(state, [spent, old], NOW) is NONE


def test_the_order_of_the_buckets_does_not_matter() -> None:
    buckets = [
        bucket(used=1_000),
        bucket(used=1_000, n=2),
        bucket(starts=NOW - 31 * DAY, expires=NOW - DAY, n=3),
    ]
    assert action_for(A, buckets, NOW) is action_for(A, list(reversed(buckets)), NOW)


def test_the_moment_must_carry_a_timezone() -> None:
    naive = datetime(2026, 11, 2, 12, 0)  # noqa: DTZ001 - the point of the test
    with pytest.raises(ValueError):
        action_for(A, [bucket()], naive)
