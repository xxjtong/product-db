"""从零建库：迁移链必须能跑通，且建出的结构与生产/模型一致。

回归背景（2026-09-17 实测「全新库 vs 生产库」比对发现）：
- `fix_explicit_ddl` 无条件 `DROP TABLE download_tickets`，而 DownloadTicket 模型
  已在 R27 删除、全新库不会建它 → `alembic upgrade head` 第一步就崩
- `b2c3d4e5f6a7` 无条件 `ADD COLUMN is_link`，而显式 DDL 已含该列 →
  `duplicate column name: is_link`
- 历史迁移链**完全没有** `product_categories`（它不是 ORM 模型）→ 产品按品类过滤、
  产品导入、AI 上下文构建在全新的库上会 `no such table: product_categories`
- 模型 `index=True` 声明的一批索引（含 11 个 created_by）两边都缺
"""
import os
import sqlite3
import tempfile

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-32charmin")
os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.config import settings  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAD_REVISION = "d4e5f6a7b8c9"


def _build_fresh_db() -> str:
    """用迁移链从零建一个库，返回文件路径。"""
    path = tempfile.mktemp(suffix=".db")
    original = settings.DATABASE_URL
    settings.DATABASE_URL = f"sqlite:///{path}"
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    try:
        command.upgrade(cfg, "head")
    finally:
        settings.DATABASE_URL = original
    return path


class TestFreshDatabaseBuild:
    def test_migration_chain_builds_a_usable_schema(self):
        path = _build_fresh_db()
        try:
            con = sqlite3.connect(path)
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}

            # 非 ORM 表必须被建出来，否则全新库上的产品按品类过滤/导入会直接报错
            assert "product_categories" in tables
            # R27 删除的死表不该再出现在全新库
            assert "download_tickets" not in tables
            assert con.execute("SELECT * FROM alembic_version").fetchone()[0] == HEAD_REVISION

            # 迁移期间新增的列
            for table, column in (("products", "created_by"),
                                  ("manufacturers", "sort_order"),
                                  ("quotations", "download_count"),
                                  ("dict_sensor_metrics", "accuracy")):
                cols = {c[1] for c in con.execute(f"PRAGMA table_info('{table}')")}
                assert column in cols, f"{table}.{column} 缺失"

            # 模型声明但曾两边都缺的索引
            idx = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
            for name in ("ix_products_created_by", "ix_solutions_created_by",
                         "ix_manufacturers_created_by", "ix_login_logs_user_id",
                         "idx_pc_category"):
                assert name in idx, f"{name} 缺失"
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_migration_is_idempotent_on_existing_db(self):
        """在已迁移到底的库上重复 upgrade 不应报错（生产部署走的就是这条路）。"""
        path = _build_fresh_db()
        try:
            original = settings.DATABASE_URL
            settings.DATABASE_URL = f"sqlite:///{path}"
            cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
            cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
            try:
                command.upgrade(cfg, "head")  # 第二次
            finally:
                settings.DATABASE_URL = original

            con = sqlite3.connect(path)
            # 重复执行不得产生重复的表/索引
            dupes = con.execute(
                "SELECT name, COUNT(*) c FROM sqlite_master WHERE type='table' "
                "GROUP BY name HAVING c > 1").fetchall()
            assert dupes == []
        finally:
            if os.path.exists(path):
                os.unlink(path)
