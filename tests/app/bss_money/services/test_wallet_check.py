"""The nightly check can fail: it must report a wallet that disagrees with its ledger."""

from __future__ import annotations

import logging

import pytest

from app.bss_money.domain.entries import new_posting
from app.bss_money.services.ledger import post_entry
from app.bss_money.services.wallet_check import check_wallets
from tests.app.bss_money.fakes import InMemoryLedgerRepository


def _ledger_with_two_lines() -> InMemoryLedgerRepository:
    ledger = InMemoryLedgerRepository()
    post_entry(ledger, new_posting(1, 1_000, "top_up", "a"))
    post_entry(ledger, new_posting(2, 2_000, "top_up", "a"))
    return ledger


def test_the_check_is_quiet_when_the_books_balance() -> None:
    assert check_wallets(_ledger_with_two_lines()) == []


def test_the_check_reports_a_deliberately_corrupted_balance(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ledger = _ledger_with_two_lines()
    ledger.balances[2] = 2_001
    caplog.set_level(logging.ERROR)
    found = check_wallets(ledger)
    assert [(m.line_id, m.wallet_kobo, m.ledger_kobo) for m in found] == [(2, 2_001, 2_000)]
    events = [
        r.__dict__ for r in caplog.records if r.__dict__.get("event") == "ledger.wallet_mismatch"
    ]
    assert len(events) == 1 and events[0]["line_id"] == 2


def test_the_check_reports_a_wallet_with_money_but_no_entries() -> None:
    ledger = InMemoryLedgerRepository()
    ledger.balances[5] = 10
    assert [(m.line_id, m.wallet_kobo, m.ledger_kobo) for m in check_wallets(ledger)] == [
        (5, 10, 0)
    ]
