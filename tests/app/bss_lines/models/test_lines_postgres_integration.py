"""The lines migration on a real PostgreSQL: it applies, rolls back one step and applies again, it
refuses to drop tables that hold data, and nothing a line depends on can be deleted.

Run with RATEL_TEST_POSTGRES_URI set (see tests/app/bss_money/postgres.py). Each test gets its own
database, built by the real migrations.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.app.bss_money.postgres import Database

pytestmark = pytest.mark.integration

LINE_TABLES = {"customer", "sim", "number", "plan", "line", "line_audit"}
MONEY_TABLES = {"wallet", "ledger_entry", "allowance_bucket"}


def _tables(database: Database) -> set[str]:
    with database.engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        return set(rows)


def _add_a_line(database: Database) -> None:
    """One customer with one line: synthetic values only."""
    statements = [
        "INSERT INTO customer (name, phone, kyc_status) VALUES ('Synthetic', '2340000000001', 'verified')",  # noqa: E501
        "INSERT INTO sim (iccid, imsi, batch, state) "
        "VALUES ('8900000000000000001', '620000000000001', 'b', 'in_use')",
        "INSERT INTO number (msisdn, state) VALUES ('2340000000001', 'in_use')",
        "INSERT INTO plan (name, speed_ul_mbps, speed_dl_mbps, on_exhaustion, state) "
        "VALUES ('p', 1, 2, 'slow', 'on_sale')",
        "INSERT INTO line (customer_id, iccid, imsi, msisdn, plan_id, state) "
        "SELECT customer_id, '8900000000000000001', '620000000000001', '2340000000001', "
        "(SELECT plan_id FROM plan LIMIT 1), 'awaiting_activation' FROM customer",
    ]
    with database.engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def test_the_lines_migration_applies_rolls_back_one_step_and_applies_again(db: Database) -> None:
    assert LINE_TABLES <= _tables(db)
    db.alembic("downgrade", "-1")
    assert not LINE_TABLES & _tables(db)
    assert MONEY_TABLES <= _tables(db)  # only the lines step was undone
    db.alembic("upgrade", "head")
    assert LINE_TABLES <= _tables(db)


def test_a_rollback_is_refused_while_customers_exist_and_nothing_is_lost(db: Database) -> None:
    _add_a_line(db)
    with pytest.raises(RuntimeError, match="refusing to drop"):
        db.alembic("downgrade", "-1")
    assert LINE_TABLES <= _tables(db)
    assert db.scalar("SELECT count(*) FROM line") == 1


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM customer",
        "DELETE FROM sim",
        "DELETE FROM number",
        "DELETE FROM plan",
    ],
)
def test_nothing_a_line_depends_on_can_be_deleted(db: Database, statement: str) -> None:
    _add_a_line(db)
    with pytest.raises(IntegrityError), db.engine.begin() as conn:
        conn.execute(text(statement))
    assert db.scalar("SELECT count(*) FROM line") == 1
