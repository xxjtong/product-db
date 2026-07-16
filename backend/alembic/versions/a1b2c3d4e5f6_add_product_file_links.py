"""add_product_file_links

Revision ID: a1b2c3d4e5f6
Revises: fix_create_all_to_explicit_ddl
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('product_files', sa.Column('is_link', sa.Boolean(), nullable=True, server_default=sa.text('0')))
    op.add_column('product_files', sa.Column('link_url', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('product_files', 'link_url')
    op.drop_column('product_files', 'is_link')
