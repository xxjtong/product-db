"""Round 3 tests: mock external HTTP/LLM calls to cover ai_engine, ai_extract, storage, agent, ai.py."""
import pytest
import os
import tempfile
import json
import io
from unittest.mock import patch, MagicMock, AsyncMock

_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["DEV_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-32charmin"

from fastapi.testclient import TestClient
from app.database import Base, engine, SessionLocal
from app.main import app
from app.models.user import User
from app.models.product import Product
from app.models.category import Category
from app.models.dictionary import Manufacturer, DictCommMethod
from app.models.mapping import ProductCommMethod
from app.auth import hash_password, create_token

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text('''CREATE TABLE IF NOT EXISTS product_categories (
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            PRIMARY KEY (product_id, category_id)
        )'''))
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
    admin = db.query(User).filter_by(username="admin").first()
    token = create_token(admin.id, admin.username)
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
# LLM Engine (54% → ~85%)
# ============================================================
class TestLlmEngine:
    def test_engine_api_key_from_config(self):
        from app.services.ai_engine import LlmEngine
        e = LlmEngine(api_key="test-key-12345")
        assert e.api_key == "test-key-12345"

    def test_engine_api_key_from_env(self):
        from app.services.ai_engine import LlmEngine
        e = LlmEngine()
        # Falls back to settings.AI_GATEWAY_KEY
        key = e.api_key
        assert isinstance(key, str)

    def test_engine_headers(self):
        from app.services.ai_engine import LlmEngine
        e = LlmEngine(api_key="my-key")
        h = e._headers()
        assert h["Authorization"] == "Bearer my-key"
        assert h["Content-Type"] == "application/json"

    @patch("httpx.AsyncClient.post")
    def test_chat_non_streaming(self, mock_post):
        from app.services.ai_engine import LlmEngine
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        import asyncio
        e = LlmEngine(api_key="test-key")
        result = asyncio.run(
            e.chat([{"role": "user", "content": "hi"}])
        )
        assert result["choices"][0]["message"]["content"] == "Hello!"
        mock_post.assert_called_once()

    @patch("httpx.AsyncClient.post")
    def test_chat_with_tools(self, mock_post):
        from app.services.ai_engine import LlmEngine
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok", "tool_calls": []}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        import asyncio
        e = LlmEngine(api_key="test-key")
        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        result = asyncio.run(
            e.chat([{"role": "user", "content": "use tool"}], tools=tools)
        )
        call_args = mock_post.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        assert "tools" in payload

    @patch("httpx.AsyncClient.stream")
    def test_chat_streaming(self, mock_stream):
        from app.services.ai_engine import LlmEngine
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        async def iter_lines():
            yield 'data: {"choices":[{"delta":{"content":"Hi"}}]}'
            yield 'data: [DONE]'

        mock_resp.aiter_lines = iter_lines
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_stream.return_value = mock_ctx

        import asyncio
        e = LlmEngine(api_key="test-key")
        chunks = []
        async def collect():
            async for chunk in e.chat_stream([{"role": "user", "content": "hi"}]):
                chunks.append(chunk)
        asyncio.run(collect())
        assert len(chunks) >= 1

    @patch("httpx.AsyncClient.post")
    def test_simple_chat(self, mock_post):
        from app.services.ai_engine import LlmEngine
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Simple response"}}],
            "usage": {}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        import asyncio
        e = LlmEngine(api_key="test-key")
        result = asyncio.run(
            e.simple_chat("hello", system_prompt="You are helpful")
        )
        assert result == "Simple response"


