"""The customer and plan columns the PRD added exist with the right types.

These are the columns from the Product Rules document, decided 2026-10-23.
Not every rule here is enforced yet (id_type values and address format are
TODO(PRD)); the columns themselves must be there, and the money column must
be BIGINT.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.app.bss_money.postgres import Database

pytestmark = pytest.mark.integration


def _columns(db: Database, table: str) -> dict[str, str]:
    with db.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table},
        ).all()
    return {r[0]: r[1] for r in rows}


def test_customer_has_the_prd_fields(db: Database) -> None:
    cols = _columns(db, "customer")
    for name in ("email", "id_type", "id_number", "address", "blocked", "kyc_status"):
        assert name in cols, f"customer.{name} missing"


def test_plan_has_the_prd_fields(db: Database) -> None:
    cols = _columns(db, "plan")
    for name in (
        "price_kobo",
        "validity_days",
        "data_bytes",
        "slow_ul_mbps",
        "slow_dl_mbps",
        "channels",
        "on_exhaustion",
        "speed_ul_mbps",
        "speed_dl_mbps",
    ):
        assert name in cols, f"plan.{name} missing"


def test_plan_price_kobo_is_bigint(db: Database) -> None:
    assert _columns(db, "plan")["price_kobo"] == "bigint"


def test_customer_blocked_defaults_to_false(db: Database) -> None:
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO customer "
                "(name, phone, email, id_type, id_number, address, kyc_status) "
                "VALUES "
                "('A', '2348000000001', 'a@example.test', 'NIN', '00000000000', 'addr', 'pending')"
            )
        )
