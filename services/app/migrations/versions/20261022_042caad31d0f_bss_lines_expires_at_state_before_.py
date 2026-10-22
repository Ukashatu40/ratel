"""bss_lines: expires_at, state_before_suspension, bundle table, line indexes

Revision ID: 042caad31d0f
Revises: bf639b35b62f
Create Date: 2026-10-22 08:05:25.577316+00:00

PostgreSQL. Adds the two columns the line needs for expiry and suspension, the bundle table
(fields from M-16), and the lookup indexes the Build Plan asks for ("customer care can find any
line by MSISDN, ICCID or IMSI in under a second").

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the indexes, the two new columns, and the bundle table. It REFUSES to
run while `bundle` or `line` holds any row, because the columns and the table carry real data;
with real data, restore from a backup instead. Take a backup before any downgrade outside a test.

TODO(M-25): the unique rules the stock needs (a SIM or number cannot be taken twice), and the
customer and KYC fields, which wait on the PRD.
"""

from alembic import op
import sqlalchemy as sa

revision = "042caad31d0f"
down_revision = "bf639b35b62f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bundle",
        sa.Column("bundle_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("price_kobo", sa.BigInteger(), nullable=False),
        sa.Column("validity_days", sa.Integer(), nullable=False),
        sa.Column("data_bytes", sa.BigInteger(), nullable=False),
        sa.Column("channels", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("bundle_id", name=op.f("pk_bundle")),
    )
    op.add_column(
        "line", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "line",
        sa.Column("state_before_suspension", sa.String(length=30), nullable=True),
    )
    op.create_index(op.f("ix_line_iccid"), "line", ["iccid"], unique=False)
    op.create_index(op.f("ix_line_imsi"), "line", ["imsi"], unique=False)
    op.create_index(op.f("ix_line_msisdn"), "line", ["msisdn"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("bundle", "line"):
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError(
                f"refusing to drop {table}: it holds rows; restore from a backup instead"
            )
    op.drop_index(op.f("ix_line_msisdn"), table_name="line")
    op.drop_index(op.f("ix_line_imsi"), table_name="line")
    op.drop_index(op.f("ix_line_iccid"), table_name="line")
    op.drop_column("line", "state_before_suspension")
    op.drop_column("line", "expires_at")
    op.drop_table("bundle")