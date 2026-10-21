"""The allowance bucket: what it holds, when it is valid, and how a purchase creates one."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.bss_money.domain.allowance import Bucket, SourceKind, bucket_for
from app.bss_money.domain.plans import Bundle, OnExhaustion, Plan

T0 = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def _bucket(**overrides: Any) -> Bucket:
    values: dict[str, Any] = {
        "bucket_id": 1,
        "source_kind": SourceKind.PLAN,
        "source_id": 1,
        "data_bytes_total": 1_000,
        "data_bytes_used": 0,
        "valid_from": T0,
        "valid_to": T0 + timedelta(days=30),
    }
    values.update(overrides)
    return Bucket(**values)


def test_remaining_is_total_minus_used() -> None:
    assert _bucket(data_bytes_used=400).remaining_bytes == 600


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"data_bytes_total": -1}, "negative"),
        ({"data_bytes_used": -1}, "negative"),
        ({"data_bytes_used": 1_001}, "used more than it held"),
        ({"valid_from": datetime(2026, 10, 19)}, "timezone-aware"),  # noqa: DTZ001  (naive on purpose)
        ({"valid_to": datetime(2026, 11, 19)}, "timezone-aware"),  # noqa: DTZ001  (naive on purpose)
        ({"valid_to": T0}, "expire after"),
        ({"valid_to": T0 - timedelta(days=1)}, "expire after"),
        ({"source_kind": "voucher"}, "source_kind"),
    ],
)
def test_a_bad_bucket_is_refused(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _bucket(**overrides)


def test_the_source_kind_may_be_given_as_text() -> None:
    assert _bucket(source_kind="bundle").source_kind is SourceKind.BUNDLE


def test_a_bucket_is_valid_from_its_start_up_to_but_not_including_its_expiry() -> None:
    bucket = _bucket()
    assert not bucket.is_valid_at(T0 - timedelta(seconds=1))
    assert bucket.is_valid_at(T0)
    assert bucket.is_valid_at(bucket.valid_to - timedelta(seconds=1))
    assert not bucket.is_valid_at(bucket.valid_to)


def _plan() -> Plan:
    return Plan(
        plan_id=7,
        name="Synthetic",
        price_kobo=100_000,
        validity_days=30,
        data_bytes=2_000,
        speed_ul_mbps=5,
        speed_dl_mbps=10,
        channels=("app",),
        on_exhaustion=OnExhaustion.STOP,
    )


def _bundle() -> Bundle:
    return Bundle(
        bundle_id=9,
        name="Synthetic",
        price_kobo=20_000,
        validity_days=7,
        data_bytes=500,
        channels=("app",),
    )


def test_buying_a_plan_creates_a_full_bucket_for_its_validity() -> None:
    bucket = bucket_for(_plan(), bucket_id=3, starts_at=T0)
    assert (bucket.source_kind, bucket.source_id) == (SourceKind.PLAN, 7)
    assert (bucket.data_bytes_total, bucket.data_bytes_used) == (2_000, 0)
    assert (bucket.valid_from, bucket.valid_to) == (T0, T0 + timedelta(days=30))


def test_buying_a_bundle_creates_a_full_bucket_for_its_validity() -> None:
    bucket = bucket_for(_bundle(), bucket_id=4, starts_at=T0)
    assert (bucket.source_kind, bucket.source_id) == (SourceKind.BUNDLE, 9)
    assert (bucket.data_bytes_total, bucket.valid_to) == (500, T0 + timedelta(days=7))


def test_a_purchase_needs_a_timezone_aware_start() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        bucket_for(_plan(), bucket_id=1, starts_at=datetime(2026, 10, 19, 12, 0))  # noqa: DTZ001  (naive on purpose)
