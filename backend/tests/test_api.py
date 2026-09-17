"""Comprehensive test suite for product-db — uses a separate test database."""
import pytest
import os
import json
import tempfile

# Force test DB before any app imports
_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["DEV_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-32charmin"

from fastapi.testclient import TestClient
from app.database import Base, engine, SessionLocal, get_db
from app.main import app
from app.models.user import User
from app.models.category import Category, CategorySpecDefinition
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.dictionary import Manufacturer, DictCommMethod, DictCommProtocol, DictPowerSupply
from app.models.dependency import ProductDependency
from app.models.solution import Solution, SolutionItem
from app.models.quotation import Quotation, QuotationItem
from app.models.bom_template import BOMTemplate, SolutionBOMSnapshot
from app.auth import hash_password, create_token

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables and seed admin user before each test."""
    Base.metadata.create_all(bind=engine)
    # Create product_categories junction table (raw SQL, not in ORM metadata)
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS product_categories (
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                PRIMARY KEY (product_id, category_id)
            )
        '''))
        conn.commit()
    db = SessionLocal()
    if not db.query(User).filter_by(username="admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
        db.commit()
    db.close()
    yield
    # Cleanup: drop and recreate for isolation
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    """Provide a DB session for direct data setup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def auth_headers(db):
    """Return auth headers with a valid JWT."""
    admin = db.query(User).filter_by(username="admin").first()
    token = create_token(admin.id, admin.username)
    return {"Authorization": f"Bearer {token}"}


def _seed_category(db, name="测试品类", slug="test-cat"):
    cat = Category(name=name, slug=slug, level=1, sort_order=0)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _seed_manufacturer(db, name="测试厂商"):
    mfg = Manufacturer(name=name)
    db.add(mfg)
    db.commit()
    db.refresh(mfg)
    return mfg


def _seed_supplier(db, name="测试供应商"):
    s = Supplier(name=name)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _seed_product(db, name="测试产品", model="TEST-001", category_id=1, manufacturer_id=None, supplier_id=None, **kwargs):
    init_kwargs = dict(kwargs)
    p = Product(name=name, model=model, category_id=category_id,
                manufacturer_id=manufacturer_id, supplier_id=supplier_id, **init_kwargs)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ============================================================
# Health
# ============================================================
class TestHealth:
    def test_health(self):
        resp = client.get("/product-db/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ============================================================
# Auth
# ============================================================
class TestAuth:
    def test_login_fail(self):
        resp = client.post("/product-db/api/auth/login", json={"username": "nobody", "password": "wrong"})
        assert resp.status_code == 401

    def test_login_success(self):
        resp = client.post("/product-db/api/auth/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "token" in data

    def test_me(self):
        resp = client.get("/product-db/api/auth/me")
        assert resp.status_code == 200
        assert "user" in resp.json()

    def test_admin_users(self):
        resp = client.get("/product-db/api/admin/users")
        assert resp.status_code == 200


# ============================================================
# Categories
# ============================================================
class TestCategories:
    def test_create_and_list(self, db):
        cat = _seed_category(db)
        resp = client.get("/product-db/api/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(c["name"] == "测试品类" for c in data["categories"])

    def test_tree(self, db):
        _seed_category(db, name="父品类", slug="parent")
        resp = client.get("/product-db/api/categories/tree")
        assert resp.status_code == 200
        assert "tree" in resp.json()

    def test_create_category(self, db):
        resp = client.post("/product-db/api/categories", json={"name": "新建品类", "slug": "new-cat"})
        assert resp.status_code in (200, 201)
        assert resp.json()["category"]["name"] == "新建品类"

    def test_update_category(self, db):
        cat = _seed_category(db)
        resp = client.put(f"/product-db/api/categories/{cat.id}", json={"name": "更新品类"})
        assert resp.status_code == 200
        assert resp.json()["category"]["name"] == "更新品类"

    def test_delete_category(self, db):
        cat = _seed_category(db)
        cat_id = cat.id
        resp = client.delete(f"/product-db/api/categories/{cat_id}")
        assert resp.status_code == 200
        db.expire_all()
        assert db.get(Category, cat_id) is None

    def test_spec_definitions_crud(self, db):
        cat = _seed_category(db)
        # Create
        resp = client.post(f"/product-db/api/categories/{cat.id}/spec-definitions", json={
            "spec_key": "ip_rating", "display_name": "IP等级",
            "spec_type": "enum", "options": ["IP30", "IP65", "IP67"],
        })
        assert resp.status_code in (200, 201)
        sd_id = resp.json()["spec_definition"]["id"]

        # List
        resp = client.get(f"/product-db/api/categories/{cat.id}/spec-definitions")
        assert resp.status_code == 200
        assert len(resp.json()["spec_definitions"]) == 1

        # Update
        resp = client.put(f"/product-db/api/categories/{cat.id}/spec-definitions/{sd_id}",
                          json={"display_name": "防护等级"})
        assert resp.status_code == 200
        assert resp.json()["spec_definition"]["display_name"] == "防护等级"

        # Delete
        resp = client.delete(f"/product-db/api/categories/{cat.id}/spec-definitions/{sd_id}")
        assert resp.status_code == 200


# ============================================================
# Suppliers
# ============================================================
class TestSuppliers:
    def test_create_and_list(self, db):
        _seed_supplier(db)
        resp = client.get("/product-db/api/suppliers")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_search(self, db):
        _seed_supplier(db, name="深圳科技")
        resp = client.get("/product-db/api/suppliers?search=深圳")
        assert resp.status_code == 200
        assert any(s["name"] == "深圳科技" for s in resp.json()["suppliers"])

    def test_update(self, db):
        s = _seed_supplier(db)
        resp = client.put(f"/product-db/api/suppliers/{s.id}", json={"name": "更新供应商"})
        assert resp.status_code == 200
        assert resp.json()["supplier"]["name"] == "更新供应商"

    def test_delete(self, db):
        s = _seed_supplier(db)
        s_id = s.id
        resp = client.delete(f"/product-db/api/suppliers/{s_id}")
        assert resp.status_code == 200
        db.expire_all()
        assert db.get(Supplier, s_id) is None

    def test_404_update(self):
        resp = client.put("/product-db/api/suppliers/99999", json={"name": "x"})
        assert resp.status_code == 404


# ============================================================
# Products
# ============================================================
class TestProducts:
    def test_create_and_list(self, db):
        cat = _seed_category(db)
        _seed_product(db, category_id=cat.id)
        resp = client.get("/product-db/api/products")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_filter_by_category(self, db):
        cat = _seed_category(db)
        _seed_product(db, category_id=cat.id)
        resp = client.get(f"/product-db/api/products?category_id={cat.id}")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_search(self, db):
        cat = _seed_category(db)
        _seed_product(db, name="温度传感器", category_id=cat.id)
        resp = client.get("/product-db/api/products?search=温度")
        assert resp.status_code == 200

    def test_detail(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        resp = client.get(f"/product-db/api/products/{p.id}")
        assert resp.status_code == 200
        assert resp.json()["product"]["name"] == "测试产品"

    def test_detail_404(self):
        resp = client.get("/product-db/api/products/99999")
        assert resp.status_code == 404

    def test_create_product(self, db):
        cat = _seed_category(db)
        mfg = _seed_manufacturer(db)
        resp = client.post("/product-db/api/products", json={
            "name": "新产品", "model": "NEW-01",
            "category_id": cat.id, "manufacturer_id": mfg.id,
            "specs": {"ip_rating": "IP65"},
        })
        assert resp.status_code in (200, 201)
        assert resp.json()["product"]["name"] == "新产品"

    def test_update_product(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        resp = client.put(f"/product-db/api/products/{p.id}", json={"name": "更新产品"})
        assert resp.status_code == 200
        assert resp.json()["product"]["name"] == "更新产品"

    def test_delete_product(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        p_id = p.id
        resp = client.delete(f"/product-db/api/products/{p_id}")
        assert resp.status_code == 200
        db.expire_all()
        assert db.get(Product, p_id) is None

    def test_compare(self, db):
        cat = _seed_category(db)
        p1 = _seed_product(db, name="产品A", model="A", category_id=cat.id, specs={"ip_rating": "IP65"})
        p2 = _seed_product(db, name="产品B", model="B", category_id=cat.id, specs={"ip_rating": "IP67"})
        resp = client.get(f"/product-db/api/products/compare?product_ids={p1.id},{p2.id}")
        assert resp.status_code == 200
        assert "matrix" in resp.json()

    def test_compare_min_ids(self):
        resp = client.get("/product-db/api/products/compare?product_ids=1")
        assert resp.status_code == 400

    def test_spec_sheet(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        resp = client.get(f"/product-db/api/products/{p.id}/spec-sheet")
        assert resp.status_code == 200

    def test_export(self, db):
        cat = _seed_category(db)
        _seed_product(db, category_id=cat.id)
        resp = client.get("/product-db/api/products/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/vnd.openxmlformats")

    def test_ai_fetch_text(self):
        resp = client.post("/product-db/api/products/ai-fetch", json={"text": "UG67 LoRaWAN Gateway IP67 Milesight"})
        assert resp.status_code in (200, 201)
        assert "fetched" in resp.json()

    def test_ai_fetch_empty(self):
        resp = client.post("/product-db/api/products/ai-fetch", json={"url": "", "text": ""})
        assert resp.status_code == 400


# ============================================================
# Product Dependencies
# ============================================================
class TestDependencies:
    def test_create_and_list(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        target_cat = _seed_category(db, name="网关", slug="gateway")
        resp = client.post(f"/product-db/api/products/{p.id}/dependencies", json={
            "depends_on_category_id": target_cat.id,
            "dependency_type": "required",
            "description": "需要网关",
        })
        assert resp.status_code in (200, 201)
        dep_id = resp.json()["dependency"]["id"]

        resp = client.get(f"/product-db/api/products/{p.id}/dependencies")
        assert resp.status_code == 200
        assert len(resp.json()["dependencies"]) == 1

    def test_update_dependency(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        target_cat = _seed_category(db, name="网关", slug="gateway")
        dep = ProductDependency(product_id=p.id, depends_on_category_id=target_cat.id,
                                dependency_type="required")
        db.add(dep)
        db.commit()
        db.refresh(dep)

        resp = client.put(f"/product-db/api/products/{p.id}/dependencies/{dep.id}",
                          json={"dependency_type": "recommended"})
        assert resp.status_code == 200
        assert resp.json()["dependency"]["dependency_type"] == "recommended"

    def test_delete_dependency(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        target_cat = _seed_category(db, name="网关", slug="gateway")
        dep = ProductDependency(product_id=p.id, depends_on_category_id=target_cat.id,
                                dependency_type="required")
        db.add(dep)
        db.commit()
        db.refresh(dep)
        dep_id = dep.id

        resp = client.delete(f"/product-db/api/products/{p.id}/dependencies/{dep_id}")
        assert resp.status_code == 200
        db.expire_all()
        assert db.get(ProductDependency, dep_id) is None


# ============================================================
# Solutions
# ============================================================
class TestSolutions:
    def test_create_and_list(self, db):
        resp = client.post("/product-db/api/solutions", json={"name": "测试方案"})
        assert resp.status_code in (200, 201)
        sol_id = resp.json()["solution"]["id"]

        resp = client.get("/product-db/api/solutions")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_solution(self, db):
        resp = client.post("/product-db/api/solutions", json={"name": "方案详情"})
        sol_id = resp.json()["solution"]["id"]

        resp = client.get(f"/product-db/api/solutions/{sol_id}")
        assert resp.status_code in (200, 201)
        assert resp.json()["solution"]["name"] == "方案详情"

    def test_update_solution(self, db):
        resp = client.post("/product-db/api/solutions", json={"name": "原始方案"})
        sol_id = resp.json()["solution"]["id"]

        resp = client.put(f"/product-db/api/solutions/{sol_id}", json={"name": "更新方案"})
        assert resp.status_code in (200, 201)
        assert resp.json()["solution"]["name"] == "更新方案"

    def test_delete_solution(self, db):
        resp = client.post("/product-db/api/solutions", json={"name": "删除方案"})
        sol_id = resp.json()["solution"]["id"]

        resp = client.delete(f"/product-db/api/solutions/{sol_id}")
        assert resp.status_code in (200, 201)

    def test_solution_items_crud(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)

        # Create solution
        resp = client.post("/product-db/api/solutions", json={"name": "BOM方案"})
        sol_id = resp.json()["solution"]["id"]

        # Add item
        resp = client.post(f"/product-db/api/solutions/{sol_id}/items", json={
            "product_id": p.id, "quantity": 2, "unit_price": 1500,
        })
        assert resp.status_code in (200, 201)
        item_id = resp.json()["item"]["id"]

        # List items
        resp = client.get(f"/product-db/api/solutions/{sol_id}/items")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

        # Update item
        resp = client.put(f"/product-db/api/solutions/{sol_id}/items/{item_id}",
                          json={"quantity": 5})
        assert resp.status_code == 200
        assert resp.json()["item"]["quantity"] == 5

        # Delete item
        resp = client.delete(f"/product-db/api/solutions/{sol_id}/items/{item_id}")
        assert resp.status_code == 200


# ============================================================
# Solution Check & Suggest
# ============================================================
class TestSolutionCheck:
    def test_check_no_warnings(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)

        resp = client.post("/product-db/api/solutions", json={"name": "完整方案"})
        sol_id = resp.json()["solution"]["id"]

        client.post(f"/product-db/api/solutions/{sol_id}/items", json={
            "product_id": p.id, "quantity": 1,
        })

        resp = client.get(f"/product-db/api/solutions/{sol_id}/check")
        assert resp.status_code in (200, 201)
        assert resp.json()["ok"] is True
        assert len(resp.json()["warnings"]) == 0

    def test_check_missing_dependency(self, db):
        cat = _seed_category(db)
        gateway_cat = _seed_category(db, name="网关", slug="gateway")
        sensor = _seed_product(db, name="传感器", category_id=cat.id)

        # Add required dependency: sensor needs a gateway
        dep = ProductDependency(product_id=sensor.id, depends_on_category_id=gateway_cat.id,
                                dependency_type="required", description="需要LoRaWAN网关")
        db.add(dep)
        db.commit()

        # Create solution with only sensor (no gateway)
        resp = client.post("/product-db/api/solutions", json={"name": "缺网关方案"})
        sol_id = resp.json()["solution"]["id"]
        client.post(f"/product-db/api/solutions/{sol_id}/items", json={
            "product_id": sensor.id, "quantity": 10,
        })

        resp = client.get(f"/product-db/api/solutions/{sol_id}/check")
        assert resp.status_code in (200, 201)
        assert resp.json()["ok"] is False
        assert len(resp.json()["warnings"]) >= 1
        assert resp.json()["warnings"][0]["type"] == "missing_category"

    def test_suggest_fulfills_dependency(self, db):
        cat = _seed_category(db)
        gateway_cat = _seed_category(db, name="网关", slug="gateway")
        sensor = _seed_product(db, name="传感器", category_id=cat.id)
        gateway = _seed_product(db, name="UG65网关", model="UG65", category_id=gateway_cat.id,
                                specs={"max_endpoints": 500})

        dep = ProductDependency(product_id=sensor.id, depends_on_category_id=gateway_cat.id,
                                dependency_type="required")
        db.add(dep)
        db.commit()

        resp = client.post("/product-db/api/solutions", json={"name": "需推荐方案"})
        sol_id = resp.json()["solution"]["id"]
        client.post(f"/product-db/api/solutions/{sol_id}/items", json={
            "product_id": sensor.id, "quantity": 5,
        })

        resp = client.get(f"/product-db/api/solutions/{sol_id}/suggest")
        assert resp.status_code in (200, 201)
        suggestions = resp.json()["suggestions"]
        assert len(suggestions) >= 1
        assert suggestions[0]["missing_category"] == "网关"
        assert any(prod["name"] == "UG65网关" for prod in suggestions[0]["products"])


# ============================================================
# Quotations
# ============================================================
class TestQuotations:
    def test_create_and_list(self, db):
        resp = client.post("/product-db/api/quotations", json={"title": "测试报价单"})
        assert resp.status_code in (200, 201)
        qt = resp.json()["quotation"]
        assert qt["title"] == "测试报价单"
        assert qt["quote_number"].startswith("QT-")

        resp = client.get("/product-db/api/quotations")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_create_from_solution(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        p.base_price = 1500
        db.commit()

        sol = Solution(name="方案A", client_name="客户甲")
        db.add(sol)
        db.commit()
        db.refresh(sol)

        item = SolutionItem(solution_id=sol.id, product_id=p.id, quantity=2,
                            unit_price=1500, discount_rate=100)
        db.add(item)
        db.commit()

        resp = client.post("/product-db/api/quotations", json={
            "solution_id": sol.id,
            "title": "从方案创建",
        })
        assert resp.status_code in (200, 201)
        qt = resp.json()["quotation"]
        assert qt["client_name"] == "客户甲"

    def test_update_quotation(self, db):
        resp = client.post("/product-db/api/quotations", json={"title": "原始报价"})
        qt_id = resp.json()["quotation"]["id"]

        resp = client.put(f"/product-db/api/quotations/{qt_id}", json={"title": "更新报价"})
        assert resp.status_code in (200, 201)
        assert resp.json()["quotation"]["title"] == "更新报价"

    def test_delete_quotation(self, db):
        resp = client.post("/product-db/api/quotations", json={"title": "删除报价"})
        qt_id = resp.json()["quotation"]["id"]

        resp = client.delete(f"/product-db/api/quotations/{qt_id}")
        assert resp.status_code in (200, 201)

    def test_quotation_items_crud(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        p.base_price = 100
        db.commit()

        resp = client.post("/product-db/api/quotations", json={"title": "报价项测试"})
        qt_id = resp.json()["quotation"]["id"]

        # Add item
        resp = client.post(f"/product-db/api/quotations/{qt_id}/items", json={
            "product_id": p.id, "quantity": 3, "unit_price": 100,
        })
        assert resp.status_code in (200, 201)
        item_id = resp.json()["item"]["id"]

        # List
        resp = client.get(f"/product-db/api/quotations/{qt_id}/items")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

        # Update
        resp = client.put(f"/product-db/api/quotations/{qt_id}/items/{item_id}",
                          json={"quantity": 5})
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/product-db/api/quotations/{qt_id}/items/{item_id}")
        assert resp.status_code == 200

    def test_export_xlsx(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        p.base_price = 200
        db.commit()

        resp = client.post("/product-db/api/quotations", json={"title": "导出测试"})
        qt_id = resp.json()["quotation"]["id"]
        client.post(f"/product-db/api/quotations/{qt_id}/items", json={
            "product_id": p.id, "quantity": 1, "unit_price": 200,
        })

        resp = client.get(f"/product-db/api/quotations/{qt_id}/export-xlsx")
        assert resp.status_code in (200, 201)
        assert resp.headers["content-type"].startswith("application/vnd.openxmlformats")


# ============================================================
# BOM Templates
# ============================================================
class TestBOMTemplates:
    def test_create_and_list(self, db):
        resp = client.post("/product-db/api/bom-templates", json={
            "name": "标准模板", "snapshot": {"cells": {"A1": {"v": "标题"}}},
        })
        assert resp.status_code in (200, 201)
        t_id = resp.json()["template"]["id"]

        resp = client.get("/product-db/api/bom-templates")
        assert resp.status_code == 200
        assert len(resp.json()["templates"]) >= 1

    def test_get_template(self, db):
        resp = client.post("/product-db/api/bom-templates", json={
            "name": "查询模板", "snapshot": {},
        })
        t_id = resp.json()["template"]["id"]

        resp = client.get(f"/product-db/api/bom-templates/{t_id}")
        assert resp.status_code in (200, 201)
        assert resp.json()["template"]["name"] == "查询模板"

    def test_update_template(self, db):
        resp = client.post("/product-db/api/bom-templates", json={
            "name": "旧模板", "snapshot": {},
        })
        t_id = resp.json()["template"]["id"]

        resp = client.put(f"/product-db/api/bom-templates/{t_id}", json={"name": "新模板"})
        assert resp.status_code in (200, 201)
        assert resp.json()["template"]["name"] == "新模板"

    def test_delete_template(self, db):
        resp = client.post("/product-db/api/bom-templates", json={
            "name": "删除模板", "snapshot": {},
        })
        t_id = resp.json()["template"]["id"]

        resp = client.delete(f"/product-db/api/bom-templates/{t_id}")
        assert resp.status_code in (200, 201)

    def test_duplicate_template(self, db):
        resp = client.post("/product-db/api/bom-templates", json={
            "name": "原始模板", "snapshot": {"cells": {"A1": {"v": "x"}}},
        })
        t_id = resp.json()["template"]["id"]

        resp = client.post(f"/product-db/api/bom-templates/{t_id}/duplicate")
        assert resp.status_code in (200, 201)
        assert "副本" in resp.json()["template"]["name"]


# ============================================================
# BOM Snapshots
# ============================================================
class TestBOMSnapshots:
    def test_get_bom_snapshot_generates_from_template(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)

        # Create default template
        client.post("/product-db/api/bom-templates", json={
            "name": "默认模板", "snapshot": {"cells": {"A1": {"v": "BOM"}}}, "is_default": True,
        })

        # Create solution with item
        resp = client.post("/product-db/api/solutions", json={"name": "BOM方案"})
        sol_id = resp.json()["solution"]["id"]
        client.post(f"/product-db/api/solutions/{sol_id}/items", json={
            "product_id": p.id, "quantity": 2, "unit_price": 100,
        })

        # Get snapshot (auto-generated)
        resp = client.get(f"/product-db/api/solutions/{sol_id}/bom-snapshot")
        assert resp.status_code in (200, 201)
        assert "bom_snapshot" in resp.json()
        # Header row is now overwritten with unified layout
        assert resp.json()["bom_snapshot"]["snapshot"]["cells"]["A1"]["v"] == "#"
        # Data row should have product info
        cells = resp.json()["bom_snapshot"]["snapshot"]["cells"]
        assert cells["B3"]["v"] == "测试产品"  # product name in data row

    def test_save_bom_snapshot(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)

        resp = client.post("/product-db/api/solutions", json={"name": "快照方案"})
        sol_id = resp.json()["solution"]["id"]

        # Save snapshot
        resp = client.put(f"/product-db/api/solutions/{sol_id}/bom-snapshot", json={
            "snapshot": {"cells": {"A1": {"v": "自定义内容"}}},
        })
        assert resp.status_code in (200, 201)

        # Read back
        resp = client.get(f"/product-db/api/solutions/{sol_id}/bom-snapshot")
        assert resp.status_code == 200
        assert resp.json()["bom_snapshot"]["snapshot"]["cells"]["A1"]["v"] == "自定义内容"

    def test_save_as_template(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)

        resp = client.post("/product-db/api/solutions", json={"name": "另存模板方案"})
        sol_id = resp.json()["solution"]["id"]

        client.put(f"/product-db/api/solutions/{sol_id}/bom-snapshot", json={
            "snapshot": {"cells": {"A1": {"v": "另存测试"}}},
        })

        resp = client.post(f"/product-db/api/solutions/{sol_id}/bom-snapshot/save-as-template", json={
            "name": "从快照创建模板",
        })
        assert resp.status_code in (200, 201)
        assert resp.json()["template"]["name"] == "从快照创建模板"

    def test_export_bom_xlsx(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)

        resp = client.post("/product-db/api/solutions", json={"name": "导出BOM方案"})
        sol_id = resp.json()["solution"]["id"]
        client.post(f"/product-db/api/solutions/{sol_id}/items", json={
            "product_id": p.id, "quantity": 1, "unit_price": 500,
        })

        resp = client.get(f"/product-db/api/solutions/{sol_id}/bom-snapshot/export-xlsx")
        assert resp.status_code in (200, 201)
        assert resp.headers["content-type"].startswith("application/vnd.openxmlformats")


# ============================================================
# Dictionaries
# ============================================================
class TestDictionaries:
    def test_comm_methods(self, db):
        db.add(DictCommMethod(name="Ethernet", method_type="wired"))
        db.commit()
        resp = client.get("/product-db/api/dicts/comm-methods")
        assert resp.status_code == 200

    def test_comm_protocols(self, db):
        db.add(DictCommProtocol(name="MQTT"))
        db.commit()
        resp = client.get("/product-db/api/dicts/comm-protocols")
        assert resp.status_code == 200

    def test_manufacturers(self, db):
        _seed_manufacturer(db)
        resp = client.get("/product-db/api/dicts/manufacturers")
        assert resp.status_code == 200


# ============================================================
# AI Chat
# ============================================================
class TestAI:
    def test_chat_no_input(self):
        resp = client.post("/product-db/api/ai/chat", json={"input": ""})
        assert resp.status_code == 400

    def test_conversations(self):
        resp = client.get("/product-db/api/ai/conversations")
        assert resp.status_code in (200, 201)


# ============================================================
# Settings
# ============================================================
class TestSettings:
    def test_list(self):
        resp = client.get("/product-db/api/settings")
        assert resp.status_code == 200


# ============================================================
# Import Preview
# ============================================================
class TestImport:
    def test_import_preview_no_file(self):
        resp = client.post("/product-db/api/products/import-preview")
        assert resp.status_code == 422


# ============================================================
# Spec Validation (unit test)
# ============================================================
class TestSpecValidation:
    def test_validate_enum(self, db):
        cat = _seed_category(db)
        sd = CategorySpecDefinition(
            category_id=cat.id, spec_key="ip_rating", display_name="IP等级",
            spec_type="enum", options=["IP30", "IP65", "IP67"],
        )
        db.add(sd)
        db.commit()

        from app.services.spec_service import validate_specs
        errors = validate_specs({"ip_rating": "IP65"}, [sd])
        assert len(errors) == 0

        errors = validate_specs({"ip_rating": "IP99"}, [sd])
        assert len(errors) == 1

    def test_validate_number(self, db):
        cat = _seed_category(db)
        sd = CategorySpecDefinition(
            category_id=cat.id, spec_key="weight_g", display_name="重量",
            spec_type="number", validation={"min": 0, "max": 50000},
        )
        db.add(sd)
        db.commit()

        from app.services.spec_service import validate_specs
        errors = validate_specs({"weight_g": 500}, [sd])
        assert len(errors) == 0

        errors = validate_specs({"weight_g": 99999}, [sd])
        assert len(errors) == 1

    def test_validate_boolean(self, db):
        cat = _seed_category(db)
        sd = CategorySpecDefinition(
            category_id=cat.id, spec_key="has_display", display_name="显示屏",
            spec_type="boolean",
        )
        db.add(sd)
        db.commit()

        from app.services.spec_service import validate_specs
        errors = validate_specs({"has_display": True}, [sd])
        assert len(errors) == 0

        errors = validate_specs({"has_display": "yes"}, [sd])
        assert len(errors) == 1


class TestFieldVisibility:
    """Test that field visibility settings hide sensitive fields from non-admin users."""

    def _make_user(self, db, username="normal", role="user"):
        from app.auth import hash_password
        u = User(username=username, password_hash=hash_password("test123"), role=role)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def _auth_for(self, user):
        token = create_token(user.id, user.username)
        return {"Authorization": f"Bearer {token}"}

    def _seed_field_setting(self, db, field_name, user_visible):
        from app.models.field_setting import FieldSetting
        fs = db.query(FieldSetting).filter_by(field_name=field_name).first()
        if fs:
            fs.user_visible = user_visible
        else:
            db.add(FieldSetting(field_name=field_name, user_visible=user_visible))
        db.commit()

    def _clear_field_settings(self, db):
        from app.models.field_setting import FieldSetting
        db.query(FieldSetting).delete()
        db.commit()
        # Clear cache
        from app.services.field_visibility import _cache
        _cache["ts"] = 0
        _cache["data"] = None

    def test_list_hides_cost_price_for_user(self, db):
        """GET /products hides cost_price when field visible=false for non-admin."""
        self._clear_field_settings(db)
        self._seed_field_setting(db, "cost_price", False)
        cat = _seed_category(db)
        _seed_product(db, category_id=cat.id, cost_price=999.99)

        # Admin sees cost_price
        admin = db.query(User).filter_by(username="admin").first()
        res = client.get("/product-db/api/products", headers=self._auth_for(admin))
        assert res.status_code == 200
        assert res.json()["products"][0]["cost_price"] == 999.99

        # Normal user should NOT see cost_price
        user = self._make_user(db)
        res = client.get("/product-db/api/products", headers=self._auth_for(user))
        assert res.status_code == 200
        assert res.json()["products"][0]["cost_price"] is None

    def test_detail_hides_cost_price_for_user(self, db):
        """GET /products/{id} hides cost_price when field visible=false for non-admin."""
        self._clear_field_settings(db)
        self._seed_field_setting(db, "cost_price", False)
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id, cost_price=888.88)

        # Admin sees cost_price
        admin = db.query(User).filter_by(username="admin").first()
        res = client.get(f"/product-db/api/products/{p.id}", headers=self._auth_for(admin))
        assert res.status_code == 200
        assert res.json()["product"]["cost_price"] == 888.88

        # Normal user should NOT see cost_price
        user = self._make_user(db)
        res = client.get(f"/product-db/api/products/{p.id}", headers=self._auth_for(user))
        assert res.status_code == 200
        assert res.json()["product"]["cost_price"] is None

    def test_detail_shows_cost_price_when_visible(self, db):
        """GET /products/{id} shows cost_price when field visible=true for non-admin."""
        self._clear_field_settings(db)
        self._seed_field_setting(db, "cost_price", True)
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id, cost_price=777.77)

        user = self._make_user(db)
        res = client.get(f"/product-db/api/products/{p.id}", headers=self._auth_for(user))
        assert res.status_code == 200
        assert res.json()["product"]["cost_price"] == 777.77

    def test_quotation_snapshot_hides_cost_price_for_user(self, db):
        """Quotation item snapshot + BOM must hide cost_price when field visible=false."""
        self._clear_field_settings(db)
        self._seed_field_setting(db, "cost_price", False)
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id, base_price=100, cost_price=66.6)
        admin = db.query(User).filter_by(username="admin").first()
        user = self._make_user(db)

        # User creates own quotation with a product item (snapshot contains cost internally)
        res = client.post("/product-db/api/quotations", json={"title": "T"}, headers=self._auth_for(user))
        assert res.status_code == 201
        qid = res.json()["quotation"]["id"]
        res = client.post(
            f"/product-db/api/quotations/{qid}/items",
            json={"product_id": p.id, "quantity": 1, "unit_price": 50},
            headers=self._auth_for(user),
        )
        assert res.status_code == 201

        # User must NOT see cost_price in the quotation snapshot
        res = client.get(f"/product-db/api/quotations/{qid}", headers=self._auth_for(user))
        assert res.status_code == 200
        snap = res.json()["quotation"]["items"][0]["product_snapshot"]
        assert "cost_price" not in snap

        # Items endpoint must not leak cost_price either
        res = client.get(f"/product-db/api/quotations/{qid}/items", headers=self._auth_for(user))
        assert res.status_code == 200
        snap = res.json()["items"][0]["product_snapshot"]
        assert "cost_price" not in snap

        # BOM rows must not expose cost
        res = client.get(f"/product-db/api/quotations/{qid}/bom", headers=self._auth_for(user))
        assert res.status_code == 200
        assert res.json()["rows"][0].get("cost") is None

        # Admin still sees cost_price
        res = client.get(f"/product-db/api/quotations/{qid}", headers=self._auth_for(admin))
        assert res.status_code == 200
        snap = res.json()["quotation"]["items"][0]["product_snapshot"]
        assert snap.get("cost_price") == 66.6

    def test_bom_snapshot_and_export_hide_cost_for_user(self, db):
        """BOM 快照与 xlsx 导出也必须遵守字段可见性。

        回归：`get_bom_snapshot` 原样返回快照、`export_bom_xlsx` 在「有快照」的分支
        里完全不看 show_cost，而快照的 J 列固定写死每个产品的 cost_price →
        管理员关掉成本可见性后，普通用户照样能拿到逐条成本。
        """
        import io
        import openpyxl

        self._clear_field_settings(db)
        self._seed_field_setting(db, "cost_price", False)
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id, base_price=100, cost_price=66.6)
        user = self._make_user(db)
        admin = db.query(User).filter_by(username="admin").first()

        res = client.post("/product-db/api/solutions", json={"name": "BOM 成本"},
                          headers=self._auth_for(user))
        assert res.status_code in (200, 201), res.text
        sid = res.json()["solution"]["id"]
        res = client.post(f"/product-db/api/solutions/{sid}/items",
                          json={"product_id": p.id, "quantity": 2, "unit_price": 50},
                          headers=self._auth_for(user))
        assert res.status_code in (200, 201), res.text

        # 快照（首次读会生成并落库）：普通用户看不到 J 列，其它列不受影响
        res = client.get(f"/product-db/api/solutions/{sid}/bom-snapshot",
                         headers=self._auth_for(user))
        assert res.status_code == 200
        cells = res.json()["bom_snapshot"]["snapshot"]["cells"]
        assert not [k for k in cells if k.startswith("J")], "快照不得含成本列"
        assert cells.get("B1", {}).get("v") == "产品名称", "其它列必须保留"

        # 导出走的是「已有快照」分支，正是历史上漏过滤的那条
        res = client.get(f"/product-db/api/solutions/{sid}/bom-snapshot/export-xlsx",
                         headers=self._auth_for(user))
        assert res.status_code == 200
        ws = openpyxl.load_workbook(io.BytesIO(res.content)).active
        assert ws["J3"].value in (None, ""), "导出不得含成本值"
        assert ws["B3"].value == p.name, "导出仍需包含产品行"

        # admin 照旧能拿到成本
        res = client.get(f"/product-db/api/solutions/{sid}/bom-snapshot",
                         headers=self._auth_for(admin))
        assert res.status_code == 200
        admin_cells = res.json()["bom_snapshot"]["snapshot"]["cells"]
        assert any(k.startswith("J") for k in admin_cells), "admin 仍应看到成本列"
        assert admin_cells["J3"]["v"] == 66.6

    def test_admin_always_sees_cost_price(self, db):
        """Admin sees cost_price regardless of field visibility setting."""
        self._clear_field_settings(db)
        self._seed_field_setting(db, "cost_price", False)
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id, cost_price=555.55)

        admin = db.query(User).filter_by(username="admin").first()
        res = client.get(f"/product-db/api/products/{p.id}", headers=self._auth_for(admin))
        assert res.status_code == 200
        assert res.json()["product"]["cost_price"] == 555.55

    def test_session_returns_field_visibility_for_user(self, db):
        """GET /auth/session returns field_visibility for non-admin, empty for admin."""
        self._clear_field_settings(db)
        self._seed_field_setting(db, "cost_price", False)
        self._seed_field_setting(db, "manufacturer_name", True)

        # Non-admin gets field_visibility dict
        user = self._make_user(db)
        res = client.get("/product-db/api/auth/session", headers=self._auth_for(user))
        assert res.status_code == 200
        fv = res.json()["field_visibility"]
        assert fv["cost_price"] is False
        assert fv["manufacturer_name"] is True

        # Admin gets empty dict (sees everything)
        admin = db.query(User).filter_by(username="admin").first()
        res = client.get("/product-db/api/auth/session", headers=self._auth_for(admin))
        assert res.status_code == 200
        assert res.json()["field_visibility"] == {}

    def test_no_field_settings_defaults_visible(self, db):
        """When no FieldSetting rows exist, all fields default to visible."""
        self._clear_field_settings(db)
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id, cost_price=333.33)

        # Admin endpoint auto-creates defaults, but regular endpoints
        # just pass through (filter_fields_for_user has nothing to hide)
        user = self._make_user(db)
        res = client.get(f"/product-db/api/products/{p.id}", headers=self._auth_for(user))
        assert res.status_code == 200
        # Without field settings, no fields are filtered
        assert res.json()["product"]["cost_price"] == 333.33


class TestOwnershipGaps:
    """Ownership checks that were missing: dependencies, export, compare."""

    def _make_user(self, db, username):
        u = User(username=username, password_hash=hash_password("test123"), role="user")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def _auth_for(self, user):
        return {"Authorization": f"Bearer {create_token(user.id, user.username)}"}

    def test_non_admin_cannot_modify_others_product_dependencies(self, db):
        """Dependency create/update/delete must enforce product ownership."""
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)  # created_by NULL → admin/legacy
        # Give the product an explicit owner for a clean 403 scenario
        p.created_by = 1
        db.commit()

        user = self._make_user(db, "dep_user")
        headers = self._auth_for(user)

        res = client.post(
            f"/product-db/api/products/{p.id}/dependencies",
            json={"depends_on_category_id": cat.id, "dependency_type": "required"},
            headers=headers,
        )
        assert res.status_code == 403, res.text

    def test_non_admin_cannot_update_or_delete_others_dependencies(self, db):
        """Existing dependency owned by another user's product must be 403."""
        from app.models.dependency import ProductDependency
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        p.created_by = 1
        db.commit()
        dep = ProductDependency(product_id=p.id, depends_on_category_id=cat.id, dependency_type="required")
        db.add(dep)
        db.commit()
        db.refresh(dep)

        user = self._make_user(db, "dep_user2")
        headers = self._auth_for(user)

        res = client.put(
            f"/product-db/api/products/{p.id}/dependencies/{dep.id}",
            json={"description": "hacked"},
            headers=headers,
        )
        assert res.status_code == 403, res.text

        res = client.delete(
            f"/product-db/api/products/{p.id}/dependencies/{dep.id}",
            headers=headers,
        )
        assert res.status_code == 403, res.text

    def test_export_respects_ownership_filter(self, db):
        """Export must not include products owned by other regular users."""
        cat = _seed_category(db)
        admin = db.query(User).filter_by(username="admin").first()
        user1 = self._make_user(db, "exp_user1")
        user2 = self._make_user(db, "exp_user2")

        p_own = _seed_product(db, name="user1产品", category_id=cat.id)
        p_own.created_by = user1.id
        db.commit()

        # user2's list must exclude user1's product
        res = client.get("/product-db/api/products?per_page=100", headers=self._auth_for(user2))
        assert res.status_code == 200
        ids = {pp["id"] for pp in res.json()["products"]}
        assert p_own.id not in ids

        # export must exclude it as well
        res = client.get("/product-db/api/products/export", headers=self._auth_for(user2))
        assert res.status_code == 200
        import io, openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(res.content))
        ws = wb.active
        names = []
        for row in ws.iter_rows(min_row=4, values_only=True):
            if row and row[1]:
                names.append(str(row[1]))
        assert "user1产品" not in names, names[:5]

    def test_compare_respects_ownership_filter(self, db):
        """Compare must not return products owned by other regular users."""
        cat = _seed_category(db)
        user1 = self._make_user(db, "cmp_user1")
        user2 = self._make_user(db, "cmp_user2")

        p_a = _seed_product(db, name="A产品", category_id=cat.id)
        p_a.created_by = user1.id
        p_b = _seed_product(db, name="B产品", category_id=cat.id)
        p_b.created_by = user2.id
        db.commit()

        # user2 compares A (not visible) + B (visible) → only 1 visible → 404
        res = client.get(
            f"/product-db/api/products/compare?product_ids={p_a.id},{p_b.id}",
            headers=self._auth_for(user2),
        )
        assert res.status_code == 404, res.text


class TestMasterDataAdminOnly:
    """回归：主数据（品类/厂商/供应商/字典/BOM 模板）的写操作原用
    check_ownership(strict=False)，而它对 created_by IS NULL 的历史行直接放行；
    生产上这些表几乎全是 NULL（manufacturers 48/48、suppliers 55/55、
    dict_sensor_metrics 36/36…）→ 任何登录用户都能改删全站共用数据。
    现改为仅 admin 可写；业务数据（产品/方案/报价单）仍按归属校验。"""

    def _make_user(self, db, username, role="user"):
        u = User(username=username, password_hash=hash_password("test123"), role=role)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def _auth_for(self, user):
        return {"Authorization": f"Bearer {create_token(user.id, user.username)}"}

    def test_non_admin_cannot_write_master_data(self, db):
        cat = _seed_category(db)
        # 模拟生产现状：历史行 created_by 为 NULL
        cat.created_by = None
        db.commit()
        user = self._make_user(db, "md_user")
        headers = self._auth_for(user)

        cases = [
            ("post", "/product-db/api/categories", {"name": "越权品类"}),
            ("put", f"/product-db/api/categories/{cat.id}", {"name": "改名"}),
            ("delete", f"/product-db/api/categories/{cat.id}", None),
            ("post", "/product-db/api/suppliers", {"name": "越权供应商"}),
            ("post", "/product-db/api/dicts/manufacturers", {"name": "越权厂商"}),
            ("delete", "/product-db/api/dicts/sensor-metrics/1", None),
            ("post", "/product-db/api/bom-templates", {"name": "越权模板"}),
        ]
        for method, url, body in cases:
            call = getattr(client, method)
            res = call(url, json=body, headers=headers) if body is not None else call(url, headers=headers)
            assert res.status_code == 403, f"{method.upper()} {url} 应 403，实际 {res.status_code}"

    def test_admin_can_still_write_master_data(self, db):
        admin = db.query(User).filter_by(username="admin").first()
        headers = self._auth_for(admin)
        res = client.post("/product-db/api/categories", json={"name": "管理员建的品类"}, headers=headers)
        assert res.status_code == 201, res.text

    def test_non_admin_business_data_writes_unaffected(self, db):
        """门禁只针对主数据：普通用户仍可创建/修改自己的产品与方案。"""
        cat = _seed_category(db)
        user = self._make_user(db, "biz_user")
        headers = self._auth_for(user)

        res = client.post("/product-db/api/products",
                          json={"name": "普通用户产品", "model": "U-1", "category_id": cat.id},
                          headers=headers)
        assert res.status_code in (200, 201), res.text
        pid = res.json()["product"]["id"]

        res = client.put(f"/product-db/api/products/{pid}", json={"name": "改名后"}, headers=headers)
        assert res.status_code == 200, res.text

        res = client.post("/product-db/api/solutions", json={"name": "普通用户方案"}, headers=headers)
        assert res.status_code in (200, 201), res.text

        res = client.post("/product-db/api/quotations", json={"title": "普通用户报价"}, headers=headers)
        assert res.status_code == 201, res.text
