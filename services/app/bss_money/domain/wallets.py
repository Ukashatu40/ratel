"""A wallet's balance must equal the sum of its ledger entries. This describes a disagreement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WalletMismatch:
    """A wallet whose stored balance is not the sum of its ledger entries."""

    line_id: int
    wallet_kobo: int
    ledger_kobo: int
