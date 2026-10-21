"""create usage_record table

Revision ID: 0001
Revises:
Create Date: 2026-10-20 10:55:00 UTC
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = "4776e9127fec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_record",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("imsi", sa.String(length=15), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bytes_up", sa.BigInteger(), nullable=False),
        sa.Column("bytes_down", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_record")),
        sa.UniqueConstraint(
            "imsi", "period_start", name=op.f("uq_usage_record_imsi_period_start")
        ),
        sa.CheckConstraint("bytes_up >= 0", name=op.f("ck_usage_record_bytes_up_non_negative")),
        sa.CheckConstraint(
            "bytes_down >= 0", name=op.f("ck_usage_record_bytes_down_non_negative")
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name=op.f("ck_usage_record_period_valid")
        ),
    )
    op.create_index(
        op.f("ix_usage_record_imsi"), "usage_record", ["imsi"], unique=False
    )
    op.create_index(
        op.f("ix_usage_record_period_start"),
        "usage_record",
        ["period_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_record_period_start"), table_name="usage_record")
    op.drop_index(op.f("ix_usage_record_imsi"), table_name="usage_record")
    op.drop_table("usage_record")
