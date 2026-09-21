"""清理批量删除遗留的孤儿子行（R41）

Revision ID: b7c8d9e0f1a2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-21

背景：`POST /solutions/batch-delete` 与 `/quotations/batch-delete` 原先用
`db.query(...).delete()`（bulk DELETE）。那不会触发 ORM 的 cascade，而 SQLite 的
外键约束在生产**并未启用**（`PRAGMA foreign_keys` 默认关闭，且关闭状态无法直接打开，
见下），于是子行被留在了库里：

  solution_items           50 行父方案已不存在
  solution_bom_snapshots    2 行父方案已不存在
  quotation_items         124 行父报价单已不存在

危害不止是占空间：SQLite 的 `INTEGER PRIMARY KEY` 在没有 AUTOINCREMENT 时会**复用**
被删行的 rowid，新方案/报价单拿到同一个 id 时，这些历史孤儿子行会被静默认领，
凭空出现在新单据里。

**为什么不能顺手把 `PRAGMA foreign_keys` 打开**：生产库 `PRAGMA foreign_key_check`
有 978 行违规，除了上面这三类，还有 `ai_messages` 712、`product_categories` 56、
`login_logs` 19 等 —— 其中 `login_logs`/`ai_usage_logs`/`dict_*` 指向已删用户的那些行
是**审计信息，不该删**。要开启外键得先逐类定策略，属独立事项；在那之前，
批量删除已改为逐条 ORM 删除以自行级联（见 routers 内的注释）。

**不可逆**：本迁移删除的数据无法恢复，`downgrade` 故意留空（与 f6a7b8c9d0e1 一致）。
执行前的库快照见 `deploy/backup-db.sh` 的每日备份。
"""
from __future__ import annotations

from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

# (子表, 外键列, 父表)
_ORPHAN_TARGETS = [
    ("solution_items", "solution_id", "solutions"),
    ("solution_bom_snapshots", "solution_id", "solutions"),
    ("quotation_items", "quotation_id", "quotations"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for table, column, parent in _ORPHAN_TARGETS:
        # 只删「父行已不存在」的子行：它们不属于任何单据，任何接口都读不到
        conn.exec_driver_sql(
            f"DELETE FROM {table} WHERE {column} IS NOT NULL "
            f"AND {column} NOT IN (SELECT id FROM {parent})"
        )


def downgrade() -> None:
    """不还原：删掉的行无法凭本迁移重建。"""
    pass
