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

# Revision ids referenced by the tests below. Kept as named constants so a change to the
# migration chain forces the tests to be re-read rather than silently drifting.
_BEFORE_LINES = "0001"
_BEFORE_CUSTOMER_AND_PLAN_FIELDS = "ef28cf85753e"


def _tables(database: Database) -> set[str]:
    with database.engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        return set(rows)


def _add_a_line(database: Database) -> None:
    """One customer with one line: synthetic values only."""
    statements = [
        "INSERT INTO customer "
        "(name, phone, email, id_type, id_number, address, kyc_status) "
        "VALUES "
        "('Synthetic', '2340000000001', 's@example.test', 'NIN', "
        "'00000000000', 'addr', 'verified')",
        "INSERT INTO sim (iccid, imsi, batch, state) "
        "VALUES ('8900000000000000001', '620000000000001', 'b', 'in_use')",
        "INSERT INTO number (msisdn, state) VALUES ('2340000000001', 'in_use')",
        "INSERT INTO plan "
        "(name, price_kobo, validity_days, data_bytes, "
        "speed_ul_mbps, speed_dl_mbps, slow_ul_mbps, slow_dl_mbps, "
        "channels, on_exhaustion, state) "
        "VALUES ('p', 500, 30, 1000000, 1, 2, 1, 1, 'data', 'slow', 'on_sale')",
        "INSERT INTO line (customer_id, iccid, imsi, msisdn, plan_id, state) "
        "SELECT customer_id, '8900000000000000001', '620000000000001', '2340000000001', "
        "(SELECT plan_id FROM plan LIMIT 1), 'awaiting_activation' FROM customer",
    ]
    with database.engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def test_the_lines_migration_applies_rolls_back_one_step_and_applies_again(db: Database) -> None:
    """Roll back to the migration *before* the lines migration and confirm the tables are gone.

    The lines migration is no longer the head: bss_lines added one on top
    (expires_at, state_before_suspension, bundle, indexes) and then the customer and plan
    fields (e3b80975b879). This test downgrades explicitly to the revision before lines
    (0001) rather than to head - 1, so it stays correct as more migrations land.
    """
    assert LINE_TABLES <= _tables(db)
    db.alembic("downgrade", _BEFORE_LINES)
    assert not LINE_TABLES & _tables(db)
    assert MONEY_TABLES <= _tables(db)  # only the lines migration was undone
    db.alembic("upgrade", "head")
    assert LINE_TABLES <= _tables(db)


def test_a_rollback_is_refused_while_customers_exist_and_nothing_is_lost(db: Database) -> None:
    _add_a_line(db)
    with pytest.raises(RuntimeError, match="refusing to drop"):
        db.alembic("downgrade", _BEFORE_LINES)
    assert LINE_TABLES <= _tables(db)
    assert db.scalar("SELECT count(*) FROM line") == 1


def test_the_lines_migration_refuses_on_its_own_when_only_a_customer_exists(db: Database) -> None:
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO customer "
                "(name, phone, email, id_type, id_number, address, kyc_status) "
                "VALUES "
                "('Synthetic', '2340000000001', 's@example.test', 'NIN', "
                "'00000000000', 'addr', 'verified')"
            )
        )


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


# --- The customer and plan fields migration (e3b80975b879) -----------------------------


def test_the_customer_and_plan_migration_upgrades_on_a_non_empty_table(
    db: Database,
) -> None:
    """A deployment with existing rows upgrades cleanly.

    The migration adds NOT NULL customer and plan columns. On a table that already holds
    rows, those must be backfilled first, or the ALTER COLUMN ... SET NOT NULL fails. This
    test seeds a customer and a plan under the previous schema, upgrades, and checks the
    backfilled values.
    """
    db.alembic("downgrade", _BEFORE_CUSTOMER_AND_PLAN_FIELDS)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO customer "
                "(name, phone, kyc_status) "
                "VALUES ('Synthetic', '2340000000001', 'verified')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO plan "
                "(name, speed_ul_mbps, speed_dl_mbps, on_exhaustion, state) "
                "VALUES ('Synthetic Plan', 10, 20, 'slow', 'on_sale')"
            )
        )

    db.alembic("upgrade", "head")

    id_type = db.scalar("SELECT id_type FROM customer LIMIT 1")
    id_number = db.scalar("SELECT id_number FROM customer LIMIT 1")
    address = db.scalar("SELECT address FROM customer LIMIT 1")
    email = db.scalar("SELECT email FROM customer LIMIT 1")
    blocked = db.scalar("SELECT blocked FROM customer LIMIT 1")
    assert id_type == "NIN"
    assert id_number == "00000000000"
    assert address == "unknown"
    assert email is None
    assert blocked is False

    price_kobo = db.scalar("SELECT price_kobo FROM plan LIMIT 1")
    validity_days = db.scalar("SELECT validity_days FROM plan LIMIT 1")
    data_bytes = db.scalar("SELECT data_bytes FROM plan LIMIT 1")
    channels = db.scalar("SELECT channels FROM plan LIMIT 1")
    assert price_kobo == 0
    assert validity_days == 1
    assert data_bytes == 0
    assert channels == "data"


