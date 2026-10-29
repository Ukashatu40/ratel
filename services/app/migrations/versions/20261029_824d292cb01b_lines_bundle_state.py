"""lines: bundle.state, so a bundle can be retired

Revision ID: 824d292cb01b
Revises: 1e88ea7593b2
Create Date: 2026-10-29 06:52:17.261569+00:00

Adds `state` (`on_sale` or `retired`) to bundle, as plan already has. Every existing bundle is
`on_sale`. A retired bundle is never listed on RatelPay and cannot be bought; allowances already
bought from it stand. The CHECK keeps the value to those two.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the check and the column. It REFUSES while any bundle is retired:
dropping the column would put a retired bundle back on sale. With retired bundles, restore from a
backup or delete them deliberately first.
"""

from alembic import op
import sqlalchemy as sa

revision = "824d292cb01b"
down_revision = "1e88ea7593b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bundle",
        sa.Column("state", sa.String(length=20), server_default="on_sale", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_bundle_state_valid"), "bundle", "state IN ('on_sale', 'retired')"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM bundle WHERE state = 'retired')")).scalar():
        raise RuntimeError(
            "refusing to drop bundle.state: a retired bundle would be put back on sale; "
            "restore from a backup instead"
        )
    op.drop_constraint(op.f("ck_bundle_state_valid"), "bundle", type_="check")
    op.drop_column("bundle", "state")
