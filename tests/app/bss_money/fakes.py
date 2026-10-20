"""An in-memory ledger for the service tests. Test code only.

It follows the same contract as the SQL repository (repositories/ports.py): an entry and the wallet
move together, a repeated (line, kind, reference) is a duplicate, and a balance that would leave the
BIGINT range is refused. Production code never imports this module (tests/architecture enforces it).
"""

from __future__ import annotations

from app.bss_money.domain.entries import BIGINT_MAX, Posting
from app.bss_money.domain.wallets import WalletMismatch
from app.bss_money.repositories.ports import BalanceOutOfRange, DuplicateEntry, StoredEntry


class InMemoryLedgerRepository:
    def __init__(self) -> None:
        self.entries: list[StoredEntry] = []
        self.balances: dict[int, int] = {}  # tests may corrupt this on purpose

    def append(self, posting: Posting) -> tuple[StoredEntry, int]:
        if self.find(posting.line_id, posting.kind.value, posting.reference) is not None:
            raise DuplicateEntry
        new_balance = self.balances.get(posting.line_id, 0) + posting.amount_kobo
        if abs(new_balance) > BIGINT_MAX:
            raise BalanceOutOfRange
        entry = StoredEntry(
            len(self.entries) + 1,
            posting.line_id,
            posting.amount_kobo,
            posting.kind.value,
            posting.reference,
            None,
        )
        self.entries.append(entry)
        self.balances[posting.line_id] = new_balance
        return entry, new_balance

    def find(self, line_id: int, kind: str, reference: str) -> StoredEntry | None:
        return next(
            (
                e
                for e in self.entries
                if (e.line_id, e.kind, e.reference) == (line_id, kind, reference)
            ),
            None,
        )

    def balance(self, line_id: int) -> int | None:
        return self.balances.get(line_id)

    def mismatches(self) -> list[WalletMismatch]:
        found = []
        for line_id, balance in sorted(self.balances.items()):
            total = sum(e.amount_kobo for e in self.entries if e.line_id == line_id)
            if balance != total:
                found.append(WalletMismatch(line_id, balance, total))
        return found
