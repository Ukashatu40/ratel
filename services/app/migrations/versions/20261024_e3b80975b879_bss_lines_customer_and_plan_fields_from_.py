"""bss_lines: customer and plan fields from the PRD

Revision ID: e3b80975b879
Revises: ef28cf85753e
Create Date: 2026-10-24 08:01:33.800945+00:00

Adds the customer fields from PRODUCT_RULES.md (email, id_type, id_number, address,
blocked) and the plan fields (price_kobo, validity_days, data_bytes, slow_ul_mbps,
slow_dl_mbps, channels), plus the database-level CHECK constraints the plan needs.

New NOT NULL columns need a value for every existing row. `customer` may already
have rows on a real deployment, and `plan` certainly does (plans exist before this
migration). All four customer columns (email, id_type, id_number, address) are
required, matching the Customer schema in contracts/openapi.yaml, so they get a
placeholder value first, then NOT NULL.

The placeholder backfill must not be used on a database with real customers. A
real deployment must replace these values before the pilot; they exist only so the
migration can run on a table that already has rows.

The migration refuses to run while any existing plan has on_exhaustion = 'slow' with
no slow speeds: it is about to add the slow speeds as NULL, and a CHECK that requires
them for slow plans. Rather than invent speeds, it stops and names the offending
plans. A plan with on_exhaustion = 'stop' is fine, because it correctly has no slow
speeds.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the six new plan columns (with their CHECK constraints),
the five new customer columns, and the three plan CHECK constraints. It REFUSES while
`customer` or `plan` holds any row: the columns carry real data, and dropping them
silently destroys it. With real data, restore from a backup instead. Take a backup
before any downgrade outside a test.

TODO(PRD, decision 3): `id_type` allowed values and `address` format are still open.
The placeholder values here ('NIN', '00000000000', 'unknown', 'unknown@example.invalid')
are demo values, not product decisions.
"""

from alembic import op
import sqlalchemy as sa


revision = "e3b80975b879"
down_revision = "ef28cf85753e"
branch_labels = None
depends_on = None


# --- Placeholder values for backfilling the four required customer columns ---
# These exist so the migration can run on a `customer` table that already has rows.
# The placeholder backfill must not be used on a database with real customers: a real
# deployment must replace them before the pilot; they are not product decisions.
#   email       -> 'unknown@example.invalid'  (an obvious placeholder, not a real address)
#   id_type     -> 'NIN'                     (the demo value from PRODUCT_RULES.md)
#   id_number   -> '00000000000'             (an obvious placeholder, not a real NIN)
#   address     -> 'unknown'                 (PRODUCT_RULES.md leaves the format open)
_BACKFILL_EMAIL = "unknown@example.invalid"
_BACKFILL_ID_TYPE = "NIN"
_BACKFILL_ID_NUMBER = "00000000000"
_BACKFILL_ADDRESS = "unknown"


