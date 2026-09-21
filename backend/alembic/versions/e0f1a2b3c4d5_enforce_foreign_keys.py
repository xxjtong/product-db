"""enforce foreign keys: 清理存量违规 + 补齐缺失的 ON DELETE（R57）

Revision ID: e0f1a2b3c4d5
Revises: c8d9e0f1a2b3

背景（2026-09 实测）：生产库 42 个外键里有 **21 个没有 ON DELETE 子句** —— 迁移文件里定义了
（`fix_create_all_to_explicit_ddl.py`），但实际表是更早的 DDL 建的，两者漂移了。SQLite 缺省是
NO ACTION，所以一旦开启 `PRAGMA foreign_keys=ON`：
  - 删除用户 → 被 solutions/quotations/products.created_by 等引用 → 直接报错
  - 删除 BOM 模板 → 被 solution_bom_snapshots.template_id 引用 → 直接报错
即「先补 ON DELETE，才谈得上开外键」，否则删除功能会从"静默留孤儿"退化成 500。

本迁移做两件事：
1. **重建 17 张表**补上 ON DELETE（SQLite 不能改外键，只能重建）
2. **清理存量违规**（787 行）：无意义的孤儿行删除；审计类表把指向已删用户的列置 NULL（保留审计）

顺序不能反：`ai_usage_logs.user_id` 原为 NOT NULL，必须先重建去掉 NOT NULL，
才能把它 SET NULL 保留审计记录。重建本身只做 `INSERT INTO tmp SELECT *`，
不校验外键，孤儿行原样带过去，随后由清理步骤处理。

实现策略：**读现有 DDL 文本再改**，而不是从模型重建 —— 保证列、类型、默认值、顺序一字不差
（模型与生产库已有历史漂移）。索引在重建后原样恢复。
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "e0f1a2b3c4d5"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


# --- 1. 存量违规清理 -------------------------------------------------------
# 删除类：父行已不存在，子行没有任何入口能访问到，纯冗余
_DELETES = [
    ("ai_messages", "conversation_id", "ai_conversations"),
    ("product_categories", "product_id", "products"),
    ("product_categories", "category_id", "device_categories"),
    ("product_comm_methods", "product_id", "products"),
    ("product_comm_methods", "method_id", "dict_comm_methods"),
    ("product_comm_protocols", "product_id", "products"),
    ("product_comm_protocols", "protocol_id", "dict_comm_protocols"),
    ("product_power_supplies", "product_id", "products"),
    ("product_power_supplies", "power_id", "dict_power_supplies"),
    ("product_hardware_interfaces", "product_id", "products"),
    ("product_sensor_capabilities", "product_id", "products"),
    ("product_sensor_capabilities", "metric_id", "dict_sensor_metrics"),
    ("product_images", "product_id", "products"),
    ("product_files", "product_id", "products"),
    ("product_dependencies", "product_id", "products"),
    ("product_dependencies", "depends_on_product_id", "products"),
    ("product_dependencies", "depends_on_category_id", "device_categories"),
    ("category_spec_definitions", "category_id", "device_categories"),
    ("solution_items", "solution_id", "solutions"),
    ("solution_bom_snapshots", "solution_id", "solutions"),
    ("quotation_items", "quotation_id", "quotations"),
]

# 置 NULL 类：审计/归属信息，记录本身要留（列可空）
_NULLS = [
    ("login_logs", "user_id", "users"),
    ("ai_usage_logs", "user_id", "users"),
    ("products", "created_by", "users"),
    ("solutions", "created_by", "users"),
    ("quotations", "created_by", "users"),
    ("bom_templates", "created_by", "users"),
    ("manufacturers", "created_by", "users"),
    ("suppliers", "created_by", "users"),
    ("device_categories", "created_by", "users"),
    ("dict_comm_methods", "created_by", "users"),
    ("dict_comm_protocols", "created_by", "users"),
    ("dict_power_supplies", "created_by", "users"),
    ("dict_sensor_metrics", "created_by", "users"),
    ("ai_conversations", "user_id", "users"),   # 先置 NULL 再重建为 CASCADE
    ("download_logs", "user_id", "users"),
]


# --- 2. 各表要补的 ON DELETE（列名 → 动作）---------------------------------
_FK_ACTIONS = {
    "products": {"category_id": "RESTRICT", "manufacturer_id": "SET NULL",
                 "supplier_id": "SET NULL", "parent_id": "SET NULL", "created_by": "SET NULL"},
    "device_categories": {"parent_id": "SET NULL", "created_by": "SET NULL"},
    "ai_conversations": {"user_id": "CASCADE"},
    "ai_usage_logs": {"user_id": "SET NULL"},
    "bom_templates": {"created_by": "SET NULL"},
    "login_logs": {"user_id": "SET NULL"},
    "manufacturers": {"created_by": "SET NULL"},
    "suppliers": {"created_by": "SET NULL"},
    "solutions": {"created_by": "SET NULL"},
    "quotations": {"created_by": "SET NULL"},
    "solution_items": {"product_id": "RESTRICT"},
    "solution_bom_snapshots": {"template_id": "CASCADE"},
    "dict_comm_methods": {"created_by": "SET NULL"},
    "dict_comm_protocols": {"created_by": "SET NULL"},
    "dict_power_supplies": {"created_by": "SET NULL"},
    "dict_sensor_metrics": {"created_by": "SET NULL"},
    "download_logs": {"user_id": "SET NULL"},
    "product_dependencies": {"product_id": "CASCADE", "depends_on_product_id": "CASCADE",
                             "depends_on_category_id": "CASCADE"},
}

# 生产库里压根没有这些外键（表是另一条路径建的/历史漂移），得整条补进去。
# 全新库走 fix_create_all_to_explicit_ddl，那边声明了 REFERENCES 但缺 ON DELETE，
# 由上面的内联正则补 —— 两边最终一致。
_MISSING_FKS = {
    "download_logs": [
        "FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL",
    ],
    "product_dependencies": [
        "FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE",
        "FOREIGN KEY(depends_on_product_id) REFERENCES products(id) ON DELETE CASCADE",
        "FOREIGN KEY(depends_on_category_id) REFERENCES device_categories(id) ON DELETE CASCADE",
    ],
}

# 顺带修正的可空性：这些列原来是 NOT NULL，导致无法用 SET NULL 保留审计
_DROP_NOT_NULL = {("ai_usage_logs", "user_id"), ("download_logs", "user_id")}


def _rows(conn, sql, **params):
    return conn.execute(sa.text(sql), params).fetchall()


def _count(conn, sql):
    return conn.execute(sa.text(sql)).scalar() or 0


def _cleanup(conn) -> list[str]:
    """清理存量违规，返回处理明细（写进迁移日志便于事后核对）。"""
    log = []
    for table, col, parent in _DELETES:
        try:
            n = _count(conn, f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL "
                             f"AND {col} NOT IN (SELECT id FROM {parent})")
        except Exception:
            continue
        if n:
            conn.execute(sa.text(f"DELETE FROM {table} WHERE {col} IS NOT NULL "
                                 f"AND {col} NOT IN (SELECT id FROM {parent})"))
            log.append(f"删除 {table}.{col} 孤儿 {n} 行")

    for table, col, parent in _NULLS:
        n = _count(conn, f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL "
                         f"AND {col} NOT IN (SELECT id FROM {parent})")
        if n:
            conn.execute(sa.text(f"UPDATE {table} SET {col} = NULL WHERE {col} IS NOT NULL "
                                 f"AND {col} NOT IN (SELECT id FROM {parent})"))
            log.append(f"{table}.{col} 置 NULL {n} 行（父行已删，保留记录本身）")
    return log


def _table_ddl(conn, table: str):
    row = conn.execute(sa.text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=:t"), {"t": table}).fetchone()
    # 表不存在（历史链/生产各有各的漂移）→ 返回 None，由调用方跳过，别让迁移直接崩
    if not row or not row[0]:
        return None
    return row[0]


def _index_ddls(conn, table: str) -> list[str]:
    rows = conn.execute(sa.text(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=:t AND sql IS NOT NULL"),
        {"t": table}).fetchall()
    return [r[0] for r in rows]


def _patch_ddl(ddl: str, table: str) -> str:
    """给 DDL 里还没有 ON DELETE 的外键补上策略（表级与内联两种写法都处理）。"""
    actions = _FK_ACTIONS.get(table, {})

    def add(m):
        col = m.group("col")
        action = actions.get(col)
        return m.group(0) + (f" ON DELETE {action}" if action else "")

    # 表级：FOREIGN KEY(col) REFERENCES tbl (id)   —— 只补尚未带 ON DELETE 的
    ddl = re.sub(r"FOREIGN KEY\((?P<col>\w+)\) REFERENCES \w+ ?\(id\)(?! ON DELETE)", add, ddl)
    # 内联：col INTEGER REFERENCES tbl(id)
    ddl = re.sub(r"(?P<col>\w+) (?:INTEGER|INT) REFERENCES \w+\(id\)(?! ON DELETE)", add, ddl)

    # 整条外键都不存在的列：塞进表级约束（放在最后一个 ")" 之前）
    for (tbl, col) in _DROP_NOT_NULL:
        if tbl == table:
            # 去掉该列的 NOT NULL，使其可用 SET NULL 保留审计
            ddl = re.sub(rf"(\b{col}\s+(?:INTEGER|INT))\s+NOT NULL", r"\1", ddl)

    missing = _MISSING_FKS.get(table, [])
    for constraint in missing:
        col = re.search(r"FOREIGN KEY\((\w+)\)", constraint).group(1)
        if not re.search(rf"\b{col}\b[^,)]*REFERENCES", ddl, re.I):
            pos = ddl.rfind(")")
            ddl = f"{ddl[:pos].rstrip()}, {constraint}{ddl[pos:]}"
    return ddl


def _rebuild(conn, table: str) -> None:
    """按修补后的 DDL 重建表：建新表 → 复制数据 → 换名 → 恢复索引。表不存在则跳过。"""
    old_ddl = _table_ddl(conn, table)
    if old_ddl is None:
        return
    new_ddl = _patch_ddl(old_ddl, table)
    if new_ddl == old_ddl:
        return

    tmp = f"{table}__fk_new"
    # 用原 DDL 的形态替换表名（可能带双引号）
    if re.search(rf'CREATE TABLE "{re.escape(table)}"', old_ddl, re.I):
        new_ddl = re.sub(rf'CREATE TABLE "{re.escape(table)}"', f'CREATE TABLE "{tmp}"', new_ddl, count=1, flags=re.I)
    else:
        new_ddl = re.sub(rf"CREATE TABLE {re.escape(table)}\b", f"CREATE TABLE {tmp}", new_ddl, count=1, flags=re.I)

    indexes = _index_ddls(conn, table)
    conn.execute(sa.text(f'DROP TABLE IF EXISTS "{tmp}"'))
    conn.execute(sa.text(new_ddl))
    conn.execute(sa.text(f'INSERT INTO "{tmp}" SELECT * FROM "{table}"'))
    conn.execute(sa.text(f'DROP TABLE "{table}"'))
    conn.execute(sa.text(f'ALTER TABLE "{tmp}" RENAME TO "{table}"'))
    for idx in indexes:
        conn.execute(sa.text(idx))


def upgrade() -> None:
    conn = op.get_bind()

    # 重建期间必须关掉外键检查（SQLite 的 PRAGMA 在事务外生效，Alembic 这里的连接是 autocommit）
    try:
        conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
    except Exception:
        pass

    print("[R57] 重建表并补齐 ON DELETE：")
    for table in _FK_ACTIONS:
        _rebuild(conn, table)
        print("   -", table)

    log = _cleanup(conn)
    print("[R57] 存量违规清理：")
    for line in log:
        print("   -", line)
    if not log:
        print("   - (无)")

    try:
        conn.execute(sa.text("PRAGMA foreign_keys=ON"))
    except Exception:
        pass

    remaining = len(_rows(conn, "PRAGMA foreign_key_check"))
    print(f"[R57] 迁移后 foreign_key_check 剩余违规 = {remaining}")
    if remaining:
        raise RuntimeError(f"仍有 {remaining} 行外键违规，请检查后再开启 PRAGMA foreign_keys")


def downgrade() -> None:
    """不还原。

    数据清理删掉的是**父行已不存在**的孤儿行（无法恢复也无意义）；表重建把缺的 ON DELETE
    补成了设计值。回退只会把库变回不一致状态，因此这里显式不做处理。
    """
    pass
