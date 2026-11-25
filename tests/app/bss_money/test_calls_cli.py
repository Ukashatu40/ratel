"""The call-charging job's exit code is what its timer sees, and it is off until a start is set."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.bss_lines.models.lines import CustomerSms
from app.bss_money.calls_cli import main
from app.bss_money.domain.entries import EntryKind, new_posting
from app.bss_money.models.catalogue import CallCharge
from app.bss_money.repositories.sql import SqlLedgerRepository
from app.db import Base
from app.meter_api.models import CallRecordModel
from tests.app.bss_money.rating_data import seed_line

ENDED = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)


def _database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+pysqlite:///{tmp_path / 'bss.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s, s.begin():
        line = seed_line(s)
        s.flush()
        SqlLedgerRepository(s).append(new_posting(line.line_id, 50_000, EntryKind.TOP_UP, "t:1"))
        s.add(
            CallRecordModel(
                call_id="c1",
                from_msisdn="2348000000001",  # seed_line(n=1)
                to_msisdn="08031234567",
                started_at=ENDED - timedelta(seconds=70),
                answered_at=ENDED - timedelta(seconds=60),
                ended_at=ENDED,
                end_reason="completed",
            )
        )
    engine.dispose()
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def test_off_until_a_start_is_set_and_nothing_is_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = _database(tmp_path, monkeypatch)
    monkeypatch.setenv("CALL_CHARGING_FROM", "")
    assert main([]) == 0
    engine = create_engine(url)
    with Session(engine) as s:
        assert s.scalar(select(CallCharge.call_record_id)) is None
    engine.dispose()


def test_a_call_is_charged_and_its_sms_queued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = _database(tmp_path, monkeypatch)
    monkeypatch.setenv("CALL_CHARGING_FROM", "2026-11-25T00:00:00+00:00")
    assert main([]) == 0
    engine = create_engine(url)
    with Session(engine) as s:
        charge = s.scalars(select(CallCharge)).one()
        sms = s.scalars(select(CustomerSms)).one()
    engine.dispose()
    assert (charge.seconds, charge.charged_kobo) == (
        60,
        2_000,
    )  # off-net minute at the default rate
    assert sms.kind == "call" and sms.dedupe_key == f"call:{charge.call_record_id}"
    assert (
        sms.text
        == "Last call to 08031234567: 1m 00s, cost N20.00. Balance N480.00. Text MENU to 555."
    )


def test_exit_2_when_the_database_cannot_be_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'missing' / 'x.db'}")
    monkeypatch.setenv("CALL_CHARGING_FROM", "2026-11-25T00:00:00+00:00")
    assert main([]) == 2
    assert "missing" not in capsys.readouterr().err
