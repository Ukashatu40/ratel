"""lines: customer_audit, who registered, verified or rejected a customer, and why

Revision ID: 1e88ea7593b2
Revises: 27c13d2d79bc
Create Date: 2026-10-28 19:53:25.663710+00:00

One row per change to a customer's identity status. Appended to, never edited. `reason` is free
text typed by staff and is personal data. The foreign key is RESTRICT: a customer with a history
is never removed with it.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the table. It REFUSES while the table holds any row: the rows are the
record of who vouched for whom, and without them that cannot be recovered. With data, restore from
a backup instead.
"""

from alembic import op
import sqlalchemy as sa

revision = "1e88ea7593b2"
down_revision = "27c13d2d79bc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer.customer_id"],
            name=op.f("fk_customer_audit_customer_id_customer"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_audit")),
    )
    op.create_index("ix_customer_audit_customer_id", "customer_audit", ["customer_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM customer_audit)")).scalar():
        raise RuntimeError(
            "refusing to drop customer_audit: it holds rows, the record of who vouched for whom; "
            "restore from a backup instead"
        )
    op.drop_index("ix_customer_audit_customer_id", table_name="customer_audit")
    op.drop_table("customer_audit")
