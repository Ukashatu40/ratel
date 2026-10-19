"""The tables state their own rules, so the database refuses what the code should never send.

Every refusal is checked for its reason, not only for the fact of an error, so a test cannot pass
because something else went wrong.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss_money.models import AllowanceBucket, LedgerEntry, Wallet
from app.db import Base

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


def _wallet(session: Session, line_id: int = 1) -> None:
    # Flushed on its own: the entries below refer to it.
    session.add(Wallet(line_id=line_id, balance_kobo=0))
    session.flush()


def test_the_three_tables_from_the_build_plan_exist() -> None:
    assert {"wallet", "ledger_entry", "allowance_bucket"} <= set(Base.metadata.tables)


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


def test_a_ledger_entry_needs_a_wallet(session: Session) -> None:
    session.add(LedgerEntry(line_id=99, amount_kobo=100, kind="top_up", reference="r"))
    with pytest.raises(IntegrityError) as refused:
        session.commit()
    assert "FOREIGN KEY" in str(refused.value)


def test_a_zero_ledger_entry_is_refused(session: Session) -> None:
    _wallet(session)
    session.add(LedgerEntry(line_id=1, amount_kobo=0, kind="top_up", reference="r"))
    with pytest.raises(IntegrityError) as refused:
        session.commit()
    assert "amount_not_zero" in str(refused.value)


def test_the_same_line_kind_and_reference_cannot_be_posted_twice(session: Session) -> None:
    _wallet(session)
    session.add(LedgerEntry(line_id=1, amount_kobo=100, kind="top_up", reference="pay-1"))
    session.commit()
    session.add(LedgerEntry(line_id=1, amount_kobo=100, kind="top_up", reference="pay-1"))
    with pytest.raises(IntegrityError) as refused:
        session.commit()
    assert "UNIQUE" in str(refused.value)


def test_one_reference_may_carry_a_purchase_and_its_vat(session: Session) -> None:
    _wallet(session)
    session.add(LedgerEntry(line_id=1, amount_kobo=-1000, kind="purchase", reference="buy-1"))
    session.add(LedgerEntry(line_id=1, amount_kobo=-75, kind="vat", reference="buy-1"))
    session.commit()


def test_the_ledger_table_has_no_updated_at() -> None:
    # An entry is never updated, so a column that suggests otherwise would be misleading.
    assert "updated_at" not in LedgerEntry.__table__.columns
