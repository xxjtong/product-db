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


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # 幂等：上一个迁移（fix_explicit_ddl）的显式 DDL 是照当时的模型写的，已含这两列，
    # 全新库跑到这里会报 duplicate column name: is_link
    if not _has_column('product_files', 'is_link'):
        op.add_column('product_files', sa.Column('is_link', sa.Boolean(), nullable=True, server_default=sa.text('0')))
    if not _has_column('product_files', 'link_url'):
        op.add_column('product_files', sa.Column('link_url', sa.String(500), nullable=True))


def downgrade() -> None:
    if _has_column('product_files', 'link_url'):
        op.drop_column('product_files', 'link_url')
    if _has_column('product_files', 'is_link'):
        op.drop_column('product_files', 'is_link')
