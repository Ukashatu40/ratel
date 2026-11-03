"""meter: call records

Revision ID: a7c3e1f9b2d4
Revises: dd286ac07496
Create Date: 2026-11-03 09:30:00+00:00

Adds `call_record`: one row per call, keyed on `call_id` (the SIP Call-ID), written by the meter
agent's call mode and read by `GET /v1/calls` and by RatelDesk's line page
(docs/call-record-agreement.md). The CHECKs hold the agreement's rules: the end is not before the
start, an answer falls inside the call, and `completed` and "answered" are the same fact.
`end_reason` is the set proposed in the agreement (PRD decision 8 is still open); changing the set
is a new migration.

Call records are personal data (who called whom, and when).

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the table. It REFUSES while the table holds rows: the rows are the only
copy the app has (the voice VM's `acc` tables keep the raw events, but a drop would lose the
history already read). With rows, take a backup first and drop the table deliberately.
"""

from alembic import op
import sqlalchemy as sa

revision = "a7c3e1f9b2d4"
down_revision = "dd286ac07496"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "call_record",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("from_msisdn", sa.String(length=32), nullable=False),
        sa.Column("to_msisdn", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_reason", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_record")),
        sa.UniqueConstraint("call_id", name=op.f("uq_call_record_call_id")),
        sa.CheckConstraint(
            "end_reason IN ('completed', 'cancelled', 'declined', 'not_answered', "
            "'unavailable', 'failed')",
            name=op.f("ck_call_record_end_reason_valid"),
        ),
        sa.CheckConstraint("ended_at >= started_at", name=op.f("ck_call_record_period_valid")),
        sa.CheckConstraint(
            "answered_at IS NULL OR (answered_at >= started_at AND answered_at <= ended_at)",
            name=op.f("ck_call_record_answered_within_call"),
        ),
        sa.CheckConstraint(
            "(end_reason = 'completed') = (answered_at IS NOT NULL)",
            name=op.f("ck_call_record_completed_means_answered"),
        ),
    )
    op.create_index(op.f("ix_call_record_from_msisdn"), "call_record", ["from_msisdn"], unique=False)
    op.create_index(op.f("ix_call_record_to_msisdn"), "call_record", ["to_msisdn"], unique=False)
    op.create_index(op.f("ix_call_record_started_at"), "call_record", ["started_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM call_record)")).scalar():
        raise RuntimeError(
            "refusing to drop call_record: it holds call records; take a backup and drop it "
            "deliberately"
        )
    op.drop_index(op.f("ix_call_record_started_at"), table_name="call_record")
    op.drop_index(op.f("ix_call_record_to_msisdn"), table_name="call_record")
    op.drop_index(op.f("ix_call_record_from_msisdn"), table_name="call_record")
    op.drop_table("call_record")
