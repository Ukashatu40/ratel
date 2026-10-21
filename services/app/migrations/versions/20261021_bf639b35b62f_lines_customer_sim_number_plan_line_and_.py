"""lines: customer, sim, number, plan, line and audit

Revision ID: bf639b35b62f
Revises: 4776e9127fec
Create Date: 2026-10-21 09:27:13+00:00

PostgreSQL. The tables of RatelBSS: lines (docs/issues-modules, bss_lines). No ki or opc, and no
money: those live elsewhere. Every foreign key is ON DELETE RESTRICT, so nothing the business must
keep is removed with its parent.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the six tables in reverse order. It REFUSES to run while `line` or
`customer` holds any row, because dropping them destroys the record of who owns which line; with
real data, restore from a backup instead. Take a backup before any downgrade outside a test.

TODO(M-25): unique rules the stock needs (a SIM or number cannot be taken twice), the plan and
bundle fields, and indexes for finding a line by MSISDN, ICCID or IMSI.
"""

import sqlalchemy as sa
from alembic import op

revision = "bf639b35b62f"
down_revision = "4776e9127fec"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _timestamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "customer",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("kyc_status", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("customer_id", name=op.f("pk_customer")),
    )
    op.create_table(
        "number",
        sa.Column("msisdn", sa.String(length=15), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("msisdn", name=op.f("pk_number")),
    )
    op.create_table(
        "plan",
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("speed_ul_mbps", sa.Double(), nullable=False),
        sa.Column("speed_dl_mbps", sa.Double(), nullable=False),
        sa.Column("on_exhaustion", sa.String(length=10), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("plan_id", name=op.f("pk_plan")),
    )
    op.create_table(
        "sim",
        sa.Column("iccid", sa.String(length=20), nullable=False),
        sa.Column("imsi", sa.String(length=15), nullable=False),
        sa.Column("batch", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("iccid", name=op.f("pk_sim")),
        sa.UniqueConstraint("imsi", name=op.f("uq_sim_imsi")),
    )
    op.create_table(
        "line",
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("iccid", sa.String(length=20), nullable=False),
        sa.Column("imsi", sa.String(length=15), nullable=False),
        sa.Column("msisdn", sa.String(length=15), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer.customer_id"],
            name=op.f("fk_line_customer_id_customer"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["iccid"], ["sim.iccid"], name=op.f("fk_line_iccid_sim"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["msisdn"], ["number.msisdn"], name=op.f("fk_line_msisdn_number"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plan.plan_id"], name=op.f("fk_line_plan_id_plan"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("line_id", name=op.f("pk_line")),
    )
    op.create_table(
        "line_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.String(length=30), nullable=False),
        sa.Column("to_state", sa.String(length=30), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["line_id"], ["line.line_id"], name=op.f("fk_line_audit_line_id_line"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_line_audit")),
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("line", "customer"):
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError(
                f"refusing to drop {table}: it holds rows; restore from a backup instead"
            )
    op.drop_table("line_audit")
    op.drop_table("line")
    op.drop_table("sim")
    op.drop_table("plan")
    op.drop_table("number")
    op.drop_table("customer")
