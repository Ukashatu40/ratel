"""The ledger on PostgreSQL (and SQLite in unit tests), through SQLAlchemy.

Only this module talks to the database for RatelBSS: money. It works inside the transaction the
caller owns and never commits, so a purchase can post a debit and its VAT entry together or not
at all. No rules here: those are in the domain and the services.
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.bss_money.domain.entries import Posting
from app.bss_money.domain.wallets import WalletMismatch
from app.bss_money.models.ledger import LedgerEntry, Wallet
from app.bss_money.repositories.ports import BalanceOutOfRange, DuplicateEntry, StoredEntry


class SqlLedgerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, posting: Posting) -> tuple[StoredEntry, int]:
        self._ensure_wallet(posting.line_id)
        try:
            # A savepoint: if the entry or the balance update fails, neither is kept, and the
            # caller's transaction can carry on.
            with self._session.begin_nested():
                entry = LedgerEntry(
                    line_id=posting.line_id,
                    amount_kobo=posting.amount_kobo,
                    kind=posting.kind.value,
                    reference=posting.reference,
                )
                self._session.add(entry)
                self._session.flush()
                balance = self._add_to_balance(posting.line_id, posting.amount_kobo)
        except IntegrityError as exc:
            if self.find(posting.line_id, posting.kind.value, posting.reference) is None:
                raise  # some other rule failed: do not call it a duplicate
            raise DuplicateEntry from exc
        except DataError as exc:
            raise BalanceOutOfRange from exc
        return _stored(entry), balance

    def find(self, line_id: int, kind: str, reference: str) -> StoredEntry | None:
        entry = self._session.execute(
            select(LedgerEntry).where(
                LedgerEntry.line_id == line_id,
                LedgerEntry.kind == kind,
                LedgerEntry.reference == reference,
            )
        ).scalar_one_or_none()
        return None if entry is None else _stored(entry)

    def balance(self, line_id: int) -> int | None:
        value = self._session.execute(
            select(Wallet.balance_kobo).where(Wallet.line_id == line_id)
        ).scalar_one_or_none()
        return None if value is None else int(value)

    def mismatches(self) -> list[WalletMismatch]:
        # Starts from the wallets: an entry cannot exist without one (foreign key), and a wallet
        # with no entries must have a zero balance.
        totals = (
            select(LedgerEntry.line_id, func.sum(LedgerEntry.amount_kobo).label("total"))
            .group_by(LedgerEntry.line_id)
            .subquery()
        )
        ledger_total = func.coalesce(totals.c.total, 0)
        rows = self._session.execute(
            select(Wallet.line_id, Wallet.balance_kobo, ledger_total)
            .outerjoin(totals, totals.c.line_id == Wallet.line_id)
            .where(Wallet.balance_kobo != ledger_total)
            .order_by(Wallet.line_id)
        ).all()
        return [WalletMismatch(int(r[0]), int(r[1]), int(r[2])) for r in rows]

    def _ensure_wallet(self, line_id: int) -> None:
        """Create the wallet with a zero balance if there is none. Safe to repeat and to race."""
        dialect = self._session.get_bind().dialect.name
        if dialect == "postgresql":
            pg = postgresql.insert(Wallet).values(line_id=line_id, balance_kobo=0)
            self._session.execute(pg.on_conflict_do_nothing(index_elements=[Wallet.line_id]))
        elif dialect == "sqlite":
            lite = sqlite.insert(Wallet).values(line_id=line_id, balance_kobo=0)
            self._session.execute(lite.on_conflict_do_nothing(index_elements=[Wallet.line_id]))
        else:
            raise NotImplementedError(
                f"the ledger supports PostgreSQL (and SQLite in tests), not {dialect}"
            )

    def _add_to_balance(self, line_id: int, amount_kobo: int) -> int:
        """One statement, so two postings to a line at the same moment cannot lose one."""
        new_balance = self._session.execute(
            update(Wallet)
            .where(Wallet.line_id == line_id)
            .values(balance_kobo=Wallet.balance_kobo + amount_kobo)
            .returning(Wallet.balance_kobo)
        ).scalar_one()
        return int(new_balance)


def _stored(entry: LedgerEntry) -> StoredEntry:
    return StoredEntry(
        entry.entry_id,
        entry.line_id,
        entry.amount_kobo,
        entry.kind,
        entry.reference,
        entry.created_at,
    )
