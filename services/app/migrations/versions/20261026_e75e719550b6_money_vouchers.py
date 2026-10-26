"""money: voucher and voucher_attempt, the prepaid cards and their failed redemptions

Revision ID: e75e719550b6
Revises: e3b80975b879
Create Date: 2026-10-26 10:41:48.711605+00:00

`voucher` holds each card's number, a salted scrypt hash of its PIN (never the PIN), its face value
in kobo and its state. CHECK constraints keep the state to the Build Plan's list, the face value
positive, the number 20 characters, and a used card tied to who used it and when.
`voucher_attempt` holds the failed redemptions that count towards five per number per hour.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops both tables. It REFUSES while `voucher` holds any row: cards may be
printed and sold, and a PIN cannot be recovered from its hash, so dropping the table makes every
card worthless for good. With data, restore from a backup instead. `voucher_attempt` only holds the
last hour that matters and is dropped without a check.
"""

from alembic import op
import sqlalchemy as sa

revision = "e75e719550b6"
down_revision = "e3b80975b879"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voucher",
        sa.Column(
            "voucher_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("card_number", sa.String(length=20), nullable=False),
        sa.Column("pin_hash", sa.String(length=200), nullable=False),
        sa.Column("face_value_kobo", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("batch", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_line_id", sa.Integer(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(state = 'used') = (used_by_line_id IS NOT NULL AND used_at IS NOT NULL)",
            name=op.f("ck_voucher_used_has_user"),
        ),
        sa.CheckConstraint(
            "state IN ('requested', 'approved', 'sent_to_printer', 'in_stock', 'on_sale', "
            "'used', 'expired', 'locked')",
            name=op.f("ck_voucher_state_valid"),
        ),
        sa.CheckConstraint("face_value_kobo > 0", name=op.f("ck_voucher_face_value_positive")),
        sa.CheckConstraint("length(card_number) = 20", name=op.f("ck_voucher_card_number_length")),
        sa.PrimaryKeyConstraint("voucher_id", name=op.f("pk_voucher")),
        sa.UniqueConstraint("card_number", name=op.f("uq_voucher_card_number")),
    )
    op.create_index("ix_voucher_batch_state", "voucher", ["batch", "state"], unique=False)
    op.create_table(
        "voucher_attempt",
        sa.Column(
            "attempt_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("card_number", sa.String(length=20), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "length(card_number) = 20", name=op.f("ck_voucher_attempt_card_number_length")
        ),
        sa.PrimaryKeyConstraint("attempt_id", name=op.f("pk_voucher_attempt")),
    )
    op.create_index(
        "ix_voucher_attempt_card_number_attempted_at",
        "voucher_attempt",
        ["card_number", "attempted_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM voucher)")).scalar():
        raise RuntimeError(
            "refusing to drop voucher: it holds cards, and a PIN cannot be recovered from its "
            "hash; restore from a backup instead"
        )
    op.drop_index("ix_voucher_attempt_card_number_attempted_at", table_name="voucher_attempt")
    op.drop_table("voucher_attempt")
    op.drop_index("ix_voucher_batch_state", table_name="voucher")
    op.drop_table("voucher")
