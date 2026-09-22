"""Round 13 回归：`suggest_solution` 的 N+1（R76）。

原实现在 `for item in items` 里逐条 `db.query(ProductDependency).filter_by(product_id=...)`
—— 方案有几个条目就查几次依赖。改成一次 `IN` 取回后按 `product_id` 分组，查询数与条目数脱钩。

这里用 SQLAlchemy 的 `before_cursor_execute` 事件**实际数 SQL 条数**来断言
（只看代码"看着像没有循环查询"是不够的）。
"""
import os
import tempfile
from contextlib import contextmanager

_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["DEV_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-32charmin"

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.main import app
from app.models.user import User
from app.models.product import Product
from app.models.category import Category
from app.models.dependency import ProductDependency
from app.models.solution import Solution, SolutionItem
from app.auth import hash_password, create_token
from tests.conftest import create_test_schema, drop_test_schema

client = TestClient(app)
API = "/product-db/api"


@contextmanager
def _count_selects():
    """统计这段窗口内真正下发的 SELECT 条数。"""
    stmts = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip()[:6].upper() == "SELECT":
            stmts.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield stmts
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def _seed_solution(n_items: int) -> int:
    """建 `n_items` 个各自带「需搭配网关」依赖的主机产品，放进一个新方案，返回方案 id。"""
    drop_test_schema()
    create_test_schema()
    db = SessionLocal()
    try:
        admin = User(username="admin", password_hash=hash_password("admin"), role="admin")
        db.add(admin)
        db.flush()

        base = Category(name="主机", slug="host", level=1, sort_order=0)
        gateway = Category(name="网关", slug="gateway", level=1, sort_order=0)
        db.add_all([base, gateway])
        db.flush()

        # 落在网关品类里的候选产品：应该被建议出来
        db.add(Product(name="候选网关", model="GW-1", category_id=gateway.id, status="active"))

        product_ids = []
        for i in range(n_items):
            p = Product(name=f"主机{i}", model=f"H-{i}", category_id=base.id, status="active")
            db.add(p)
            db.flush()
            db.add(ProductDependency(product_id=p.id, depends_on_category_id=gateway.id,
                                     dependency_type="required"))
            product_ids.append(p.id)

        sol = Solution(name=f"方案-{n_items}", created_by=admin.id)
        db.add(sol)
        db.flush()
        for pid in product_ids:
            db.add(SolutionItem(solution_id=sol.id, product_id=pid, quantity=1))
        db.commit()
        return sol.id
    finally:
        db.close()


def _headers() -> dict:
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username="admin").first()
        return {"Authorization": f"Bearer {create_token(u.id, u.username)}"}
    finally:
        db.close()


def _suggest_and_count(n_items: int):
    """跑一次 suggest，返回 (SELECT 条数, 响应体)。"""
    sol_id = _seed_solution(n_items)
    headers = _headers()
    with _count_selects() as stmts:
        resp = client.get(f"{API}/solutions/{sol_id}/suggest", headers=headers)
    assert resp.status_code == 200, resp.text
    return len(stmts), resp.json()


class TestSuggestNoNPlusOne:
    def teardown_method(self):
        drop_test_schema()

    def test_query_count_is_flat_in_item_count(self):
        """条目 1 → 6，SELECT 条数必须**完全不变**（原先每多一个条目就多一次依赖查询）。"""
        one, _ = _suggest_and_count(1)
        six, _ = _suggest_and_count(6)
        assert six == one, f"1 个条目 {one} 条 SELECT，6 个条目 {six} 条 —— 仍随条目数增长"

    def test_query_count_is_flat_at_larger_size(self):
        """再拉大一档（12 个条目）确认不是小样本巧合。"""
        one, _ = _suggest_and_count(1)
        twelve, _ = _suggest_and_count(12)
        assert twelve == one, f"1 个条目 {one} 条 SELECT，12 个条目 {twelve} 条"

    def test_suggestion_behaviour_unchanged(self):
        """行为不变：6 个条目仍带出「缺网关」这一类建议，且候选产品在里面。"""
        _, body = _suggest_and_count(6)
        suggestions = body["suggestions"]
        assert len(suggestions) == 1, f"同一缺失品类应只出一类建议，实际 {suggestions}"
        assert suggestions[0]["missing_category"] == "网关"
        assert "候选网关" in [p["name"] for p in suggestions[0]["products"]]

    def test_no_dependency_means_no_suggestion(self):
        """没有依赖时不产生建议（一次 IN 查询返回空，循环不进入）。"""
        drop_test_schema()
        create_test_schema()
        db = SessionLocal()
        try:
            admin = User(username="admin", password_hash=hash_password("admin"), role="admin")
            db.add(admin)
            db.flush()
            cat = Category(name="主机", slug="host", level=1, sort_order=0)
            db.add(cat)
            db.flush()
            p = Product(name="独立主机", model="S-1", category_id=cat.id, status="active")
            db.add(p)
            db.flush()
            sol = Solution(name="无依赖方案", created_by=admin.id)
            db.add(sol)
            db.flush()
            db.add(SolutionItem(solution_id=sol.id, product_id=p.id, quantity=1))
            db.commit()
            sol_id = sol.id
        finally:
            db.close()

        resp = client.get(f"{API}/solutions/{sol_id}/suggest", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []
