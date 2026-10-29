"""money: foreign keys from the money tables to line

Revision ID: dd286ac07496
Revises: 824d292cb01b
Create Date: 2026-10-29 07:28:49.323119+00:00

`wallet.line_id`, `allowance_bucket.line_id`, `payment.line_id` and `voucher.used_by_line_id` now
name a line that exists, RESTRICT on delete: a line with money against it is never removed. (The
ledger entries follow through `wallet`; `usage_rating` already had its key.) `allowance_bucket.source_id`
stays a plain integer because it names a plan or a bundle depending on `source_kind`.

The routes already refuse a line that does not exist, so this is the database saying the same
thing, for the day a tool or a mistake does not go through them.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Upgrade: refuses, naming the table and how many rows, if any row names a line that does not exist
(left over from lab tests). Fix or remove those rows deliberately first; the migration never
deletes money records.

Rollback: downgrade() drops the four constraints. Safe with data: dropping a foreign key changes
no row.
"""

from alembic import op
import sqlalchemy as sa

revision = "dd286ac07496"
down_revision = "824d292cb01b"
branch_labels = None
depends_on = None

# (table, column, constraint). The names follow the naming convention in app/db.py.
KEYS = (
    ("allowance_bucket", "line_id", "fk_allowance_bucket_line_id_line"),
    ("payment", "line_id", "fk_payment_line_id_line"),
    ("voucher", "used_by_line_id", "fk_voucher_used_by_line_id_line"),
    ("wallet", "line_id", "fk_wallet_line_id_line"),
)


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, _name in KEYS:
        orphans = bind.execute(
            sa.text(
                f"SELECT count(*) FROM {table} t WHERE t.{column} IS NOT NULL "  # noqa: S608
                f"AND NOT EXISTS (SELECT 1 FROM line l WHERE l.line_id = t.{column})"
            )
        ).scalar()
        if orphans:
            raise RuntimeError(
                f"refusing to add the key: {orphans} row(s) in {table}.{column} name a line that "
                "does not exist; fix or remove them deliberately first"
            )
    for table, column, name in KEYS:
        op.create_foreign_key(
            op.f(name), table, "line", [column], ["line_id"], ondelete="RESTRICT"
        )


def downgrade() -> None:
    for table, _column, name in reversed(KEYS):
        op.drop_constraint(op.f(name), table, type_="foreignkey")
