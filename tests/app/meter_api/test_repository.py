"""Tests for SqlUsageRepository: upsert, replay, filtering, and large-scale pagination."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.meter_api.domain import UsageRecord
from app.meter_api.models import UsageRecordModel
from app.meter_api.repositories.sql import SqlUsageRepository
from common.timeutil import from_epoch


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


def test_upsert_and_replay_overwrites_without_duplicates(session: Session) -> None:
    repo = SqlUsageRepository(session)

    initial = [
        UsageRecord(
            imsi="621000000000001",
            period_start=1791820800,
            period_end=1791821100,
            bytes_up=1000,
            bytes_down=2000,
        )
    ]
    repo.upsert_records(initial)
    session.commit()

    records, _ = repo.query_usage(
        from_time=from_epoch(1791820000),
        to_time=from_epoch(1791822000),
        imsi="621000000000001",
    )
    assert len(records) == 1
    assert records[0].bytes_up == 1000

    # Replay with updated bytes: must overwrite the row, not create a second row
    replay = [
        UsageRecord(
            imsi="621000000000001",
            period_start=1791820800,
            period_end=1791821100,
            bytes_up=1500,
            bytes_down=3000,
        )
    ]
    repo.upsert_records(replay)
    session.commit()

    all_rows = session.query(UsageRecordModel).all()
    assert len(all_rows) == 1
    assert all_rows[0].bytes_up == 1500
    assert all_rows[0].bytes_down == 3000


def test_query_filtering_by_imsi_and_time(session: Session) -> None:
    repo = SqlUsageRepository(session)

    records = [
        UsageRecord("621000000000001", 1791820800, 1791821100, 100, 100),
        UsageRecord("621000000000001", 1791821100, 1791821400, 200, 200),
        UsageRecord("621000000000002", 1791820800, 1791821100, 300, 300),
    ]
    repo.upsert_records(records)
    session.commit()

    # Filter by IMSI 1
    res1, _ = repo.query_usage(
        from_time=from_epoch(1791820800),
        to_time=from_epoch(1791821400),
        imsi="621000000000001",
    )
    assert len(res1) == 2

    # Filter by specific interval
    res2, _ = repo.query_usage(
        from_time=from_epoch(1791821100),
        to_time=from_epoch(1791821100),
    )
    assert len(res2) == 1
    assert res2[0].imsi == "621000000000001"


def test_pagination_covers_12000_records_with_no_gaps_or_duplicates(session: Session) -> None:
    """M-12 Acceptance Criteria: Pagination covers 12,000 records with no gap and no duplicate."""
    repo = SqlUsageRepository(session)

    total_records = 12000
    base_epoch = 1791820800
    batch_size = 2000

    # Insert 12,000 records in batches (e.g. 10 IMSIs across 1200 intervals)
    for batch_idx in range(0, total_records, batch_size):
        chunk: list[UsageRecord] = []
        for i in range(batch_idx, batch_idx + batch_size):
            interval_idx = i // 10
            imsi_idx = i % 10
            p_start = base_epoch + interval_idx * 300
            chunk.append(
                UsageRecord(
                    imsi=f"6210000000000{imsi_idx:02d}",
                    period_start=p_start,
                    period_end=p_start + 300,
                    bytes_up=100 + i,
                    bytes_down=200 + i,
                )
            )
        repo.upsert_records(chunk)
    session.commit()

    # Paginate through all 12,000 records using cursor
    collected: list[UsageRecord] = []
    cursor: str | None = None
    page_limit = 2500

    while True:
        page, cursor = repo.query_usage(
            from_time=from_epoch(base_epoch),
            to_time=from_epoch(base_epoch + 1500 * 300),
            limit=page_limit,
            cursor=cursor,
        )
        collected.extend(page)
        if cursor is None:
            break

    assert len(collected) == total_records

    # Check for no duplicates
    keys = {(r.imsi, r.period_start) for r in collected}
    assert len(keys) == total_records
