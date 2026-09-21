"""测试公共设施。

注意：本文件**不能**在模块顶层 import app.* —— conftest 由 pytest 在收集测试模块
之前加载，此时测试模块里的 `os.environ["DATABASE_URL"] = ...` 还没执行，提前 import
会让 app.database 绑定到真实库。所有 app 相关导入一律放进函数内部（延迟导入）。
"""
from sqlalchemy import text

# 非 ORM 表：product_categories 靠裸 SQL 建，不在 Base.metadata 里。
# FK 必须指向 device_categories（品类表的真实表名）。老夹具写的是 REFERENCES categories(id)
# ——那是不存在的表，外键未强制时没人察觉，R57 开启强制后所有涉及该表的增删都会
# 报 `no such table: main.categories`。DDL 与生产/迁移 d4e5f6a7b8c9 保持一致。
_PRODUCT_CATEGORIES_DDL = (
    "CREATE TABLE IF NOT EXISTS product_categories ("
    "  product_id INTEGER NOT NULL,"
    "  category_id INTEGER NOT NULL,"
    "  PRIMARY KEY (product_id, category_id),"
    "  FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,"
    "  FOREIGN KEY(category_id) REFERENCES device_categories(id) ON DELETE CASCADE"
    ")"
)


def create_test_schema():
    """建 ORM 表 + 非 ORM 的 product_categories。"""
    from app.database import Base, engine

    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text(_PRODUCT_CATEGORIES_DDL))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_pc_category ON product_categories(category_id)"))
        conn.commit()


def drop_test_schema():
    """用例结束后清库：先删裸 SQL 表，再 drop_all 元数据表。

    R57 起 SQLite 外键强制开启，不能再直接 drop_all：product_categories 带 FK 指向
    products，但不在 Base.metadata 里，SQLAlchemy 删父表时不知道要绕开它，隐式 DELETE
    会回查已被删掉的对端表。
    """
    from app.database import Base, engine

    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS product_categories"))
        conn.commit()
    Base.metadata.drop_all(bind=engine)
