"""Converge migration-built schema with the live schema: product_categories + missing columns/indexes.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-17

背景（2026-09-17 实测比对「全新库 vs 生产库」得到）：

历史迁移链是照「已存在的库」写的（见 c3d4e5f6a7b8 的说明），因此
`alembic upgrade head` 从零建出的库与生产/模型不一致：

1. **完全没有 product_categories**：它不是 ORM 模型（靠手工 SQL 建的），
   历史迁移里一处都没有。缺它 → 产品列表按品类过滤、产品导入、AI 上下文
   全部 `no such table: product_categories`
2. **缺 16 处列**：created_by 系列（用户隔离功能加的）+ 字典表的
   description / accuracy / resolution、manufacturers.sort_order、
   quotations.download_count
3. **缺 26 个索引**：模型 `index=True` 声明但生产也缺的 15 个（含 11 个
   created_by）+ 生产手工建而全新库没有的 11 个
4. 反向地，全新库会多出一张死表 download_tickets（DownloadTicket 模型已在
   R27 删除，但历史迁移的显式 DDL 仍会建它）

本迁移**幂等**：
- 生产库上只会补出那 15 个缺失索引（其余分支都命中已存在判断）
- 全新库上补齐全部结构、列与索引，与生产对齐

生产库的 alembic_version 已是 c3d4e5f6a7b8，所以 `upgrade head` 只会执行本迁移，
不会再跑历史链里那个「DROP 全表重建」的 fix_explicit_ddl。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── 全新库缺失的列（生产已有，类型按生产实测的 DDL 原样照搬）──────────────
_MISSING_COLUMNS = [
    ("device_categories", "created_by", "INTEGER"),
    ("manufacturers", "created_by", "INTEGER"),
    ("manufacturers", "sort_order", "INTEGER DEFAULT 0"),
    ("suppliers", "created_by", "INTEGER"),
    ("products", "created_by", "INTEGER"),
    ("quotations", "download_count", "INTEGER DEFAULT 0"),
    ("dict_comm_methods", "created_by", "INTEGER"),
    ("dict_comm_methods", "description", "TEXT DEFAULT ''"),
    ("dict_comm_protocols", "created_by", "INTEGER"),
    ("dict_comm_protocols", "description", "TEXT DEFAULT ''"),
    ("dict_power_supplies", "created_by", "INTEGER"),
    ("dict_power_supplies", "description", "TEXT DEFAULT ''"),
    ("dict_sensor_metrics", "created_by", "INTEGER"),
    ("dict_sensor_metrics", "description", "TEXT DEFAULT ''"),
    ("dict_sensor_metrics", "accuracy", "TEXT DEFAULT ''"),
    ("dict_sensor_metrics", "resolution", "TEXT DEFAULT ''"),
]

# ── 模型 index=True 声明、但生产与全新库都缺的索引 ──────────────────────
_MODEL_INDEXES = [
    ("ix_bom_templates_created_by", "bom_templates", ("created_by",)),
    ("ix_category_spec_definitions_category_id", "category_spec_definitions", ("category_id",)),
    ("ix_device_categories_created_by", "device_categories", ("created_by",)),
    ("ix_device_categories_parent_id", "device_categories", ("parent_id",)),
    ("ix_dict_comm_methods_created_by", "dict_comm_methods", ("created_by",)),
    ("ix_dict_comm_protocols_created_by", "dict_comm_protocols", ("created_by",)),
    ("ix_dict_power_supplies_created_by", "dict_power_supplies", ("created_by",)),
    ("ix_dict_sensor_metrics_created_by", "dict_sensor_metrics", ("created_by",)),
    ("ix_login_logs_user_id", "login_logs", ("user_id",)),
    ("ix_manufacturers_created_by", "manufacturers", ("created_by",)),
    ("ix_products_created_by", "products", ("created_by",)),
    ("ix_quotation_items_quotation_id", "quotation_items", ("quotation_id",)),
    ("ix_quotations_created_by", "quotations", ("created_by",)),
    ("ix_solutions_created_by", "solutions", ("created_by",)),
    ("ix_suppliers_created_by", "suppliers", ("created_by",)),
]

# ── 生产手工建、全新库缺失的索引（让从零建库的查询性能与生产一致）────────
_LIVE_ONLY_INDEXES = [
    ("idx_ai_conv_updated", "ai_conversations", ("updated_at",)),
    ("idx_ai_messages_conv", "ai_messages", ("conversation_id",)),
    ("idx_download_logs_user", "download_logs", ("user_id",)),
    ("idx_login_logs_ip", "login_logs", ("ip_address", "success", "created_at")),
    ("idx_deps_depends_on", "product_dependencies", ("depends_on_product_id",)),
    ("idx_deps_product", "product_dependencies", ("product_id",)),
    ("idx_product_files_product", "product_files", ("product_id",)),
    ("idx_products_status_mfg", "products", ("status", "manufacturer_id")),
    ("idx_quotation_solution", "quotations", ("solution_id",)),
    ("idx_solution_items_product", "solution_items", ("product_id",)),
    ("idx_solution_items_sol", "solution_items", ("solution_id",)),
]


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(insp, table: str) -> bool:
    return table in insp.get_table_names()


def _has_column(insp, table: str, column: str) -> bool:
    return column in {c["name"] for c in insp.get_columns(table)}


def _indexed_columns(insp, table: str) -> set:
    return {tuple(i["column_names"]) for i in insp.get_indexes(table)}


def upgrade() -> None:
    insp = _inspector()

    # 1) product_categories：非 ORM 表，历史迁移链从未创建（列/约束按生产 DDL 照搬）
    if not _has_table(insp, "product_categories"):
        op.execute(sa.text(
            "CREATE TABLE product_categories ("
            "  product_id INTEGER NOT NULL,"
            "  category_id INTEGER NOT NULL,"
            "  PRIMARY KEY (product_id, category_id),"
            "  FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,"
            "  FOREIGN KEY(category_id) REFERENCES device_categories(id) ON DELETE CASCADE"
            ")"
        ))
        op.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS idx_pc_category ON product_categories(category_id)"
        ))

    # 2) 补齐全新库缺失的列
    for table, column, ddl in _MISSING_COLUMNS:
        if _has_table(insp, table) and not _has_column(insp, table, column):
            op.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))

    # 3) 补索引：按「列组合」判断是否已存在，避免同一列上出现两个同义索引
    for name, table, cols in _MODEL_INDEXES + _LIVE_ONLY_INDEXES:
        if not _has_table(insp, table):
            continue
        if tuple(cols) in _indexed_columns(insp, table):
            continue
        op.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS {name} ON {table}({', '.join(cols)})"
        ))

    # 4) 死表：DownloadTicket 模型已在 R27 删除，历史迁移仍会把它建出来
    if _has_table(insp, "download_tickets"):
        op.execute(sa.text("DROP TABLE IF EXISTS download_tickets"))


def downgrade() -> None:
    """只回滚本迁移新建的索引。

    不回滚列与 product_categories：降级时它们可能已经承载了业务数据，
    破坏性回滚的代价远大于收益。
    """
    for name, _table, _cols in _MODEL_INDEXES:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))
