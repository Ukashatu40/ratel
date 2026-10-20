"""money: the wallet, the append-only ledger and the allowance buckets

Revision ID: 4776e9127fec
Revises:
Create Date: 2026-10-19 00:00:00+00:00

PostgreSQL only (the triggers are PostgreSQL). Money is BIGINT kobo.

The ledger is append-only in the database itself: a trigger refuses UPDATE and DELETE on every
row and TRUNCATE on the table (docs/adr/0009-ledger-append-only-in-the-database.md).

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md. Money tables: two reviewers.

Rollback: downgrade() drops the three tables and the trigger function. It REFUSES to run while
`ledger_entry` holds any row, because dropping a ledger destroys the record of every payment; with
real entries, restore from a backup instead. Take a backup before any downgrade outside a test.

TODO(M-25): foreign keys from `line_id` to `line.line_id`, and from `source_id` to the plan and
bundle tables, in a later migration once the bss_lines schema exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "4776e9127fec"
down_revision = None
branch_labels = None
depends_on = None

BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "wallet",
        sa.Column("line_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("balance_kobo", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("line_id", name=op.f("pk_wallet")),
    )

    op.create_table(
        "ledger_entry",
        sa.Column("entry_id", BIGINT_PK, autoincrement=True, nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("amount_kobo", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount_kobo <> 0", name=op.f("ck_ledger_entry_amount_not_zero")),
        sa.ForeignKeyConstraint(
            ["line_id"],
            ["wallet.line_id"],
            name=op.f("fk_ledger_entry_line_id_wallet"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("entry_id", name=op.f("pk_ledger_entry")),
        sa.UniqueConstraint(
            "line_id", "kind", "reference", name=op.f("uq_ledger_entry_line_id_kind_reference")
        ),
    )
    op.create_index("ix_ledger_entry_line_id", "ledger_entry", ["line_id"])

    op.create_table(
        "allowance_bucket",
        sa.Column("bucket_id", BIGINT_PK, autoincrement=True, nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(length=10), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("data_bytes_total", sa.BigInteger(), nullable=False),
        sa.Column("data_bytes_used", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source_kind IN ('plan', 'bundle')", name=op.f("ck_allowance_bucket_source_kind_valid")
        ),
        sa.CheckConstraint(
            "data_bytes_total >= 0", name=op.f("ck_allowance_bucket_total_not_negative")
        ),
        sa.CheckConstraint(
            "data_bytes_used >= 0", name=op.f("ck_allowance_bucket_used_not_negative")
        ),
        sa.CheckConstraint(
            "data_bytes_used <= data_bytes_total", name=op.f("ck_allowance_bucket_used_within_total")
        ),
        sa.CheckConstraint(
            "valid_to > valid_from", name=op.f("ck_allowance_bucket_valid_to_after_valid_from")
        ),
        sa.PrimaryKeyConstraint("bucket_id", name=op.f("pk_allowance_bucket")),
    )
    op.create_index(
        "ix_allowance_bucket_line_id_valid_to", "allowance_bucket", ["line_id", "valid_to"]
    )

    # Append-only, enforced by the database (ADR 0009). Row triggers refuse UPDATE and DELETE;
    # a statement trigger refuses TRUNCATE, which row triggers do not see.
    op.execute(
        """
        CREATE FUNCTION ledger_entry_refuse_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'ledger_entry is append-only: % is refused', TG_OP
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER ledger_entry_no_update_delete
        BEFORE UPDATE OR DELETE ON ledger_entry
        FOR EACH ROW EXECUTE FUNCTION ledger_entry_refuse_change()
        """
    )
    op.execute(
        """
        CREATE TRIGGER ledger_entry_no_truncate
        BEFORE TRUNCATE ON ledger_entry
        FOR EACH STATEMENT EXECUTE FUNCTION ledger_entry_refuse_change()
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM ledger_entry)")).scalar():
        raise RuntimeError(
            "refusing to drop a ledger that holds entries; restore from a backup instead"
        )
    op.execute("DROP TRIGGER ledger_entry_no_truncate ON ledger_entry")
    op.execute("DROP TRIGGER ledger_entry_no_update_delete ON ledger_entry")
    op.execute("DROP FUNCTION ledger_entry_refuse_change()")
    op.drop_index("ix_allowance_bucket_line_id_valid_to", table_name="allowance_bucket")
    op.drop_table("allowance_bucket")
    op.drop_index("ix_ledger_entry_line_id", table_name="ledger_entry")
    op.drop_table("ledger_entry")
    op.drop_table("wallet")
