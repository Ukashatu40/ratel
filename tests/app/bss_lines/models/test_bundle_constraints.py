"""The bundle table refuses invalid values at the database level.

The domain layer rejects them; this proves the database does too, the same way
`usage_record` does.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.app.bss_money.postgres import Database

pytestmark = pytest.mark.integration


def _insert(db: Database, *, price_kobo: int, validity_days: int, data_bytes: int) -> None:
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO bundle (name, price_kobo, validity_days, data_bytes, channels) "
                "VALUES ('test', :price, :days, :data, 'data')"
            ),
            {"price": price_kobo, "days": validity_days, "data": data_bytes},
        )


def test_a_valid_bundle_is_accepted(db: Database) -> None:
    _insert(db, price_kobo=500, validity_days=30, data_bytes=1_000_000)
    assert db.scalar("SELECT count(*) FROM bundle") == 1


def test_a_negative_price_is_refused(db: Database) -> None:
    with pytest.raises(IntegrityError, match="ck_bundle_price_kobo_non_negative"):
        _insert(db, price_kobo=-1, validity_days=30, data_bytes=1_000_000)


@pytest.mark.parametrize("days", [0, -1])
def test_a_zero_or_negative_validity_days_is_refused(db: Database, days: int) -> None:
    with pytest.raises(IntegrityError, match="ck_bundle_validity_days_positive"):
        _insert(db, price_kobo=500, validity_days=days, data_bytes=1_000_000)


def test_negative_data_bytes_is_refused(db: Database) -> None:
    with pytest.raises(IntegrityError, match="ck_bundle_data_bytes_non_negative"):
        _insert(db, price_kobo=500, validity_days=30, data_bytes=-1)
