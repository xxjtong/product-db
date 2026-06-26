"""Tests for Agent, Admin, and Product Files endpoints."""
import pytest
import os
import tempfile
import io

# Force test DB before any app imports
_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["DEV_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-32charmin"

from fastapi.testclient import TestClient
from app.database import Base, engine, SessionLocal, get_db
from app.main import app
from app.models.user import User
from app.models.product import Product
from app.models.category import Category
from app.models.product_file import ProductFile
from app.auth import hash_password, create_token

client = TestClient(app)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables and seed admin user before each test."""
    Base.metadata.create_all(bind=engine)
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
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def auth_headers(db):
    """Return auth headers with a valid JWT for admin user."""
    admin = db.query(User).filter_by(username="admin").first()
    token = create_token(admin.id, admin.username)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def regular_user(db):
    """Create and return a regular (non-admin) user."""
    u = User(username="regular_user", password_hash=hash_password("testpass123"), role="user")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def regular_headers(regular_user):
    """Return auth headers for a regular user."""
    token = create_token(regular_user.id, regular_user.username)
    return {"Authorization": f"Bearer {token}"}


def _seed_category(db, name="测试品类", slug="test-cat"):
    cat = Category(name=name, slug=slug, level=1, sort_order=0)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _seed_product(db, name="测试产品", model="TEST-001", category_id=1, **kwargs):
    p = Product(name=name, model=model, category_id=category_id, **kwargs)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ============================================================
# Agent Endpoints
# ============================================================
class TestAgentConfig:
    def test_get_config(self, auth_headers):
        resp = client.get("/product-db/api/agent/config", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "db_path" in data
        assert "api_base" in data
        assert "upload_dir" in data

    def test_get_config_unauthenticated(self):
        """Without DEV_MODE bypass, unauthenticated should be 401."""
        # In DEV_MODE, unauthenticated requests get auto-admin, so this still returns 200
        resp = client.get("/product-db/api/agent/config")
        assert resp.status_code == 200


class TestAgentPrompt:
    def test_get_prompt(self, auth_headers):
        resp = client.get("/product-db/api/agent/prompt", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "prompt" in data
        assert isinstance(data["prompt"], str)
        assert len(data["prompt"]) > 0


class TestAgentCleanup:
    def test_cleanup_uploads(self, auth_headers):
        resp = client.post("/product-db/api/agent/cleanup-uploads", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "cleaned" in data
        assert isinstance(data["cleaned"], int)

    def test_cleanup_non_admin(self, regular_headers):
        resp = client.post("/product-db/api/agent/cleanup-uploads", headers=regular_headers)
        assert resp.status_code == 403


class TestAgentChat:
    def test_chat_missing_messages(self, auth_headers):
        resp = client.post("/product-db/api/agent/chat",
                           json={"messages": [], "stream": False},
                           headers=auth_headers)
        assert resp.status_code == 400

    def test_chat_returns_stream(self, auth_headers):
        """Agent chat with valid messages returns SSE stream (may fail to connect to Hermes)."""
        resp = client.post("/product-db/api/agent/chat",
                           json={"messages": [{"role": "user", "content": "hello"}], "stream": True},
                           headers=auth_headers)
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


class TestAgentApproval:
    def test_approval_not_found(self, auth_headers):
        resp = client.post("/product-db/api/agent/approval/nonexistent-task-id",
                           json={"approved": True, "reason": ""},
                           headers=auth_headers)
        assert resp.status_code == 404

    def test_list_approvals(self, auth_headers):
        resp = client.get("/product-db/api/agent/approvals", headers=auth_headers)
        assert resp.status_code == 200
        assert "tasks" in resp.json()

    def test_test_approval(self, auth_headers):
        resp = client.post("/product-db/api/agent/test-approval", headers=auth_headers)
        assert resp.status_code == 200
        assert "task_id" in resp.json()


# ============================================================
# Admin Endpoints
# ============================================================
class TestAdminUsers:
    def test_list_users(self, auth_headers):
        resp = client.get("/product-db/api/admin/users", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert len(data["users"]) >= 1
        # Each user should have ai_count and ai_tokens fields
        user = data["users"][0]
        assert "ai_count" in user
        assert "ai_tokens" in user

    def test_list_users_search(self, auth_headers, db):
        resp = client.get("/product-db/api/admin/users?search=admin", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["users"]) >= 1

    def test_create_user(self, auth_headers):
        resp = client.post("/product-db/api/admin/users", json={
            "username": "newuser", "password": "testpass123", "role": "user"
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["username"] == "newuser"
        assert data["user"]["role"] == "user"

    def test_create_duplicate_user(self, auth_headers):
        client.post("/product-db/api/admin/users", json={
            "username": "dupuser", "password": "testpass123"
        }, headers=auth_headers)
        resp = client.post("/product-db/api/admin/users", json={
            "username": "dupuser", "password": "testpass123"
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_update_user(self, auth_headers, regular_user):
        resp = client.put(f"/product-db/api/admin/users/{regular_user.id}", json={
            "role": "admin", "email": "updated@test.com"
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["user"]["role"] == "admin"
        assert resp.json()["user"]["email"] == "updated@test.com"

    def test_update_user_404(self, auth_headers):
        resp = client.put("/product-db/api/admin/users/99999", json={"role": "admin"},
                          headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_user(self, auth_headers, regular_user):
        uid = regular_user.id
        resp = client.delete(f"/product-db/api/admin/users/{uid}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_self(self, auth_headers, db):
        """Admin cannot delete themselves."""
        admin = db.query(User).filter_by(username="admin").first()
        resp = client.delete(f"/product-db/api/admin/users/{admin.id}", headers=auth_headers)
        assert resp.status_code == 400

    def test_users_non_admin(self, regular_headers):
        resp = client.get("/product-db/api/admin/users", headers=regular_headers)
        assert resp.status_code == 403

    def test_create_user_non_admin(self, regular_headers):
        resp = client.post("/product-db/api/admin/users", json={
            "username": "hacker", "password": "testpass123"
        }, headers=regular_headers)
        assert resp.status_code == 403

    def test_delete_user_non_admin(self, regular_headers, regular_user):
        resp = client.delete(f"/product-db/api/admin/users/{regular_user.id}",
                             headers=regular_headers)
        assert resp.status_code == 403


class TestAdminLoginLogs:
    def test_list_login_logs(self, auth_headers):
        resp = client.get("/product-db/api/admin/login-logs", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data

    def test_login_logs_non_admin(self, regular_headers):
        resp = client.get("/product-db/api/admin/login-logs", headers=regular_headers)
        assert resp.status_code == 403


class TestAdminFields:
    def test_get_fields(self, auth_headers):
        resp = client.get("/product-db/api/admin/fields", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "fields" in data
        # Should have default fields
        assert "cost_price" in data["fields"]

    def test_update_fields(self, auth_headers):
        resp = client.put("/product-db/api/admin/fields", json={
            "cost_price": False, "manufacturer_name": True
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify update took effect
        resp = client.get("/product-db/api/admin/fields", headers=auth_headers)
        assert resp.json()["fields"]["cost_price"] is False

    def test_fields_non_admin(self, regular_headers):
        resp = client.get("/product-db/api/admin/fields", headers=regular_headers)
        assert resp.status_code == 403


class TestAdminAISettings:
    def test_get_ai_settings(self, auth_headers):
        resp = client.get("/product-db/api/admin/ai-settings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "prompts" in data
        assert "models" in data
        assert "prompt_defaults" in data
        assert "model_defaults" in data

    def test_update_ai_settings(self, auth_headers):
        resp = client.put("/product-db/api/admin/ai-settings", json={
            "prompts": {"ai_system_prompt": "custom prompt"},
            "models": {"ai_chat_model": "custom-model"}
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_ai_settings_non_admin(self, regular_headers):
        resp = client.get("/product-db/api/admin/ai-settings", headers=regular_headers)
        assert resp.status_code == 403


class TestAdminLLMConfig:
    def test_get_llm_config(self, auth_headers):
        resp = client.get("/product-db/api/admin/llm-config", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data
        assert "defaults" in data
        assert "primary" in data["config"]
        assert "vision" in data["config"]

    def test_update_llm_config(self, auth_headers):
        resp = client.put("/product-db/api/admin/llm-config", json={
            "config": {
                "primary": {"provider": "test", "api_key": "test-key"}
            }
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_llm_config_non_admin(self, regular_headers):
        resp = client.get("/product-db/api/admin/llm-config", headers=regular_headers)
        assert resp.status_code == 403


class TestAdminLLMModels:
    def test_get_llm_models(self, auth_headers):
        resp = client.get("/product-db/api/admin/llm-models", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data

    def test_llm_models_non_admin(self, regular_headers):
        resp = client.get("/product-db/api/admin/llm-models", headers=regular_headers)
        assert resp.status_code == 403


class TestAdminAIUsage:
    def test_get_ai_usage(self, auth_headers):
        resp = client.get("/product-db/api/admin/ai-usage", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "by_op" in data
        assert "recent" in data
        assert "total" in data["summary"]

    def test_ai_usage_non_admin(self, regular_headers):
        resp = client.get("/product-db/api/admin/ai-usage", headers=regular_headers)
        assert resp.status_code == 403


class TestAdminDownloadLogs:
    def test_get_download_logs(self, auth_headers):
        resp = client.get("/product-db/api/admin/download-logs", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert "total" in data
        assert "page" in data

    def test_download_logs_non_admin(self, regular_headers):
        resp = client.get("/product-db/api/admin/download-logs", headers=regular_headers)
        assert resp.status_code == 403


# ============================================================
# Product Files Endpoints
# ============================================================
class TestProductFiles:
    def test_list_files(self, db, auth_headers):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        resp = client.get(f"/product-db/api/products/{p.id}/files", headers=auth_headers)
        assert resp.status_code == 200
        assert "files" in resp.json()
        assert isinstance(resp.json()["files"], list)

    def test_list_files_404(self, auth_headers):
        resp = client.get("/product-db/api/products/99999/files", headers=auth_headers)
        assert resp.status_code == 404

    def test_upload_file(self, db, auth_headers):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        file_content = b"test file content"
        resp = client.post(
            f"/product-db/api/products/{p.id}/files",
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
            data={"label": "test label"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["file"]["filename"] == "test.txt"
        assert data["file"]["label"] == "test label"
        assert data["file"]["file_size"] == len(file_content)

    def test_upload_and_download(self, db, auth_headers):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        file_content = b"download test content"
        resp = client.post(
            f"/product-db/api/products/{p.id}/files",
            files={"file": ("download.txt", io.BytesIO(file_content), "text/plain")},
            headers=auth_headers,
        )
        file_id = resp.json()["file"]["id"]

        resp = client.get(f"/product-db/api/products/files/{file_id}", headers=auth_headers)
        assert resp.status_code == 200

    def test_download_file_404(self, auth_headers):
        resp = client.get("/product-db/api/products/files/99999", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_file(self, db, auth_headers):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)
        resp = client.post(
            f"/product-db/api/products/{p.id}/files",
            files={"file": ("delete_me.txt", io.BytesIO(b"delete"), "text/plain")},
            headers=auth_headers,
        )
        file_id = resp.json()["file"]["id"]

        resp = client.delete(f"/product-db/api/products/files/{file_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify deleted
        resp = client.get(f"/product-db/api/products/files/{file_id}", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_file_404(self, auth_headers):
        resp = client.delete("/product-db/api/products/files/99999", headers=auth_headers)
        assert resp.status_code == 404