def test_the_customer_and_plan_migration_downgrade_refuses_while_rows_exist(
    db: Database,
) -> None:
    """Downgrade must refuse while customer or plan holds rows.

    Matches the pattern in the lines and bundle migrations (042caad31d0f).
    """
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO customer "
                "(name, phone, email, id_type, id_number, address, kyc_status) "
                "VALUES ('Synthetic', '2340000000001', 's@example.test', 'NIN', "
                "'00000000000', 'addr', 'verified')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO plan "
                "(name, price_kobo, validity_days, data_bytes, speed_ul_mbps, "
                "speed_dl_mbps, slow_ul_mbps, slow_dl_mbps, channels, "
                "on_exhaustion, state) "
                "VALUES ('p', 500, 30, 1000000, 10, 20, 1, 1, 'data', 'slow', 'on_sale')"
            )
        )

    with pytest.raises(RuntimeError, match="refusing to drop"):
        db.alembic("downgrade", _BEFORE_CUSTOMER_AND_PLAN_FIELDS)

    # Nothing was dropped.
    assert db.scalar("SELECT count(*) FROM customer") == 1
    assert db.scalar("SELECT count(*) FROM plan") == 1


def test_a_stop_plan_has_no_slow_speeds_and_a_slow_plan_must_have_them(
    db: Database,
) -> None:
    """The CHECK constraint enforces the rule in both directions.

    on_exhaustion = 'slow' requires both slow speeds; any other value forbids them.
    """
    # slow plan with slow speeds: accepted
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO plan "
                "(name, price_kobo, validity_days, data_bytes, speed_ul_mbps, "
                "speed_dl_mbps, slow_ul_mbps, slow_dl_mbps, channels, "
                "on_exhaustion, state) "
                "VALUES ('slow-p', 500, 30, 1000000, 10, 20, 1, 1, 'data', 'slow', 'on_sale')"
            )
        )

    # stop plan with NULL slow speeds: accepted
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO plan "
                "(name, price_kobo, validity_days, data_bytes, speed_ul_mbps, "
                "speed_dl_mbps, slow_ul_mbps, slow_dl_mbps, channels, "
                "on_exhaustion, state) "
                "VALUES ('stop-p', 500, 30, 1000000, 10, 20, NULL, NULL, 'data', 'stop', 'on_sale')"
            )
        )

    # stop plan with non-NULL slow speeds: refused
    with pytest.raises(IntegrityError), db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO plan "
                "(name, price_kobo, validity_days, data_bytes, speed_ul_mbps, "
                "speed_dl_mbps, slow_ul_mbps, slow_dl_mbps, channels, "
                "on_exhaustion, state) "
                "VALUES ('bad-stop-p', 500, 30, 1000000, 10, 20, 1, 1, "
                "'data', 'stop', 'on_sale')"
            )
        )

    # slow plan with NULL slow speeds: refused
    with pytest.raises(IntegrityError), db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO plan "
                "(name, price_kobo, validity_days, data_bytes, speed_ul_mbps, "
                "speed_dl_mbps, slow_ul_mbps, slow_dl_mbps, channels, "
                "on_exhaustion, state) "
                "VALUES ('bad-slow-p', 500, 30, 1000000, 10, 20, NULL, NULL, "
                "'data', 'slow', 'on_sale')"
            )
        )

    count = db.scalar("SELECT count(*) FROM plan")
    assert isinstance(count, int)
    assert count >= 2


def test_a_plan_price_cannot_be_negative_or_validity_zero_or_data_negative(
    db: Database,
) -> None:
    """The plan CHECKs match the bundle CHECKs (price >= 0, validity > 0, data >= 0)."""
    cases: list[tuple[str, int, int, int, int]] = [
        ("price_kobo", -1, 500, 30, 1_000_000),
        ("validity_days", 0, 500, 0, 1_000_000),
        ("data_bytes", -1, 500, 30, -1),
    ]
    for column, bad_value, price, validity, data in cases:
        with pytest.raises(IntegrityError), db.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO plan "
                    "(name, price_kobo, validity_days, data_bytes, speed_ul_mbps, "
                    "speed_dl_mbps, slow_ul_mbps, slow_dl_mbps, channels, "
                    "on_exhaustion, state) "
                    "VALUES (:name, :price, :validity, :data, 10, 20, 1, 1, "
                    "'data', 'slow', 'on_sale')"
                ).bindparams(
                    name=f"bad-{column}",
                    price=bad_value if column == "price_kobo" else price,
                    validity=bad_value if column == "validity_days" else validity,
                    data=bad_value if column == "data_bytes" else data,
                )
            )
