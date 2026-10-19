"""SQL for the wallet and the ledger. No rules here: those are in domain.py and services.py.

Every function works inside the caller's transaction and never commits, so a purchase can post a
debit and its VAT entry together or not at all.
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.bss_money.domain import Posting, WalletMismatch
from app.bss_money.models import LedgerEntry, Wallet


def ensure_wallet(session: Session, line_id: int) -> None:
    """Create the line's wallet with a zero balance if it has none. Safe to repeat and to race."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        pg = postgresql.insert(Wallet).values(line_id=line_id, balance_kobo=0)
        session.execute(pg.on_conflict_do_nothing(index_elements=[Wallet.line_id]))
    elif dialect == "sqlite":
        lite = sqlite.insert(Wallet).values(line_id=line_id, balance_kobo=0)
        session.execute(lite.on_conflict_do_nothing(index_elements=[Wallet.line_id]))
    else:
        raise NotImplementedError(
            f"the ledger supports PostgreSQL (and SQLite in tests), not {dialect}"
        )


def insert_entry(session: Session, posting: Posting) -> LedgerEntry:
    """Append one entry. Raises IntegrityError if (line, kind, reference) was already posted."""
    entry = LedgerEntry(
        line_id=posting.line_id,
        amount_kobo=posting.amount_kobo,
        kind=posting.kind.value,
        reference=posting.reference,
    )
    session.add(entry)
    session.flush()
    return entry


def add_to_balance(session: Session, line_id: int, amount_kobo: int) -> int:
    """Add to the balance in one statement, so concurrent postings to a line cannot lose one."""
    new_balance = session.execute(
        update(Wallet)
        .where(Wallet.line_id == line_id)
        .values(balance_kobo=Wallet.balance_kobo + amount_kobo)
        .returning(Wallet.balance_kobo)
    ).scalar_one()
    return int(new_balance)


def find_entry(session: Session, line_id: int, kind: str, reference: str) -> LedgerEntry | None:
    return session.execute(
        select(LedgerEntry).where(
            LedgerEntry.line_id == line_id,
            LedgerEntry.kind == kind,
            LedgerEntry.reference == reference,
        )
    ).scalar_one_or_none()


def wallet_balance(session: Session, line_id: int) -> int | None:
    balance = session.execute(
        select(Wallet.balance_kobo).where(Wallet.line_id == line_id)
    ).scalar_one_or_none()
    return None if balance is None else int(balance)


def wallet_mismatches(session: Session) -> list[WalletMismatch]:
    """Every wallet whose balance is not the sum of its entries.

    Starts from the wallets: an entry cannot exist without one (foreign key), and a wallet with
    no entries must have a zero balance.
    """
    totals = (
        select(LedgerEntry.line_id, func.sum(LedgerEntry.amount_kobo).label("total"))
        .group_by(LedgerEntry.line_id)
        .subquery()
    )
    ledger_total = func.coalesce(totals.c.total, 0)
    rows = session.execute(
        select(Wallet.line_id, Wallet.balance_kobo, ledger_total)
        .outerjoin(totals, totals.c.line_id == Wallet.line_id)
        .where(Wallet.balance_kobo != ledger_total)
        .order_by(Wallet.line_id)
    ).all()
    return [WalletMismatch(int(r[0]), int(r[1]), int(r[2])) for r in rows]
