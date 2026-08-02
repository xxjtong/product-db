"""Sync live schema to models: product_files link columns + login_logs indexes.

The live DBs (dev and production) evolved past the initial migration without
Alembic tracking. Running the historical chain would execute
`fix_explicit_ddl`, which DROPS and recreates every table (data loss), so DBs
are stamped to `b2c3d4e5f6a7` before running this migration. It closes the
remaining gap between models and database:

- product_files.is_link / link_url (used by the file-link feature)
- login_logs rate-limit indexes (idx_login_logs_ip_success, idx_login_logs_created)

The operations are idempotent so the same migration can be applied to DBs
whose columns were already added manually (e.g. production).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-02
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c['name'] for c in sa.inspect(bind).get_columns('product_files')}
    if 'is_link' not in cols:
        op.add_column(
            'product_files',
            sa.Column('is_link', sa.Boolean(), nullable=True, server_default=sa.text('0')),
        )
    if 'link_url' not in cols:
        op.add_column(
            'product_files',
            sa.Column('link_url', sa.String(500), nullable=True),
        )
    op.execute('CREATE INDEX IF NOT EXISTS idx_login_logs_ip_success ON login_logs (ip_address, success)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_login_logs_created ON login_logs (created_at)')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS idx_login_logs_created')
    op.execute('DROP INDEX IF EXISTS idx_login_logs_ip_success')
    bind = op.get_bind()
    cols = {c['name'] for c in sa.inspect(bind).get_columns('product_files')}
    if 'link_url' in cols:
        op.drop_column('product_files', 'link_url')
    if 'is_link' in cols:
        op.drop_column('product_files', 'is_link')
