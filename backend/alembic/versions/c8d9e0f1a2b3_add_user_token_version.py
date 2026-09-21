"""add users.token_version —— 让 JWT 可以撤销（登出/改密后立即失效）

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-21

JWT 是无状态的：在此之前全仓没有登出接口，也没有任何撤销手段，改密或管理员重置密码后
旧 token 仍能用满 `JWT_EXPIRE_MINUTES`（默认 24h）。新增 `token_version` 后，
`create_token()` 会把当前版本号写进 payload 的 `ver`，`get_current_user()`
每次校验 `ver == users.token_version`；登出 / 改密 / 管理员重置密码时递增该列，
即一次性作废该用户所有已签发的 token。

`server_default="0"` 是必需的：存量行必须拿到 0，而老 token 没有 `ver` 字段
（按 0 比对）—— 两者相等，所以部署本迁移**不会**把任何已登录用户踢下线。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("users", "token_version"):
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if _has_column("users", "token_version"):
        op.drop_column("users", "token_version")
