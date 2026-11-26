"""money: prepaid calls and SMS (call reservations, SMS charges, the SMS price)

Revision ID: 8d2f6a4c1e93
Revises: 5b8e0c3d7a21
Create Date: 2026-11-26 10:00:00+00:00

Calls stop when the airtime runs out, and texts are paid from airtime (ADR 0013, decided by the
project lead on 2026-11-26):

- `catalogue_setting.sms_onnet_kobo`: the price of one text to another Ratelplus line, VAT
  inclusive. The existing row gets 200 (N2), the decided price; staff change it in RatelDesk.
- `call_reservation`: money held for a call while it runs, one row per SIP Call-ID. `state` is
  open (running), ended (hung up, holding the call's cost) or settled (its call record has been
  charged). Open and ended rows that have not reached `expires_at` count against the line's
  available balance.
- `sms_charge`: one row per text the SMS centre asked about, unique on its message id, so a retry
  gets the same answer and is charged once. `line_id` is null when the sender is not a line in
  RatelBSS.

Nothing is backfilled: both tables start empty, and nothing is charged until CALL_CHARGING_FROM.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the two tables and the column. It refuses while `sms_charge` holds
rows (they explain ledger entries). `call_reservation` rows are working state and may go.
"""

from alembic import op
import sqlalchemy as sa

revision = "8d2f6a4c1e93"
down_revision = "5b8e0c3d7a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalogue_setting",
        sa.Column("sms_onnet_kobo", sa.BigInteger(), server_default="200", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_catalogue_setting_sms_onnet_not_negative"),
        "catalogue_setting",
        "sms_onnet_kobo >= 0",
    )

    op.create_table(
        "call_reservation",
        sa.Column("reservation_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("rate_kobo_per_min", sa.BigInteger(), nullable=False),
        sa.Column("max_seconds", sa.Integer(), nullable=False),
        sa.Column("reserved_kobo", sa.BigInteger(), nullable=False),
        sa.Column("used_seconds", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("max_seconds > 0", name=op.f("ck_call_reservation_max_seconds_positive")),
        sa.CheckConstraint("reserved_kobo >= 0", name=op.f("ck_call_reservation_reserved_not_negative")),
        sa.CheckConstraint("rate_kobo_per_min >= 0", name=op.f("ck_call_reservation_rate_not_negative")),
        sa.CheckConstraint(
            "state IN ('open', 'ended', 'settled')", name=op.f("ck_call_reservation_known_state")
        ),
        sa.ForeignKeyConstraint(
            ["line_id"], ["line.line_id"], name=op.f("fk_call_reservation_line_id_line"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("reservation_id", name=op.f("pk_call_reservation")),
        sa.UniqueConstraint("call_id", name=op.f("uq_call_reservation_call_id")),
    )
    op.create_index("ix_call_reservation_line_state", "call_reservation", ["line_id", "state"], unique=False)

    op.create_table(
        "sms_charge",
        sa.Column("sms_charge_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("charged_kobo", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("charged_kobo >= 0", name=op.f("ck_sms_charge_charged_not_negative")),
        sa.ForeignKeyConstraint(
            ["line_id"], ["line.line_id"], name=op.f("fk_sms_charge_line_id_line"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("sms_charge_id", name=op.f("pk_sms_charge")),
        sa.UniqueConstraint("message_id", name=op.f("uq_sms_charge_message_id")),
    )
    op.create_index("ix_sms_charge_line_id", "sms_charge", ["line_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM sms_charge)")).scalar():
        raise RuntimeError(
            "refusing to drop sms_charge: it holds rows that explain ledger entries; take a backup "
            "and drop it deliberately"
        )
    op.drop_index("ix_sms_charge_line_id", table_name="sms_charge")
    op.drop_table("sms_charge")
    op.drop_index("ix_call_reservation_line_state", table_name="call_reservation")
    op.drop_table("call_reservation")
    op.drop_constraint(
        op.f("ck_catalogue_setting_sms_onnet_not_negative"), "catalogue_setting", type_="check"
    )
    op.drop_column("catalogue_setting", "sms_onnet_kobo")
