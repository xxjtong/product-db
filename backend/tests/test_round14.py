"""Round 14 回归：列表接口 page / per_page 收口（R77）。

不设上限的隐患不是「请求太多行」这么温和 —— `per_page=-1` 到 SQLite 就是 `LIMIT -1`
即**不限量**，整表灌进内存；品类接口还因为是在内存里切片，`per_page=-1` 会切成
`flat[0:-1]`（全部减一条）这种怪结果。

同时要守住**前端的上限不能被压**：前端最大发 `per_page=1000`（品类全量下拉）、
`500`（字典/产品），产品列表的「全部」选项直接发 `per_page=<total>`。
"""
import os
import tempfile

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
from app.models.supplier import Supplier
from app.models.dictionary import Manufacturer
from app.auth import hash_password, create_token
from app.utils.helpers import clamp_page, MAX_PER_PAGE
from tests.conftest import create_test_schema, drop_test_schema

client = TestClient(app)
API = "/product-db/api"


def _setup():
    drop_test_schema()
    create_test_schema()
    db = SessionLocal()
    try:
        db.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
        cats = [Category(name=f"品类{i}", slug=f"cat-{i}", level=1, sort_order=i) for i in range(3)]
        db.add_all(cats)
        db.flush()
        for i in range(5):
            db.add(Product(name=f"产品{i}", model=f"P-{i}", category_id=cats[0].id, status="active"))
        db.add_all([Manufacturer(name=f"厂商{i}") for i in range(3)])
        db.add_all([Supplier(name=f"供应商{i}") for i in range(2)])
        db.commit()
    finally:
        db.close()


def _headers():
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username="admin").first()
        return {"Authorization": f"Bearer {create_token(u.id, u.username)}"}
    finally:
        db.close()


def _get(path: str):
    resp = client.get(f"{API}{path}", headers=_headers())
    assert resp.status_code == 200, f"{path} → {resp.status_code} {resp.text}"
    return resp.json()


class TestClampPageUnit:
    def test_zero_and_negative_are_pulled_up(self):
        assert clamp_page(0, 0) == (1, 1)
        assert clamp_page(-3, -1) == (1, 1)

    def test_huge_per_page_is_capped(self):
        assert clamp_page(2, 10 ** 9) == (2, MAX_PER_PAGE)

    def test_normal_values_untouched(self):
        assert clamp_page(3, 20) == (3, 20)


class TestListPagingBounds:
    def setup_method(self):
        _setup()

    def teardown_method(self):
        drop_test_schema()

    def test_huge_per_page_is_capped(self):
        body = _get("/products?per_page=100000")
        assert body["per_page"] == MAX_PER_PAGE, "响应里回的应是生效值"
        assert len(body["products"]) <= MAX_PER_PAGE

    def test_negative_per_page_no_longer_means_unlimited(self):
        """`per_page=-1` 改前到 SQLite 是 `LIMIT -1` ＝ 全部；改后应为 1 条。"""
        body = _get("/products?per_page=-1")
        assert body["per_page"] == 1
        assert len(body["products"]) == 1, f"应只剩 1 条，实际 {len(body['products'])}"

    def test_page_zero_does_not_go_negative(self):
        body = _get("/products?page=0&per_page=2")
        assert body["page"] == 1
        assert len(body["products"]) == 2

    def test_dict_negative_per_page(self):
        body = _get("/dicts/manufacturers?per_page=-1")
        assert body["per_page"] == 1
        assert len(body["manufacturers"]) == 1

    def test_categories_negative_per_page_slice(self):
        """品类在内存里切片，改前 `per_page=-1` 会切成 `flat[0:-1]`（全部减一条）。"""
        body = _get("/categories?per_page=-1")
        assert body["per_page"] == 1
        assert len(body["categories"]) == 1, f"应只剩 1 条，实际 {len(body['categories'])}"
        assert body["total"] == 3

    def test_suppliers_all_true_is_bounded(self):
        """`all=true` 改前走 `q.all()` 完全绕过分页，现在取上限值走分页路径。"""
        body = _get("/suppliers?all=true")
        assert body["page"] == 1 and body["per_page"] == MAX_PER_PAGE
        assert body["total"] == 2 and len(body["suppliers"]) == 2

    def test_frontend_max_per_page_is_not_squeezed(self):
        """前端最大会发 per_page=1000（品类全量）—— 上限必须放行它，否则是功能回退。"""
        body = _get("/categories?per_page=1000")
        assert body["per_page"] == 1000
        assert len(body["categories"]) == 3

    def test_solutions_and_quotations_also_bounded(self):
        assert _get("/solutions?per_page=-1")["per_page"] == 1
        assert _get("/quotations?per_page=-1")["per_page"] == 1
