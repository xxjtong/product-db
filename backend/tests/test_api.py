"""Comprehensive test suite for product-db — uses a separate test database."""
import pytest
import os
import json
import tempfile

# Force test DB before any app imports
_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"

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
    p = Product(name=name, model=model, category_id=category_id,
                manufacturer_id=manufacturer_id, supplier_id=supplier_id,
                specs=kwargs.get("specs", {"ip_rating": "IP67", "weight_g": 500}))
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
        sol_id = resp.json()["solution"]["id"]

        resp = client.get("/product-db/api/solutions")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_solution(self, db):
        resp = client.post("/product-db/api/solutions", json={"name": "方案详情"})
        sol_id = resp.json()["solution"]["id"]

        resp = client.get(f"/product-db/api/solutions/{sol_id}")
        assert resp.status_code == 200
        assert resp.json()["solution"]["name"] == "方案详情"

    def test_update_solution(self, db):
        resp = client.post("/product-db/api/solutions", json={"name": "原始方案"})
        sol_id = resp.json()["solution"]["id"]

        resp = client.put(f"/product-db/api/solutions/{sol_id}", json={"name": "更新方案"})
        assert resp.status_code == 200
        assert resp.json()["solution"]["name"] == "更新方案"

    def test_delete_solution(self, db):
        resp = client.post("/product-db/api/solutions", json={"name": "删除方案"})
        sol_id = resp.json()["solution"]["id"]

        resp = client.delete(f"/product-db/api/solutions/{sol_id}")
        assert resp.status_code == 200

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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
        qt = resp.json()["quotation"]
        assert qt["client_name"] == "客户甲"

    def test_update_quotation(self, db):
        resp = client.post("/product-db/api/quotations", json={"title": "原始报价"})
        qt_id = resp.json()["quotation"]["id"]

        resp = client.put(f"/product-db/api/quotations/{qt_id}", json={"title": "更新报价"})
        assert resp.status_code == 200
        assert resp.json()["quotation"]["title"] == "更新报价"

    def test_delete_quotation(self, db):
        resp = client.post("/product-db/api/quotations", json={"title": "删除报价"})
        qt_id = resp.json()["quotation"]["id"]

        resp = client.delete(f"/product-db/api/quotations/{qt_id}")
        assert resp.status_code == 200

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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/vnd.openxmlformats")


# ============================================================
# BOM Templates
# ============================================================
class TestBOMTemplates:
    def test_create_and_list(self, db):
        resp = client.post("/product-db/api/bom-templates", json={
            "name": "标准模板", "snapshot": {"cells": {"A1": {"v": "标题"}}},
        })
        assert resp.status_code == 200
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
        assert resp.status_code == 200
        assert resp.json()["template"]["name"] == "查询模板"

    def test_update_template(self, db):
        resp = client.post("/product-db/api/bom-templates", json={
            "name": "旧模板", "snapshot": {},
        })
        t_id = resp.json()["template"]["id"]

        resp = client.put(f"/product-db/api/bom-templates/{t_id}", json={"name": "新模板"})
        assert resp.status_code == 200
        assert resp.json()["template"]["name"] == "新模板"

    def test_delete_template(self, db):
        resp = client.post("/product-db/api/bom-templates", json={
            "name": "删除模板", "snapshot": {},
        })
        t_id = resp.json()["template"]["id"]

        resp = client.delete(f"/product-db/api/bom-templates/{t_id}")
        assert resp.status_code == 200

    def test_duplicate_template(self, db):
        resp = client.post("/product-db/api/bom-templates", json={
            "name": "原始模板", "snapshot": {"cells": {"A1": {"v": "x"}}},
        })
        t_id = resp.json()["template"]["id"]

        resp = client.post(f"/product-db/api/bom-templates/{t_id}/duplicate")
        assert resp.status_code == 200
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
        assert resp.status_code == 200
        assert "bom_snapshot" in resp.json()
        assert resp.json()["bom_snapshot"]["snapshot"]["cells"]["A1"]["v"] == "BOM"

    def test_save_bom_snapshot(self, db):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)

        resp = client.post("/product-db/api/solutions", json={"name": "快照方案"})
        sol_id = resp.json()["solution"]["id"]

        # Save snapshot
        resp = client.put(f"/product-db/api/solutions/{sol_id}/bom-snapshot", json={
            "snapshot": {"cells": {"A1": {"v": "自定义内容"}}},
        })
        assert resp.status_code == 200

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
        assert resp.status_code == 200
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
        assert resp.status_code == 200
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
        assert resp.status_code == 200


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
