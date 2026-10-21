"""Unit tests for meter_api domain validation rules."""

from __future__ import annotations

import pytest

from services.app.meter_api.domain import UsageRecord


def test_valid_usage_record() -> None:
    rec = UsageRecord(
        imsi="621000000000001",
        period_start=1791820800,
        period_end=1791821100,
        bytes_up=1024,
        bytes_down=2048,
    )
    rec.validate()  # Does not raise


def test_invalid_imsi_rejected() -> None:
    rec = UsageRecord(
        imsi="123",
        period_start=1791820800,
        period_end=1791821100,
        bytes_up=100,
        bytes_down=200,
    )
    with pytest.raises(ValueError, match="Invalid IMSI format"):
        rec.validate()


def test_negative_timestamp_rejected() -> None:
    rec = UsageRecord(
        imsi="621000000000001",
        period_start=-1,
        period_end=1791821100,
        bytes_up=100,
        bytes_down=200,
    )
    with pytest.raises(ValueError, match="non-negative"):
        rec.validate()


def test_negative_bytes_rejected() -> None:
    rec = UsageRecord(
        imsi="621000000000001",
        period_start=1791820800,
        period_end=1791821100,
        bytes_up=-1,
        bytes_down=200,
    )
    with pytest.raises(ValueError, match="non-negative"):
        rec.validate()
