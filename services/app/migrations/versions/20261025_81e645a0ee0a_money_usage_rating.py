"""money: usage_rating, which usage records the rating job has rated

Revision ID: 81e645a0ee0a
Revises: e3b80975b879
Create Date: 2026-10-25 11:47:44.962316+00:00

One row per usage record, keyed by the record's id, written in the same transaction that deducts
the bytes from the line's buckets (M-17). The key is what stops a record being rated twice, and the
foreign keys tie each row to a real record and a real line.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the table. It REFUSES while the table holds any row: those rows are the
only record of which usage has already been deducted, and without them the next run would deduct
the same usage again and charge customers twice. With data, restore from a backup instead.
"""

from alembic import op
import sqlalchemy as sa

revision = "81e645a0ee0a"
down_revision = "e3b80975b879"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_rating",
        sa.Column(
            "usage_record_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("deducted_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uncovered_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("deducted_bytes >= 0", name=op.f("ck_usage_rating_deducted_not_negative")),
        sa.CheckConstraint("uncovered_bytes >= 0", name=op.f("ck_usage_rating_uncovered_not_negative")),
        sa.ForeignKeyConstraint(
            ["line_id"], ["line.line_id"], name=op.f("fk_usage_rating_line_id_line"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["usage_record_id"],
            ["usage_record.id"],
            name=op.f("fk_usage_rating_usage_record_id_usage_record"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("usage_record_id", name=op.f("pk_usage_rating")),
    )
    op.create_index("ix_usage_rating_line_id", "usage_rating", ["line_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM usage_rating)")).scalar():
        raise RuntimeError(
            "refusing to drop usage_rating: it holds rows, the only record of which usage was "
            "already deducted; restore from a backup instead"
        )
    op.drop_index("ix_usage_rating_line_id", table_name="usage_rating")
    op.drop_table("usage_rating")
