"""lines: staff accounts, their sign-in sessions, and the memory of idempotent creates

Revision ID: 4f6279e32deb
Revises: e75e719550b6
Create Date: 2026-10-27 19:50:52.138826+00:00

`staff_user` holds RatelDesk's staff (a salted scrypt hash of the password, never the password) and
`staff_session` their sign-ins (the SHA-256 of the cookie's value, never the value). Both tables hold
nothing about customers. `idempotent_create` remembers which Idempotency-Key created which record
(only the key and the record's id), so a repeated create returns the first one.

Reviewer checklist: see docs/DATABASE_AND_MIGRATIONS.md.

Rollback: downgrade() drops the three tables. It REFUSES while `staff_user` holds any account, because
the accounts are how people sign in and they would have to be made again by hand. `staff_session` and
`idempotent_create` hold nothing that cannot be rebuilt and are dropped without a check. With
accounts, restore from a backup instead.
"""
from alembic import op
import sqlalchemy as sa


revision = '4f6279e32deb'
down_revision = 'e75e719550b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('idempotent_create',
    sa.Column('scope', sa.String(length=20), nullable=False),
    sa.Column('key', sa.String(length=120), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('scope', 'key', name=op.f('pk_idempotent_create'))
    )
    op.create_table('staff_user',
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('password_hash', sa.String(length=200), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('failed_logins', sa.Integer(), server_default='0', nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('agent', 'admin')", name=op.f('ck_staff_user_role_valid')),
    sa.PrimaryKeyConstraint('staff_id', name=op.f('pk_staff_user')),
    sa.UniqueConstraint('email', name=op.f('uq_staff_user_email'))
    )
    op.create_table('staff_session',
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['staff_id'], ['staff_user.staff_id'], name=op.f('fk_staff_session_staff_id_staff_user'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('session_id', name=op.f('pk_staff_session')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_staff_session_token_hash'))
    )
    op.create_index('ix_staff_session_staff_id', 'staff_session', ['staff_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM staff_user)")).scalar():
        raise RuntimeError(
            "refusing to drop staff_user: it holds accounts people sign in with; "
            "restore from a backup instead"
        )
    op.drop_index('ix_staff_session_staff_id', table_name='staff_session')
    op.drop_table('staff_session')
    op.drop_table('staff_user')
    op.drop_table('idempotent_create')
