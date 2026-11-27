"""money: voucher batches managed in RatelDesk (voucher_batch, voucher_event, the voucher values)

Revision ID: 4e1b8c7d2a90
Revises: 8d2f6a4c1e93
Create Date: 2026-11-27 15:00:00+00:00

Decided by the project lead on 2026-11-27 (docs/runbooks/voucher-batches.md): admins request,
approve, print (a branded PDF, once), stock and sell voucher batches in RatelDesk.

- `voucher_batch`: one row per batch, with who requested, approved and printed it. Its cards are
  made only when it is printed, in `voucher` with `batch` = `name`. At most 240 cards a batch.
- `voucher_event`: every voucher step taken in RatelDesk, with who and why. Never a PIN.
- `catalogue_setting.voucher_values`: the face values a batch may have, comma-separated kobo. The
  existing row gets N100, N200, N500, N1,000 and N2,000; admins change them in RatelDesk.

Nothing is backfilled. Cards made with voucher_cli keep working and are not listed as batches.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() refuses while `voucher_batch` holds rows: their cards exist and their
history explains them. Take a backup and drop them deliberately if it must go.
"""

from alembic import op
import sqlalchemy as sa

revision = "4e1b8c7d2a90"
down_revision = "8d2f6a4c1e93"
branch_labels = None
depends_on = None

BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "voucher_batch",
        sa.Column("batch_id", BIGINT_PK, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("face_value_kobo", sa.BigInteger(), nullable=False),
        sa.Column("card_count", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.String(length=254), nullable=False),
        sa.Column("approved_by", sa.String(length=254), nullable=True),
        sa.Column("printed_by", sa.String(length=254), nullable=True),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "state IN ('requested', 'approved', 'sent_to_printer', 'in_stock', 'on_sale', 'locked')",
            name=op.f("ck_voucher_batch_state_valid"),
        ),
        sa.CheckConstraint(
            "(printed_by IS NULL) = (printed_at IS NULL)", name=op.f("ck_voucher_batch_printed_has_printer")
        ),
        sa.CheckConstraint("card_count BETWEEN 1 AND 240", name=op.f("ck_voucher_batch_card_count_range")),
        sa.CheckConstraint("face_value_kobo > 0", name=op.f("ck_voucher_batch_face_value_positive")),
        sa.PrimaryKeyConstraint("batch_id", name=op.f("pk_voucher_batch")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_voucher_batch_idempotency_key")),
        sa.UniqueConstraint("name", name=op.f("uq_voucher_batch_name")),
    )
    op.create_table(
        "voucher_event",
        sa.Column("event_id", BIGINT_PK, autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=True),
        sa.Column("voucher_id", sa.BigInteger(), nullable=True),
        sa.Column("actor", sa.String(length=254), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["voucher_batch.batch_id"],
            name=op.f("fk_voucher_event_batch_id_voucher_batch"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["voucher_id"],
            ["voucher.voucher_id"],
            name=op.f("fk_voucher_event_voucher_id_voucher"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_voucher_event")),
    )
    op.create_index("ix_voucher_event_batch_id", "voucher_event", ["batch_id"], unique=False)
    op.add_column(
        "catalogue_setting",
        sa.Column(
            "voucher_values",
            sa.String(length=120),
            server_default="10000,20000,50000,100000,200000",
            nullable=False,
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM voucher_batch)")).scalar():
        raise RuntimeError(
            "refusing to drop voucher_batch: it holds batches whose cards exist; take a backup "
            "and drop it deliberately"
        )
    op.drop_column("catalogue_setting", "voucher_values")
    op.drop_index("ix_voucher_event_batch_id", table_name="voucher_event")
    op.drop_table("voucher_event")
    op.drop_table("voucher_batch")
