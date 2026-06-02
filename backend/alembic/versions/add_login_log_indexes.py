"""Add indexes on login_logs for rate limiting queries.

Revision ID: a1b2c3d4e5f6
Revises: fix_create_all_to_explicit_ddl
Create Date: 2026-06-02

This migration adds two indexes:
- idx_login_logs_ip_success: for _check_rate_limit (filter by ip_address + success)
- idx_login_logs_created: for _check_rate_limit (filter by created_at range)
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'fix_create_all_to_explicit_ddl'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('idx_login_logs_ip_success', 'login_logs', ['ip_address', 'success'])
    op.create_index('idx_login_logs_created', 'login_logs', ['created_at'])


def downgrade():
    op.drop_index('idx_login_logs_created', table_name='login_logs')
    op.drop_index('idx_login_logs_ip_success', table_name='login_logs')
