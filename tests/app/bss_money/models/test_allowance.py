"""The allowance bucket states its own rules. Every refusal is checked for its reason."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss_money.models.allowance import AllowanceBucket
from tests.app.bss_money.rating_data import seed_lines


@pytest.fixture(autouse=True)
def _lines(session: Session) -> None:
    """The foreign keys need the lines these tests name to exist."""
    seed_lines(session, 7)


NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def _bucket(**overrides: object) -> AllowanceBucket:
    values: dict[str, object] = {
        "line_id": 1,
        "source_kind": "plan",
        "source_id": 1,
        "data_bytes_total": 1_000,
        "data_bytes_used": 0,
        "valid_from": NOW,
        "valid_to": NOW + timedelta(days=30),
    }
    values.update(overrides)
    return AllowanceBucket(**values)


def test_a_valid_bucket_is_accepted(session: Session) -> None:
    session.add(_bucket())
    session.commit()


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"source_kind": "voucher"}, "source_kind_valid"),
        ({"data_bytes_total": -1, "data_bytes_used": 0}, "total_not_negative"),
        ({"data_bytes_used": -1}, "used_not_negative"),
        ({"data_bytes_used": 1_001}, "used_within_total"),  # more used than it ever held
        ({"valid_to": NOW}, "valid_to_after_valid_from"),  # expires the moment it starts
        ({"valid_to": NOW - timedelta(days=1)}, "valid_to_after_valid_from"),
    ],
)
def test_a_bucket_that_breaks_a_rule_is_refused(
    session: Session, overrides: dict[str, object], rule: str
) -> None:
    session.add(_bucket(**overrides))
    with pytest.raises(IntegrityError) as refused:
        session.commit()
    assert rule in str(refused.value)
