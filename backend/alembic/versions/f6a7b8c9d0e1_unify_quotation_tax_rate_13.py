"""把报价单税率统一为 13%

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-21

背景：`quotations.tax_rate` 一直落在 0 —— schema/model 默认值都是 0，前端也没有
设置入口（R21 把报价单页的税率/总金额信息行移除了）。而导出的 xlsx 备注行会写
「税率 N%」，于是客户拿到的报价单上印着 **税率 0%**。Hermes 侧创建报价单的脚本
（~/.hermes/scripts/create_quotation.py）反而写 13，两边长期不一致。

本次：
1. 默认值改为 13（`models/quotation.py` + `schemas/quotation.py`）—— 只影响新建
2. 这条迁移把**存量**的 0/NULL 一并改成 13，否则老报价单导出来还是 0%

注意：
- 数据迁移**不可逆**：原始值是 0 还是 NULL 无法区分，且降级时一律写回 0 会把
  「本就该是 13%」的行改错（agent 脚本创建的报价单就是 13），所以 downgrade 不做
  任何事，只保留列结构。
- 新库的列默认仍是历史迁移里的 `server_default="0"`（SQLite 改默认值要重建表，
  而本项目一律由 ORM 显式写入该字段，不值得为此重建）——建新库时若用裸 SQL
  插入报价单请显式写 tax_rate。
"""
from __future__ import annotations

from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None

NEW_RATE = 13


def upgrade() -> None:
    # 幂等：只动 0/NULL，重复执行结果一致
    op.execute(
        f"UPDATE quotations SET tax_rate = {NEW_RATE} "
        f"WHERE tax_rate IS NULL OR tax_rate = 0"
    )


def downgrade() -> None:
    """不还原：见模块 docstring（0 与 NULL 无法区分，且可能误改本就 13% 的行）"""
    pass
