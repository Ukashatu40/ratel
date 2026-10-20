"""The wallet and ledger tables state their own rules, so the database refuses what the code
should never send. Every refusal is checked for its reason, not only for the fact of an error."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss_money.models.ledger import LedgerEntry, Wallet


def _wallet(session: Session, line_id: int = 1) -> None:
    # Flushed on its own: the entries below refer to it.
    session.add(Wallet(line_id=line_id, balance_kobo=0))
    session.flush()


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


def test_the_tables_from_the_build_plan_are_registered() -> None:
    from app.db import Base

    assert {"wallet", "ledger_entry", "allowance_bucket"} <= set(Base.metadata.tables)
