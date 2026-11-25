"""lines: welcome SMS queue

Revision ID: 5b8e0c3d7a21
Revises: c4a7f2e91b35
Create Date: 2026-11-25 04:00:00+00:00

The welcome SMS a line gets once, after activation (docs/welcome-sms.md, decided by the project
lead on 2026-11-25):

- `welcome_sms`: one row per activated line, written in the activation's transaction. `sent_at` is
  null until the voice VM has handed the SMS to the SMS centre. No text and no number are stored:
  the text is built from the line's number when it is sent.

Lines activated before this migration get no row, so they get no welcome SMS. Nothing is backfilled.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the table. It refuses while the table holds rows: they record which
customers were welcomed. Take a backup and drop it deliberately.
"""

from alembic import op
import sqlalchemy as sa

revision = "5b8e0c3d7a21"
down_revision = "c4a7f2e91b35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "welcome_sms",
        sa.Column("line_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["line_id"], ["line.line_id"], name=op.f("fk_welcome_sms_line_id_line"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("line_id", name=op.f("pk_welcome_sms")),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM welcome_sms)")).scalar():
        raise RuntimeError(
            "refusing to drop welcome_sms: it holds rows; take a backup and drop it deliberately"
        )
    op.drop_table("welcome_sms")
