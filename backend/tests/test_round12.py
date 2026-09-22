"""Round 12 回归：一档收尾小项（R75）。

- 导入的「价格/成本」留空 → 落 `NULL`（未定价），不再一律写 0
- `search_products` 的 min_price / max_price 传反时自动交换（否则 SQL 查不到，
  模型会给出"没有符合的产品"这种假结论）
"""
import os
import tempfile
import json

_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["DEV_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-32charmin"

from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models.user import User
from app.models.product import Product
from app.models.category import Category
from app.auth import hash_password, create_token
from tests.conftest import create_test_schema, drop_test_schema

client = TestClient(app)
API = "/product-db/api"

MAPPING = {"0": "name", "1": "model", "2": "category", "3": "price", "4": "cost"}


def _setup():
    create_test_schema()
    db = SessionLocal()
    if not db.query(User).filter_by(username="admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
    if not db.query(Category).filter_by(name="网关").first():
        db.add(Category(name="网关", slug="gw-price", level=1, sort_order=0))
    db.commit()
    db.close()


def _headers():
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username="admin").first()
        return {"Authorization": f"Bearer {create_token(u.id, u.username)}"}
    finally:
        db.close()


def _import(rows):
    return client.post(f"{API}/products/import-confirm", headers=_headers(),
                       json={"mapping": MAPPING, "rows": rows})


class TestImportPriceSemantics:
    def setup_method(self):
        _setup()

    def teardown_method(self):
        drop_test_schema()

    def test_blank_price_stays_null(self):
        """表格里没填价格 → 存 NULL（未定价），而不是 0。"""
        r = _import([["未定价产品", "NP-1", "网关", "", ""]])
        assert r.status_code == 200 and r.json()["imported"] == 1
        db = SessionLocal()
        try:
            p = db.query(Product).filter_by(model="NP-1").first()
            assert p.base_price is None, "留空应存 NULL"
            assert p.cost_price is None
        finally:
            db.close()

    def test_explicit_zero_is_zero(self):
        """填了 0 就是 0 元 —— 与「没填」是两件事。"""
        r = _import([["零元产品", "ZP-1", "网关", "0", "0"]])
        assert r.status_code == 200
        db = SessionLocal()
        try:
            p = db.query(Product).filter_by(model="ZP-1").first()
            assert p.base_price is not None and float(p.base_price) == 0
            assert p.cost_price is not None and float(p.cost_price) == 0
        finally:
            db.close()

    def test_normal_price_unaffected(self):
        r = _import([["正常产品", "OK-1", "网关", "1200", "800"]])
        assert r.status_code == 200
        db = SessionLocal()
        try:
            p = db.query(Product).filter_by(model="OK-1").first()
            assert float(p.base_price) == 1200 and float(p.cost_price) == 800
        finally:
            db.close()


class TestSearchPriceRange:
    def setup_method(self):
        _setup()
        db = SessionLocal()
        cat = db.query(Category).filter_by(name="网关").first()
        db.add(Product(name="价格区间测试品", model="RANGE-1", category_id=cat.id,
                       base_price=100, status="active"))
        db.commit()
        db.close()

    def teardown_method(self):
        drop_test_schema()

    def test_reversed_range_is_swapped(self):
        """min>max 传反时应自动交换，仍能查到 —— 否则模型会给出「没有符合的产品」这种假结论。"""
        from app.services.ai_tools import execute_tool
        db = SessionLocal()
        try:
            # 传反：min=500 > max=50。交换后区间 50~500 应命中 100 的产品
            res = json.loads(execute_tool(
                "search_products",
                {"keywords": ["价格区间测试品"], "min_price": 500, "max_price": 50},
                db))
            names = [p["name"] for p in res.get("products", [])]
            assert "价格区间测试品" in names, f"交换后应命中，实际 {names}"
        finally:
            db.close()

    def test_normal_range_still_filters(self):
        from app.services.ai_tools import execute_tool
        db = SessionLocal()
        try:
            hit = json.loads(execute_tool(
                "search_products",
                {"keywords": ["价格区间测试品"], "min_price": 50, "max_price": 500}, db))
            assert "价格区间测试品" in [p["name"] for p in hit.get("products", [])]

            miss = json.loads(execute_tool(
                "search_products",
                {"keywords": ["价格区间测试品"], "min_price": 200, "max_price": 500}, db))
            assert "价格区间测试品" not in [p["name"] for p in miss.get("products", [])]
        finally:
            db.close()