def upgrade() -> None:
    bind = op.get_bind()

    # Refuse to add the slow-speed CHECK over rows that would violate it. A slow plan
    # must have both slow speeds; the columns do not exist yet, so any existing slow
    # plan will end up with NULL slow speeds and the CHECK will fail. Do not invent
    # speeds: name the offending plans and stop.
    offenders = (
        bind.execute(sa.text("SELECT plan_id FROM plan WHERE on_exhaustion = 'slow'"))
        .scalars()
        .all()
    )
    if offenders:
        raise RuntimeError(
            "refusing to upgrade: plan(s) "
            f"{sorted(offenders)} have on_exhaustion = 'slow' and no slow speeds yet; "
            "the migration would add the slow speeds as NULL and then the CHECK would "
            "fail. Set the slow speeds for those plans, or set on_exhaustion = 'stop', "
            "before upgrading"
        )

    # --- customer: all four columns are required, matching the Customer schema ---
    op.add_column("customer", sa.Column("email", sa.String(length=120), nullable=True))
    op.add_column("customer", sa.Column("id_type", sa.String(length=20), nullable=True))
    op.add_column("customer", sa.Column("id_number", sa.String(length=20), nullable=True))
    op.add_column("customer", sa.Column("address", sa.String(length=500), nullable=True))
    op.execute(
        sa.text(
            "UPDATE customer "
            "SET email = :email, id_type = :id_type, id_number = :id_number, "
            "address = :address"
        ).bindparams(
            email=_BACKFILL_EMAIL,
            id_type=_BACKFILL_ID_TYPE,
            id_number=_BACKFILL_ID_NUMBER,
            address=_BACKFILL_ADDRESS,
        )
    )
    op.alter_column("customer", "email", nullable=False)
    op.alter_column("customer", "id_type", nullable=False)
    op.alter_column("customer", "id_number", nullable=False)
    op.alter_column("customer", "address", nullable=False)

    op.add_column(
        "customer",
        sa.Column("blocked", sa.Boolean(), server_default="false", nullable=False),
    )

    # --- plan: price/validity/data are required, slow_* are nullable with a CHECK,
    # channels is required ---
    op.add_column("plan", sa.Column("price_kobo", sa.BigInteger(), nullable=True))
    op.add_column("plan", sa.Column("validity_days", sa.Integer(), nullable=True))
    op.add_column("plan", sa.Column("data_bytes", sa.BigInteger(), nullable=True))
    op.execute(sa.text("UPDATE plan SET price_kobo = 0, validity_days = 1, data_bytes = 0"))
    op.alter_column("plan", "price_kobo", nullable=False)
    op.alter_column("plan", "validity_days", nullable=False)
    op.alter_column("plan", "data_bytes", nullable=False)

    op.add_column("plan", sa.Column("slow_ul_mbps", sa.Double(), nullable=True))
    op.add_column("plan", sa.Column("slow_dl_mbps", sa.Double(), nullable=True))

    op.add_column("plan", sa.Column("channels", sa.String(length=40), nullable=True))
    op.execute(sa.text("UPDATE plan SET channels = 'data'"))
    op.alter_column("plan", "channels", nullable=False)

    # --- CHECK constraints on plan, matching the bundle constraints ---
    op.create_check_constraint(
        op.f("ck_plan_price_kobo_non_negative"), "plan", "price_kobo >= 0"
    )
    op.create_check_constraint(
        op.f("ck_plan_validity_days_positive"), "plan", "validity_days > 0"
    )
    op.create_check_constraint(
        op.f("ck_plan_data_bytes_non_negative"), "plan", "data_bytes >= 0"
    )
    op.create_check_constraint(
        op.f("ck_plan_slow_speeds_present_only_for_slow"),
        "plan",
        "(on_exhaustion = 'slow' AND slow_ul_mbps IS NOT NULL AND slow_dl_mbps IS NOT NULL) "
        "OR (on_exhaustion <> 'slow' AND slow_ul_mbps IS NULL AND slow_dl_mbps IS NULL)",
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("customer", "plan"):
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError(
                f"refusing to drop {table}: it holds rows; restore from a backup instead"
            )
    op.drop_constraint(
        op.f("ck_plan_slow_speeds_present_only_for_slow"), "plan", type_="check"
    )
    op.drop_constraint(op.f("ck_plan_data_bytes_non_negative"), "plan", type_="check")
    op.drop_constraint(op.f("ck_plan_validity_days_positive"), "plan", type_="check")
    op.drop_constraint(op.f("ck_plan_price_kobo_non_negative"), "plan", type_="check")
    op.drop_column("plan", "channels")
    op.drop_column("plan", "slow_dl_mbps")
    op.drop_column("plan", "slow_ul_mbps")
    op.drop_column("plan", "data_bytes")
    op.drop_column("plan", "validity_days")
    op.drop_column("plan", "price_kobo")
    op.drop_column("customer", "blocked")
    op.drop_column("customer", "address")
    op.drop_column("customer", "id_number")
    op.drop_column("customer", "id_type")
    op.drop_column("customer", "email")