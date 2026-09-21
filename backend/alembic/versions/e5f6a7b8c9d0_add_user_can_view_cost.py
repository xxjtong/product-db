"""add users.can_view_cost —— 按用户的成本价可见性覆盖（三态）

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-21

列语义（三态）：
  NULL  = 跟随全局字段开关 field_settings.cost_price（默认，存量用户行为不变）
  True  = 允许看成本
  False = 禁止看成本（即使全局开关打开）

为什么可空且不给 server_default：给了默认值就等于把存量用户一次性改权。
admin 恒可见，不受此列影响；判定统一走 services.field_visibility.cost_visible()。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("users", "can_view_cost"):
        op.add_column("users", sa.Column("can_view_cost", sa.Boolean(), nullable=True))


def downgrade() -> None:
    if _has_column("users", "can_view_cost"):
        op.drop_column("users", "can_view_cost")
