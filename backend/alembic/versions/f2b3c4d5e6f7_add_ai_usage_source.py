"""add ai_usage_logs.source —— 记录 /ai/chat 的入口来源

Revision ID: f2b3c4d5e6f7
Revises: e0f1a2b3c4d5
Create Date: 2026-09-22

为什么加：`/ai/chat` 被两个前端入口共用（全局浮窗 `floating` / 方案详情页助手
`solution`），两个入口打同一个端点、用量只记 `operation='chat'` —— 于是
「哪个入口用得多」这种问题从数据上根本答不出来。加一列可空来源即可。

不设 server_default：存量行来源未知，留 NULL 比编一个值诚实。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2b3c4d5e6f7"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("ai_usage_logs", "source"):
        op.add_column("ai_usage_logs", sa.Column("source", sa.String(20), nullable=True))


def downgrade() -> None:
    if _has_column("ai_usage_logs", "source"):
        op.drop_column("ai_usage_logs", "source")