# ============================================================
# AI Extract (38% → ~70%)
# ============================================================
class TestAIExtract:
    def test_regex_extract_from_text(self, db):
        from app.services.ai_extract import regex_extract_from_text
        text = "UG65 LoRaWAN Gateway IP67 Milesight 价格: ¥2925"
        result = regex_extract_from_text("", text, db)
        assert isinstance(result, dict)
        assert "name" in result or "model" in result

    def test_regex_extract_empty(self, db):
        from app.services.ai_extract import regex_extract_from_text
        result = regex_extract_from_text("", "", db)
        assert isinstance(result, dict)

    @patch("app.services.ai_engine.engine")
    def test_call_ai_extract_with_mock(self, mock_engine, db):
        """call_ai_extract uses asyncio.run internally, so call it directly."""
        from app.services.ai_extract import call_ai_extract
        mock_engine.api_key = "test-key"

        # call_ai_extract calls asyncio.run(engine.chat(...))
        # We need to return a coroutine from chat, not an AsyncMock result
        async def fake_chat(*args, **kwargs):
            return {
                "choices": [{"message": {"content": json.dumps({
                    "name": "UG65", "model": "UG65", "category": "网关",
                    "manufacturer": "Milesight", "base_price": 2925,
                    "description": "LoRaWAN Gateway"
                })}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50}
            }
        mock_engine.chat = fake_chat

        usage = []
        result = call_ai_extract("https://example.com/product", "UG65 LoRaWAN Gateway", "", db, usage)
        assert isinstance(result, dict)


# ============================================================
# Storage upload_from_url (60% → ~85%)
# ============================================================
class TestStorageUploadFromUrl:
    @patch("httpx.get")
    def test_upload_from_url_jpeg(self, mock_get):
        from app.services.storage import upload_from_url, delete_file
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        url = upload_from_url("https://example.com/image.jpg")
        assert "/product-db/api/uploads/" in url
        assert url.endswith(".jpg")
        delete_file(url)

    @patch("httpx.get")
    def test_upload_from_url_png(self, mock_get):
        from app.services.storage import upload_from_url, delete_file
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        url = upload_from_url("https://example.com/img.png")
        assert url.endswith(".png")
        delete_file(url)

    @patch("httpx.get")
    def test_upload_from_url_gif(self, mock_get):
        from app.services.storage import upload_from_url, delete_file
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"GIF89a" + b"\x00" * 100
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        url = upload_from_url("https://example.com/img.gif")
        assert url.endswith(".gif")
        delete_file(url)

    def test_upload_from_url_private_blocked(self):
        from app.services.storage import upload_from_url
        with pytest.raises(ValueError, match="not allowed"):
            upload_from_url("http://127.0.0.1/admin")

    @patch("httpx.get")
    def test_upload_from_url_too_small(self, mock_get):
        from app.services.storage import upload_from_url
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"tiny"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="too small"):
            upload_from_url("https://example.com/tiny.jpg")

    @patch("httpx.get")
    def test_upload_from_url_invalid_format(self, mock_get):
        from app.services.storage import upload_from_url
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"not an image file at all!!"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="does not match"):
            upload_from_url("https://example.com/fake.jpg")


