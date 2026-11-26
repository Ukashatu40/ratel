"""Prepaid calls and texts on a real PostgreSQL (ADR 0013): calls and texts from one line started
at the same moment take turns over its balance, so the same naira is never promised twice.

SQLite cannot show this (it has no row locks). Run with RATEL_TEST_POSTGRES_URI set.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.bss_money.domain.catalogue import DEFAULT_SETTINGS
from app.bss_money.domain.prepaid import SmsOutcome
from app.bss_money.repositories.ports import PrepaidRepositories
from app.bss_money.repositories.sql import (
    SqlCatalogueRepository,
    SqlLedgerRepository,
    SqlPrepaidRepository,
)
from app.bss_money.services.prepaid import authorize_call, charge_sms
from tests.app.bss_money.postgres import Database

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
LAUNCH = NOW - timedelta(hours=1)
CALLER = "2348000000001"  # line 1 (tests/app/bss_money/rating_data.py)
FRIEND = "2348000000002"  # line 2
ONNET = DEFAULT_SETTINGS.voice_onnet_kobo_per_min


@pytest.fixture
def scope(db: Database):  # type: ignore[no-untyped-def]
    db.lines(2)

    @contextmanager
    def scope() -> Iterator[PrepaidRepositories]:
        with Session(db.engine) as session, session.begin():
            yield PrepaidRepositories(
                prepaid=SqlPrepaidRepository(session),
                ledger=SqlLedgerRepository(session),
                catalogue=SqlCatalogueRepository(session),
            )

    return scope


def test_calls_started_at_once_never_hold_more_than_the_balance(db: Database, scope) -> None:  # type: ignore[no-untyped-def]
    db.post(1, 3 * ONNET, "top_up", "pay-1")  # three minutes on-net

    def call(n: int) -> int:
        decision = authorize_call(
            scope,
            call_id=f"call-{n}",
            caller=CALLER,
            dialled=FRIEND,
            free_numbers=frozenset(),
            charge_from=LAUNCH,
            now=NOW,
        )
        return decision.max_seconds if decision.allowed else 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        granted = list(pool.map(call, range(8)))
    assert sum(granted) == 180  # one call got it all; the others were refused
    assert db.scalar("SELECT sum(reserved_kobo) FROM call_reservation") == 3 * ONNET


def test_texts_sent_at_once_are_each_charged_once_and_never_below_zero(db: Database, scope) -> None:  # type: ignore[no-untyped-def]
    price = DEFAULT_SETTINGS.sms_onnet_kobo
    db.post(1, 3 * price, "top_up", "pay-1")

    def text(n: int) -> SmsOutcome:
        outcome, _ = charge_sms(
            scope,
            message_id=f"m{n % 5}",  # five texts, each retried at once
            sender=CALLER,
            recipient=FRIEND,
            vat_rate_bps=750,
            charge_from=LAUNCH,
            now=NOW,
        )
        return outcome

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(text, range(10)))
    assert db.scalar("SELECT count(*) FROM sms_charge WHERE outcome = 'charged'") == 3
    assert db.scalar("SELECT count(*) FROM sms_charge") == 5
    assert db.scalar("SELECT balance_kobo FROM wallet WHERE line_id = 1") == 0
