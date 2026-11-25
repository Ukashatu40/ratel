"""lines: SMS to customers (welcome, call summaries)

Revision ID: 5b8e0c3d7a21
Revises: c4a7f2e91b35
Create Date: 2026-11-25 04:00:00+00:00

SMS the app sends to customers from 555, through the voice VM (docs/customer-sms.md, decided by
the project lead on 2026-11-25):

- `customer_sms`: one row per SMS, queued in the same transaction as what it reports: the welcome
  at activation (`welcome:<line>`), the summary after each charged call (`call:<call record>`).
  `dedupe_key` is unique, so each happens once. `text` is final when queued (a call summary
  carries the balance at that moment). `sent_at` is null until the voice VM has handed it to the
  SMS centre.

Lines activated before this migration get no welcome. Nothing is backfilled.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the table. It refuses while the table holds rows: they record what
customers were told. Take a backup and drop it deliberately.
"""

from alembic import op
import sqlalchemy as sa

revision = "5b8e0c3d7a21"
down_revision = "c4a7f2e91b35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_sms",
        sa.Column("sms_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("text", sa.String(length=160), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["line_id"], ["line.line_id"], name=op.f("fk_customer_sms_line_id_line"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("sms_id", name=op.f("pk_customer_sms")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_customer_sms_dedupe_key")),
    )
    op.create_index(op.f("ix_customer_sms_line_id"), "customer_sms", ["line_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM customer_sms)")).scalar():
        raise RuntimeError(
            "refusing to drop customer_sms: it holds rows; take a backup and drop it deliberately"
        )
    op.drop_index(op.f("ix_customer_sms_line_id"), table_name="customer_sms")
    op.drop_table("customer_sms")
