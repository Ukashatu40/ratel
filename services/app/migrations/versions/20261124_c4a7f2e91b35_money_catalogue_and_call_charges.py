"""money: catalogue settings and audit, call charges

Revision ID: c4a7f2e91b35
Revises: a7c3e1f9b2d4
Create Date: 2026-11-24 20:30:00+00:00

The catalogue an admin keeps in RatelDesk, and voice calls paid from airtime (docs/catalogue.md,
decided by the project lead on 2026-11-24):

- `catalogue_setting`: one row (id 1) of airtime limits and call rates. No row is written here: until
  an admin saves settings, the code's defaults apply (domain/catalogue.py, DEFAULT_SETTINGS).
- `catalogue_audit`: append-only, every catalogue change with who made it and why. Catalogue values
  only, no personal data.
- `call_charge`: one row per call record the charging job has handled, keyed on the record, so a
  call is charged once. Linked to call records, which are personal data.

Plans and bundles keep their tables (`plan`, `bundle`); nothing about them changes here.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the three tables. It REFUSES while `call_charge` or `catalogue_audit`
hold rows: they are the only record of what calls were charged and of who changed the catalogue
(the ledger keeps the money itself). Take a backup and drop them deliberately.
"""

from alembic import op
import sqlalchemy as sa

revision = "c4a7f2e91b35"
down_revision = "a7c3e1f9b2d4"
branch_labels = None
depends_on = None

_TIMESTAMPS = (
    "created_at",
    "updated_at",
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        for name in _TIMESTAMPS
    ]


def upgrade() -> None:
    op.create_table(
        "catalogue_setting",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("airtime_min_kobo", sa.BigInteger(), nullable=False),
        sa.Column("card_min_kobo", sa.BigInteger(), nullable=False),
        sa.Column("card_max_kobo", sa.BigInteger(), nullable=False),
        sa.Column("airtime_presets", sa.String(length=120), nullable=False),
        sa.Column("voice_onnet_kobo_per_min", sa.BigInteger(), nullable=False),
        sa.Column("voice_offnet_kobo_per_min", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalogue_setting")),
        sa.CheckConstraint("id = 1", name=op.f("ck_catalogue_setting_single_row")),
        sa.CheckConstraint("airtime_min_kobo >= 1", name=op.f("ck_catalogue_setting_airtime_min_positive")),
        sa.CheckConstraint(
            "card_min_kobo >= airtime_min_kobo", name=op.f("ck_catalogue_setting_card_min_not_below_airtime")
        ),
        sa.CheckConstraint(
            "card_max_kobo >= card_min_kobo", name=op.f("ck_catalogue_setting_card_max_not_below_min")
        ),
        sa.CheckConstraint("voice_onnet_kobo_per_min >= 0", name=op.f("ck_catalogue_setting_onnet_not_negative")),
        sa.CheckConstraint("voice_offnet_kobo_per_min >= 0", name=op.f("ck_catalogue_setting_offnet_not_negative")),
    )
    op.create_table(
        "catalogue_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("offer_kind", sa.String(length=10), nullable=True),
        sa.Column("offer_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalogue_audit")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_catalogue_audit_idempotency_key")),
    )
    op.create_index(op.f("ix_catalogue_audit_created_at"), "catalogue_audit", ["created_at"], unique=False)
    op.create_table(
        "call_charge",
        sa.Column(
            "call_record_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=False, nullable=False
        ),
        sa.Column("line_id", sa.Integer(), nullable=True),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.Column("on_net", sa.Boolean(), nullable=False),
        sa.Column("rate_kobo_per_min", sa.BigInteger(), nullable=False),
        sa.Column("charged_kobo", sa.BigInteger(), nullable=False),
        sa.Column("uncovered_kobo", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("call_record_id", name=op.f("pk_call_charge")),
        sa.ForeignKeyConstraint(
            ["call_record_id"],
            ["call_record.id"],
            name=op.f("fk_call_charge_call_record_id_call_record"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["line_id"], ["line.line_id"], name=op.f("fk_call_charge_line_id_line"), ondelete="RESTRICT"
        ),
        sa.CheckConstraint("seconds >= 0", name=op.f("ck_call_charge_seconds_not_negative")),
        sa.CheckConstraint("charged_kobo >= 0", name=op.f("ck_call_charge_charged_not_negative")),
        sa.CheckConstraint("uncovered_kobo >= 0", name=op.f("ck_call_charge_uncovered_not_negative")),
    )
    op.create_index(op.f("ix_call_charge_line_id"), "call_charge", ["line_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("call_charge", "catalogue_audit"):
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():  # noqa: S608
            raise RuntimeError(
                f"refusing to drop {table}: it holds rows; take a backup and drop it deliberately"
            )
    op.drop_index(op.f("ix_call_charge_line_id"), table_name="call_charge")
    op.drop_table("call_charge")
    op.drop_index(op.f("ix_catalogue_audit_created_at"), table_name="catalogue_audit")
    op.drop_table("catalogue_audit")
    op.drop_table("catalogue_setting")
