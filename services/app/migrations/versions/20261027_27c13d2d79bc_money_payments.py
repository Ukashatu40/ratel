"""money: payment, the top-ups made through a gateway (Paystack first)

Revision ID: 27c13d2d79bc
Revises: 4f6279e32deb
Create Date: 2026-10-27 15:00:00.000000+00:00

One row per provider transaction. `provider_ref` and `public_id` and `idempotency_key` are unique, so a
notification delivered twice, a guessed id and a retried start each find the one row. CHECK
constraints keep the status to pending, succeeded or failed, the amount positive, the currency naira,
and `credited_at` set exactly when the payment succeeded.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the table. It REFUSES while the table holds any row: the rows are the
record of what customers paid and of which provider notification was already credited, and without
them a notification delivered again could credit the same payment a second time. With data, restore
from a backup instead.
"""

from alembic import op
import sqlalchemy as sa

revision = "27c13d2d79bc"
down_revision = "4f6279e32deb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment",
        sa.Column(
            "payment_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_ref", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("amount_kobo", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="NGN", nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("checkout_url", sa.String(length=500), nullable=True),
        sa.Column("provider_txn_id", sa.String(length=64), nullable=True),
        sa.Column("credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount_kobo > 0", name=op.f("ck_payment_amount_positive")),
        sa.CheckConstraint("currency = 'NGN'", name=op.f("ck_payment_currency_naira")),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')", name=op.f("ck_payment_status_valid")
        ),
        sa.CheckConstraint(
            "(status = 'succeeded') = (credited_at IS NOT NULL)",
            name=op.f("ck_payment_credited_iff_succeeded"),
        ),
        sa.PrimaryKeyConstraint("payment_id", name=op.f("pk_payment")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_payment_idempotency_key")),
        sa.UniqueConstraint("provider_ref", name=op.f("uq_payment_provider_ref")),
        sa.UniqueConstraint("public_id", name=op.f("uq_payment_public_id")),
    )
    op.create_index("ix_payment_status_created_at", "payment", ["status", "created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM payment)")).scalar():
        raise RuntimeError(
            "refusing to drop payment: it holds rows, the record of what was paid and credited; "
            "restore from a backup instead"
        )
    op.drop_index("ix_payment_status_created_at", table_name="payment")
    op.drop_table("payment")
