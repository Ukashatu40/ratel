"""bss_lines: bundle check constraints

Revision ID: ef28cf85753e
Revises: 042caad31d0f
Create Date: 2026-10-22 10:00:00.000000+00:00

Database-level CHECK constraints on the bundle table: a price cannot be negative,
a validity period must be at least one day, and data_bytes cannot be negative.
The domain layer rejects these values; the database must too, matching the
`usage_record` pattern.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the three CHECK constraints. Safe even with data:
dropping a CHECK constraint that all rows satisfy is a no-op; if a row violates
it (should not happen), the domain layer still rejects the value on write.
"""

from alembic import op

revision = "ef28cf85753e"
down_revision = "042caad31d0f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        op.f("ck_bundle_price_kobo_non_negative"), "bundle", "price_kobo >= 0"
    )
    op.create_check_constraint(
        op.f("ck_bundle_validity_days_positive"), "bundle", "validity_days > 0"
    )
    op.create_check_constraint(
        op.f("ck_bundle_data_bytes_non_negative"), "bundle", "data_bytes >= 0"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_bundle_data_bytes_non_negative"), "bundle", type_="check")
    op.drop_constraint(op.f("ck_bundle_validity_days_positive"), "bundle", type_="check")
    op.drop_constraint(op.f("ck_bundle_price_kobo_non_negative"), "bundle", type_="check")