# ============================================================
# Products AI Fetch (62% → ~70%)
# ============================================================
class TestProductsAIFetch:
    @patch("app.services.ai_engine.engine")
    def test_ai_fetch_text_with_mock(self, mock_engine, db, auth_headers):
        """POST /products/ai-fetch with text should extract product info."""
        mock_engine.api_key = ""  # Will use regex fallback
        resp = client.post("/product-db/api/products/ai-fetch", json={
            "text": "UG65 LoRaWAN Gateway IP67 Milesight 价格2925元"
        }, headers=auth_headers)
        assert resp.status_code in (200, 201)
        assert "fetched" in resp.json()

    def test_ai_fetch_empty(self, auth_headers):
        resp = client.post("/product-db/api/products/ai-fetch", json={
            "url": "", "text": ""
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_ai_fetch_invalid_url(self, auth_headers):
        resp = client.post("/product-db/api/products/ai-fetch", json={
            "url": "not-a-url"
        }, headers=auth_headers)
        assert resp.status_code == 400

    @patch("httpx.get")
    @patch("app.services.ai_engine.engine")
    def test_ai_fetch_url_success(self, mock_engine, mock_get, db, auth_headers):
        """POST /products/ai-fetch with URL should fetch and extract."""
        mock_engine.api_key = ""  # regex fallback
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>UG65 LoRaWAN Gateway IP67</body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        resp = client.post("/product-db/api/products/ai-fetch", json={
            "url": "https://example.com/product"
        }, headers=auth_headers)
        assert resp.status_code in (200, 201)

    def test_ai_fetch_private_url_blocked(self, auth_headers):
        resp = client.post("/product-db/api/products/ai-fetch", json={
            "url": "http://127.0.0.1/admin"
        }, headers=auth_headers)
        assert resp.status_code == 400


# ============================================================
# Agent endpoints (49% → ~65%)
# ============================================================
class TestAgentEndpoints:
    @patch("httpx.AsyncClient.stream")
    def test_agent_chat_streams(self, mock_stream, db, auth_headers):
        """Agent chat should return SSE stream."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 200

        async def iter_bytes():
            yield b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
            yield b'data: [DONE]\n\n'

        mock_resp.aiter_bytes = iter_bytes
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_stream.return_value = mock_ctx

        resp = client.post("/product-db/api/agent/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_agent_chat_empty_messages(self, auth_headers):
        resp = client.post("/product-db/api/agent/chat", json={
            "messages": [], "stream": False
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_agent_chat_no_messages(self, auth_headers):
        resp = client.post("/product-db/api/agent/chat", json={
            "stream": False
        }, headers=auth_headers)
        assert resp.status_code == 422

    def test_agent_config(self, auth_headers):
        resp = client.get("/product-db/api/agent/config", headers=auth_headers)
        assert resp.status_code == 200
        assert "db_path" in resp.json()

    def test_agent_prompt(self, auth_headers):
        resp = client.get("/product-db/api/agent/prompt", headers=auth_headers)
        assert resp.status_code == 200
        assert "prompt" in resp.json()

    def test_agent_approvals_empty(self, auth_headers):
        resp = client.get("/product-db/api/agent/approvals", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["tasks"], list)

    def test_agent_approval_not_found(self, auth_headers):
        resp = client.post("/product-db/api/agent/approval/fake-id",
                           json={"approved": True}, headers=auth_headers)
        assert resp.status_code == 404

    def test_agent_test_approval(self, auth_headers):
        resp = client.post("/product-db/api/agent/test-approval", headers=auth_headers)
        assert resp.status_code == 200
        assert "task_id" in resp.json()

    def test_agent_cleanup_non_admin(self, db):
        u = User(username="agent_user", password_hash=hash_password("test123"), role="user")
        db.add(u)
        db.commit()
        db.refresh(u)
        token = create_token(u.id, u.username)
        resp = client.post("/product-db/api/agent/cleanup-uploads",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


# ============================================================
# AI Chat with LLM mock (61% → ~70%)
# ============================================================
class TestAIChatWithLLM:
    @patch("app.services.ai_engine.engine")
    def test_chat_with_llm_product_search(self, mock_engine, db, auth_headers):
        """AI chat with LLM should search products via keyword extraction."""
        mock_engine.api_key = "test-key"
        # Mock keyword extraction response
        mock_engine.chat = AsyncMock(return_value={
            "choices": [{"message": {"content": json.dumps({
                "keywords": ["网关"],
                "matches": {},
                "brand": None, "category": None,
                "comm_method": None, "protocol": None, "power": None,
                "min_price": None, "max_price": None, "sort_by": None
            })}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}
        })

        cat = _seed_category(db)
        _seed_product(db, name="LoRaWAN网关", category_id=cat.id)

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "找网关"
        }, headers=auth_headers)
        assert resp.status_code == 200

    @patch("app.services.ai_engine.engine")
    def test_chat_with_llm_no_results(self, mock_engine, db, auth_headers):
        """AI chat when LLM finds no matching products."""
        mock_engine.api_key = "test-key"
        mock_engine.chat = AsyncMock(return_value={
            "choices": [{"message": {"content": json.dumps({
                "keywords": ["不存在的产品xyz"],
                "matches": {},
                "brand": None, "category": None,
                "comm_method": None, "protocol": None, "power": None,
                "min_price": None, "max_price": None, "sort_by": None
            })}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 30}
        })

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "找不存在的产品xyz"
        }, headers=auth_headers)
        assert resp.status_code == 200

    @patch("app.services.ai_engine.engine")
    def test_chat_with_llm_brand_filter(self, mock_engine, db, auth_headers):
        """AI chat with brand filter in extraction."""
        mock_engine.api_key = "test-key"
        mock_engine.chat = AsyncMock(return_value={
            "choices": [{"message": {"content": json.dumps({
                "keywords": ["传感器"],
                "matches": {},
                "brand": "星纵", "category": None,
                "comm_method": None, "protocol": None, "power": None,
                "min_price": None, "max_price": None, "sort_by": None
            })}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}
        })

        cat = _seed_category(db)
        mfg = Manufacturer(name="星纵")
        db.add(mfg)
        db.commit()
        db.refresh(mfg)
        _seed_product(db, name="星纵传感器", category_id=cat.id, manufacturer_id=mfg.id)

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "星纵传感器"
        }, headers=auth_headers)
        assert resp.status_code == 200

    def test_chat_conversations_list(self, auth_headers):
        resp = client.get("/product-db/api/ai/conversations", headers=auth_headers)
        assert resp.status_code == 200


# ============================================================
# Agent _execute_tool (49% → ~65%)
# ============================================================
class TestAgentExecuteTool:
    def test_execute_search_products(self, db):
        from app.routers.agent import _execute_tool
        cat = _seed_category(db)
        _seed_product(db, name="Agent网关", category_id=cat.id)

        import asyncio
        result = asyncio.run(
            _execute_tool("search_products", {"keyword": "网关"}, user_id=1)
        )
        assert "items" in result
        assert result["total"] >= 1

    def test_execute_get_product_detail(self, db):
        from app.routers.agent import _execute_tool
        cat = _seed_category(db)
        p = _seed_product(db, name="Detail产品", category_id=cat.id)

        import asyncio
        result = asyncio.run(
            _execute_tool("get_product_detail", {"product_id": p.id}, user_id=1)
        )
        assert result["name"] == "Detail产品"

    def test_execute_get_product_not_found(self, db):
        from app.routers.agent import _execute_tool
        import asyncio
        result = asyncio.run(
            _execute_tool("get_product_detail", {"product_id": 99999}, user_id=1)
        )
        assert "error" in result

    def test_execute_unknown_tool(self, db):
        from app.routers.agent import _execute_tool
        import asyncio
        result = asyncio.run(
            _execute_tool("nonexistent", {}, user_id=1)
        )
        assert "error" in result

    def test_execute_search_with_filters(self, db):
        from app.routers.agent import _execute_tool
        cat = _seed_category(db)
        mfg = Manufacturer(name="TestBrand")
        db.add(mfg)
        db.commit()
        db.refresh(mfg)
        _seed_product(db, name="Branded", category_id=cat.id, manufacturer_id=mfg.id, base_price=500)

        import asyncio
        result = asyncio.run(
            _execute_tool("search_products", {
                "keyword": "Branded", "manufacturer_name": "TestBrand",
                "min_price": 100, "max_price": 1000
            }, user_id=1)
        )
        assert result["total"] >= 1


# ============================================================
# Approval Manager async (73% → ~90%)
# ============================================================
class TestApprovalManagerAsync:
    def test_create_and_decide(self):
        from app.services.approval_manager import ApprovalManager
        mgr = ApprovalManager()
        task = mgr.create(
            tool_name="test", tool_label="测试",
            tool_input={"x": 1}, summary="test approval"
        )
        assert task.task_id
        assert len(mgr.get_pending()) == 1

        ok = mgr.decide(task.task_id, approved=True, reason="ok")
        assert ok is True
        assert len(mgr.get_pending()) == 0

    def test_decide_nonexistent(self):
        from app.services.approval_manager import ApprovalManager
        mgr = ApprovalManager()
        assert mgr.decide("fake", True) is False

    def test_wait_for_decision_timeout(self):
        from app.services.approval_manager import ApprovalManager
        mgr = ApprovalManager()
        task = mgr.create(
            tool_name="test", tool_label="测试",
            tool_input={}, summary="timeout test"
        )
        import asyncio
        # Override timeout to 0.1s for test speed
        from app.services.approval_manager import TIMEOUT_SECONDS
        import app.services.approval_manager as am
        old = am.TIMEOUT_SECONDS
        am.TIMEOUT_SECONDS = 0.1
        try:
            result = asyncio.run(
                mgr.wait_for_decision(task.task_id)
            )
            assert result["approved"] is False
            assert "超时" in result["reason"]
        finally:
            am.TIMEOUT_SECONDS = old

    def test_wait_for_nonexistent(self):
        from app.services.approval_manager import ApprovalManager
        mgr = ApprovalManager()
        import asyncio
        result = asyncio.run(
            mgr.wait_for_decision("nonexistent")
        )
        assert result["approved"] is False
