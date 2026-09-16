"""Round 4: ai.py conversations/context, agent upload/proxy, bom_templates, products AI fetch."""
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
from app.models.category import Category, CategorySpecDefinition
from app.models.dictionary import Manufacturer
from app.models.solution import Solution, SolutionItem
from app.models.bom_template import BOMTemplate, SolutionBOMSnapshot
from app.models.ai_models import AIConversation, AIMessage
from app.auth import hash_password, create_token

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    from sqlalchemy import text
    with engine.connect() as conn:
        for tbl in ['product_categories', 'product_comm_methods', 'product_comm_protocols',
                     'product_power_supplies', 'product_hardware_interfaces',
                     'product_sensor_capabilities', 'product_images']:
            conn.execute(text(f'''CREATE TABLE IF NOT EXISTS {tbl} (
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
# AI: Conversation CRUD + Context (61% → ~70%)
# ============================================================
class TestAIConversationCRUD:
    def test_create_conversation(self, db, auth_headers):
        """Creating a chat should auto-create conversation."""
        cat = _seed_category(db)
        _seed_product(db, category_id=cat.id)
        resp = client.post("/product-db/api/ai/chat", json={
            "input": "你好"
        }, headers=auth_headers)
        assert resp.status_code == 200

    def test_second_round_accepts_int_conversation_id(self, db, auth_headers):
        """Regression: frontend sends conversation_id as a JSON number. With the
        old `Optional[str]` schema every round after the first got a 422, and the
        SSE client silently rendered nothing."""
        conv = AIConversation(user_id=1, title="Round 2")
        db.add(conv)
        db.commit()
        db.refresh(conv)

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "再找个网关", "conversation_id": conv.id,
        }, headers=auth_headers)
        assert resp.status_code == 200, resp.text

    def test_list_conversations(self, db, auth_headers):
        # Create a conversation first
        conv = AIConversation(user_id=1, title="Test Conv")
        db.add(conv)
        db.commit()

        resp = client.get("/product-db/api/ai/conversations", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["conversations"]) >= 1

    def test_get_conversation(self, db, auth_headers):
        conv = AIConversation(user_id=1, title="Detail Conv")
        db.add(conv)
        db.commit()
        db.refresh(conv)

        resp = client.get(f"/product-db/api/ai/conversations/{conv.id}",
                          headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["conversation"]["title"] == "Detail Conv"

    def test_get_conversation_not_found(self, auth_headers):
        resp = client.get("/product-db/api/ai/conversations/99999", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_conversation(self, db, auth_headers):
        conv = AIConversation(user_id=1, title="Delete Me")
        db.add(conv)
        db.commit()
        db.refresh(conv)

        resp = client.delete(f"/product-db/api/ai/conversations/{conv.id}",
                             headers=auth_headers)
        assert resp.status_code == 200

    def test_delete_conversation_not_found(self, auth_headers):
        resp = client.delete("/product-db/api/ai/conversations/99999", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_conversation_with_messages(self, db, auth_headers):
        conv = AIConversation(user_id=1, title="With Msgs")
        db.add(conv)
        db.commit()
        db.refresh(conv)

        db.add(AIMessage(conversation_id=conv.id, role="user", content="hello"))
        db.add(AIMessage(conversation_id=conv.id, role="assistant", content="hi there"))
        db.commit()

        resp = client.get(f"/product-db/api/ai/conversations/{conv.id}",
                          headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["messages"]) == 2

    def test_ai_stats(self, auth_headers):
        resp = client.get("/product-db/api/ai/stats", headers=auth_headers)
        assert resp.status_code == 200
        assert "total" in resp.json()
        assert "user_count" in resp.json()


# ============================================================
# AI: message history must stay a valid tool-call sequence
# ============================================================
class TestAIContextMessageValidity:
    """Regression: orphan `tool` rows made every round 2+ request a 400 and the
    failure silently degraded to the keyword mock agent."""

    def _conv(self, db, title="Ctx"):
        conv = AIConversation(user_id=1, title=title)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv

    def test_drops_orphan_tool_rows_from_legacy_keyword_path(self, db):
        from app.routers.ai import get_messages_for_context

        conv = self._conv(db, "Legacy")
        db.add(AIMessage(conversation_id=conv.id, role="user", content="找网关"))
        # What the old keyword-extraction path wrote: a bare tool row with no
        # matching assistant tool_calls
        db.add(AIMessage(conversation_id=conv.id, role="tool",
                         content='{"found": 1, "products": []}'))
        db.add(AIMessage(conversation_id=conv.id, role="assistant", content="查询完成。"))
        db.commit()

        msgs = get_messages_for_context(conv.id, db)
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert all(m.get("tool_call_id") for m in msgs if m["role"] == "tool")

    def test_keeps_well_formed_tool_call_pair(self, db):
        from app.routers.ai import get_messages_for_context

        conv = self._conv(db, "Paired")
        db.add(AIMessage(conversation_id=conv.id, role="user", content="找网关"))
        db.add(AIMessage(conversation_id=conv.id, role="assistant",
                         tool_calls=json.dumps([{"id": "call_1", "type": "function",
                                                 "function": {"name": "search_products",
                                                              "arguments": "{}"}}])))
        db.add(AIMessage(conversation_id=conv.id, role="tool",
                         tool_call_id="call_1", content='{"found": 0}'))
        db.add(AIMessage(conversation_id=conv.id, role="assistant", content="没有找到。"))
        db.commit()

        msgs = get_messages_for_context(conv.id, db)
        assert [m["role"] for m in msgs] == ["user", "assistant", "tool", "assistant"]
        assert msgs[2]["tool_call_id"] == "call_1"

    def test_drops_assistant_tool_calls_that_were_never_answered(self, db):
        from app.routers.ai import get_messages_for_context

        conv = self._conv(db, "Unanswered")
        db.add(AIMessage(conversation_id=conv.id, role="user", content="找网关"))
        db.add(AIMessage(conversation_id=conv.id, role="assistant",
                         tool_calls=json.dumps([{"id": "call_x", "type": "function",
                                                 "function": {"name": "search_products",
                                                              "arguments": "{}"}}])))
        db.add(AIMessage(conversation_id=conv.id, role="user", content="在吗"))
        db.commit()

        msgs = get_messages_for_context(conv.id, db)
        assert [m["role"] for m in msgs] == ["user", "user"]
        assert all("tool_calls" not in m for m in msgs)

    def test_history_never_starts_mid_turn(self, db):
        from app.routers.ai import get_messages_for_context

        conv = self._conv(db, "MidTurn")
        db.add(AIMessage(conversation_id=conv.id, role="user", content="第一轮"))
        db.add(AIMessage(conversation_id=conv.id, role="assistant",
                         tool_calls=json.dumps([{"id": "call_1", "type": "function",
                                                 "function": {"name": "search_products",
                                                              "arguments": "{}"}}])))
        db.add(AIMessage(conversation_id=conv.id, role="tool",
                         tool_call_id="call_1", content='{"found": 0}'))
        db.add(AIMessage(conversation_id=conv.id, role="assistant", content="没有找到。"))
        db.commit()

        # limit=2 slices off the leading user message, leaving a dangling pair
        msgs = get_messages_for_context(conv.id, db, limit=2)
        assert msgs == []


# ============================================================
# AI: recovering plain-text tool-call markup
# ============================================================
class TestDsmlToolCallRecovery:
    """Regression: deepseek-v4-flash sometimes ignores the `tools` declaration
    and writes the call as plain text, which used to be streamed to the user
    verbatim instead of being executed."""

    def _invoke(self, name, **params):
        bar = "\uff5c\uff5cDSML\uff5c\uff5c"
        body = "".join(
            f'<{bar} parameter name="{k}" string="true">{v}</{bar} parameter>\n'
            for k, v in params.items()
        )
        return f'<{bar} calls>\n<{bar} invoke name="{name}">\n{body}</{bar} invoke>\n</{bar} calls>'

    def test_parses_invoke_and_parameters(self):
        from app.routers.ai import _parse_dsml_tool_calls

        calls = _parse_dsml_tool_calls(self._invoke("search_products", category="温湿度传感器"))
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "search_products"
        assert json.loads(calls[0]["function"]["arguments"]) == {"category": "温湿度传感器"}

    def test_parses_multiple_invokes(self):
        from app.routers.ai import _parse_dsml_tool_calls

        content = self._invoke("search_products", category="网关") + self._invoke("get_product_detail", product_id="7")
        calls = _parse_dsml_tool_calls(content)
        assert [c["function"]["name"] for c in calls] == ["search_products", "get_product_detail"]
        assert len({c["id"] for c in calls}) == 2

    def test_plain_text_yields_nothing(self):
        from app.routers.ai import _parse_dsml_tool_calls

        assert _parse_dsml_tool_calls("找到 3 个产品。") == []

    def test_recovered_call_executes_and_returns_products(self, db):
        from app.routers.ai import _parse_dsml_tool_calls
        from app.services.ai_tools import execute_tool

        cat = _seed_category(db, name="温湿度传感器", slug="th-sensor")
        _seed_product(db, name="温湿度传感器T1", model="WSDCGQ12LM", category_id=cat.id)

        calls = _parse_dsml_tool_calls(self._invoke("search_products", keyword="温湿度传感器"))
        result = json.loads(execute_tool(calls[0]["function"]["name"],
                                         json.loads(calls[0]["function"]["arguments"]), db))
        assert result["found"] >= 1


class TestAIBuildContext:
    def test_build_context_with_data(self, db):
        from app.routers.ai import build_context
        # Clear cache
        import app.routers.ai as ai_mod
        ai_mod._ctx_cache = {"ts": 0, "value": ""}

        cat = _seed_category(db, name="传感器", slug="sensor")
        cat.level = 2
        db.commit()
        sd = CategorySpecDefinition(
            category_id=cat.id, spec_key="ip_rating", display_name="IP等级",
            spec_type="enum", is_filterable=True
        )
        db.add(sd)
        mfg = Manufacturer(name="TestMfg")
        db.add(mfg)
        _seed_product(db, category_id=cat.id)
        db.commit()

        result = build_context(db)
        assert "传感器" in result
        assert "TestMfg" in result
        assert "IP等级" in result

    def test_build_context_caches(self, db):
        from app.routers.ai import build_context
        import app.routers.ai as ai_mod
        ai_mod._ctx_cache = {"ts": 0, "value": ""}

        r1 = build_context(db)
        r2 = build_context(db)
        assert r1 == r2  # cached


# ============================================================
# AI: run_agent with LLM mock (main uncovered paths)
# ============================================================
class TestAIRunAgent:
    @patch("app.services.ai_engine.engine")
    def test_run_agent_keyword_match_products(self, mock_engine, db, auth_headers):
        """LLM returns keywords with matched product IDs."""
        cat = _seed_category(db)
        p = _seed_product(db, name="LoRaWAN网关", model="UG65", category_id=cat.id)

        mock_engine.api_key = "test-key"
        call_count = {"n": 0}

        async def fake_chat(messages, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Keyword extraction
                return {
                    "choices": [{"message": {"content": json.dumps({
                        "keywords": ["网关"],
                        "matches": {"网关": [p.id]},
                        "brand": None, "category": None,
                        "comm_method": None, "protocol": None, "power": None,
                        "min_price": None, "max_price": None, "sort_by": None
                    })}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50}
                }
            # Final chat response
            return {
                "choices": [{"message": {"content": "找到相关网关产品。"}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20}
            }
        mock_engine.chat = fake_chat

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "找网关"
        }, headers=auth_headers)
        assert resp.status_code == 200

    @patch("app.services.ai_engine.engine")
    def test_run_agent_multi_solution(self, mock_engine, db, auth_headers):
        """LLM returns multi-solution grouping."""
        cat = _seed_category(db)
        p1 = _seed_product(db, name="网关A", category_id=cat.id)
        p2 = _seed_product(db, name="传感器B", category_id=cat.id)

        mock_engine.api_key = "test-key"

        async def fake_chat(messages, **kwargs):
            return {
                "choices": [{"message": {"content": json.dumps({
                    "keywords": [],
                    "matches": {},
                    "solutions": [
                        {"name": "方案A", "desc": "网关方案", "product_ids": [p1.id]},
                        {"name": "方案B", "desc": "传感器方案", "product_ids": [p2.id]},
                    ],
                    "brand": None, "category": None,
                    "comm_method": None, "protocol": None, "power": None,
                    "min_price": None, "max_price": None, "sort_by": None
                })}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50}
            }
        mock_engine.chat = fake_chat

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "推荐方案"
        }, headers=auth_headers)
        assert resp.status_code == 200

    @patch("app.services.ai_engine.engine")
    def test_run_agent_llm_tool_call(self, mock_engine, db, auth_headers):
        """LLM returns tool_calls → execute tool → return text."""
        cat = _seed_category(db)
        _seed_product(db, name="TestGW", category_id=cat.id)

        mock_engine.api_key = "test-key"
        call_count = {"n": 0}

        async def fake_chat(messages, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Keyword extraction → no match
                return {
                    "choices": [{"message": {"content": json.dumps({
                        "keywords": ["xyz_nonexistent"],
                        "matches": {},
                        "brand": None, "category": None,
                        "comm_method": None, "protocol": None, "power": None,
                        "min_price": None, "max_price": None, "sort_by": None
                    })}}],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 30}
                }
            # Chat with tool call
            return {
                "choices": [{"message": {
                    "tool_calls": [{
                        "id": "tc_1", "type": "function",
                        "function": {
                            "name": "search_products",
                            "arguments": json.dumps({"keywords": ["网关"]})
                        }
                    }]
                }}],
                "usage": {"prompt_tokens": 80, "completion_tokens": 40}
            }
        mock_engine.chat = fake_chat

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "找网关"
        }, headers=auth_headers)
        assert resp.status_code == 200

    @patch("app.services.ai_engine.engine")
    def test_run_agent_llm_auth_failure(self, mock_engine, db, auth_headers):
        """LLM returns 401 → should warn and fallback."""
        mock_engine.api_key = "bad-key"

        async def fake_chat(messages, **kwargs):
            raise Exception("401 Unauthorized")
        mock_engine.chat = fake_chat

        cat = _seed_category(db)
        _seed_product(db, name="Fallback产品", category_id=cat.id)

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "找产品"
        }, headers=auth_headers)
        assert resp.status_code == 200

    @patch("app.services.ai_engine.engine")
    def test_run_agent_brand_filter(self, mock_engine, db, auth_headers):
        """LLM returns brand filter → should filter by manufacturer."""
        cat = _seed_category(db)
        mfg = Manufacturer(name="星纵")
        db.add(mfg)
        db.commit()
        db.refresh(mfg)
        p = _seed_product(db, name="星纵网关", category_id=cat.id, manufacturer_id=mfg.id)

        mock_engine.api_key = "test-key"

        async def fake_chat(messages, **kwargs):
            return {
                "choices": [{"message": {"content": json.dumps({
                    "keywords": ["网关"],
                    "matches": {"网关": [p.id]},
                    "brand": "星纵", "category": None,
                    "comm_method": None, "protocol": None, "power": None,
                    "min_price": None, "max_price": None, "sort_by": None
                })}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50}
            }
        mock_engine.chat = fake_chat

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "星纵网关"
        }, headers=auth_headers)
        assert resp.status_code == 200

    @patch("app.services.ai_engine.engine")
    def test_run_agent_price_sort(self, mock_engine, db, auth_headers):
        """LLM returns price sort → should sort results."""
        cat = _seed_category(db)
        _seed_product(db, name="Cheap", category_id=cat.id, base_price=100)
        _seed_product(db, name="Mid", category_id=cat.id, base_price=500)
        _seed_product(db, name="Expensive", category_id=cat.id, base_price=1000)

        mock_engine.api_key = "test-key"

        async def fake_chat(messages, **kwargs):
            return {
                "choices": [{"message": {"content": json.dumps({
                    "keywords": [""],
                    "matches": {},
                    "brand": None, "category": None,
                    "comm_method": None, "protocol": None, "power": None,
                    "min_price": 50, "max_price": 2000, "sort_by": "price_asc"
                })}}],
                "usage": {"prompt_tokens": 80, "completion_tokens": 40}
            }
        mock_engine.chat = fake_chat

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "所有产品按价格排序"
        }, headers=auth_headers)
        assert resp.status_code == 200

    @patch("app.services.ai_engine.engine")
    def test_run_agent_dsml_format(self, mock_engine, db, auth_headers):
        """LLM returns DSML format → should parse keywords."""
        cat = _seed_category(db)
        _seed_product(db, name="DSML产品", category_id=cat.id)

        mock_engine.api_key = "test-key"

        async def fake_chat(messages, **kwargs):
            return {
                "choices": [{"message": {"content": 'DSML <arg name="keyword">网关</arg>'}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20}
            }
        mock_engine.chat = fake_chat

        resp = client.post("/product-db/api/ai/chat", json={
            "input": "DSML网关"
        }, headers=auth_headers)
        assert resp.status_code == 200


# ============================================================
# Agent: File Upload (49% → ~60%)
# ============================================================
class TestAgentFileUpload:
    def test_upload_text_file(self, auth_headers):
        resp = client.post("/product-db/api/agent/upload",
                           files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
                           headers=auth_headers)
        assert resp.status_code == 200
        assert "url" in resp.json()

    def test_upload_json_file(self, auth_headers):
        resp = client.post("/product-db/api/agent/upload",
                           files={"file": ("data.json", io.BytesIO(b'{"a":1}'), "application/json")},
                           headers=auth_headers)
        assert resp.status_code == 200

    def test_upload_xlsx_file(self, auth_headers):
        resp = client.post("/product-db/api/agent/upload",
                           files={"file": ("test.xlsx", io.BytesIO(b"PK" + b"\x00"*100),
                                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                           headers=auth_headers)
        assert resp.status_code == 200

    def test_upload_disallowed_type(self, auth_headers):
        resp = client.post("/product-db/api/agent/upload",
                           files={"file": ("evil.exe", io.BytesIO(b"MZ" + b"\x00"*100),
                                  "application/x-msdownload")},
                           headers=auth_headers)
        assert resp.status_code == 400

    def test_upload_too_large(self, auth_headers):
        big = b"x" * (21 * 1024 * 1024)  # 21MB
        resp = client.post("/product-db/api/agent/upload",
                           files={"file": ("big.txt", io.BytesIO(big), "text/plain")},
                           headers=auth_headers)
        assert resp.status_code == 400


# ============================================================
# BOM Templates (66% → ~80%)
# ============================================================
class TestBOMTemplatesExtended:
    def test_snapshot_save_and_read(self, db, auth_headers):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id, sku="SKU-001")

        resp = client.post("/product-db/api/solutions",
                           json={"name": "BOM Snap"}, headers=auth_headers)
        sol_id = resp.json()["solution"]["id"]

        client.post(f"/product-db/api/solutions/{sol_id}/items", json={
            "product_id": p.id, "quantity": 3, "unit_price": 100
        }, headers=auth_headers)

        # Save snapshot
        snapshot = {"cells": {
            "A1": {"v": "#"}, "B1": {"v": "名称"}, "C1": {"v": "SKU"},
            "A3": {"v": 1}, "B3": {"v": "测试产品"}, "C3": {"v": "SKU-001"},
            "E3": {"v": 5}, "F3": {"v": 200}, "G3": {"v": 100},
        }}
        resp = client.put(f"/product-db/api/solutions/{sol_id}/bom-snapshot",
                          json={"snapshot": snapshot}, headers=auth_headers)
        assert resp.status_code == 200

        # Read back
        resp = client.get(f"/product-db/api/solutions/{sol_id}/bom-snapshot",
                          headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["bom_snapshot"]["snapshot"]["cells"]["A1"]["v"] == "#"

    def test_snapshot_sync_updates_items(self, db, auth_headers):
        """Saving snapshot with edited values should sync back to solution_items."""
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id, sku="SYNC-001")

        resp = client.post("/product-db/api/solutions",
                           json={"name": "Sync Test"}, headers=auth_headers)
        sol_id = resp.json()["solution"]["id"]

        client.post(f"/product-db/api/solutions/{sol_id}/items", json={
            "product_id": p.id, "quantity": 1, "unit_price": 100
        }, headers=auth_headers)

        # Save snapshot with updated qty/price
        snapshot = {"cells": {
            "C3": {"v": "SYNC-001"}, "E3": {"v": 10}, "F3": {"v": 500},
            "G3": {"v": 80}, "I3": {"v": "加急"},
        }}
        resp = client.put(f"/product-db/api/solutions/{sol_id}/bom-snapshot",
                          json={"snapshot": snapshot}, headers=auth_headers)
        assert resp.status_code == 200

        # Verify item was updated
        resp = client.get(f"/product-db/api/solutions/{sol_id}/items",
                          headers=auth_headers)
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["quantity"] == 10
        assert items[0]["unit_price"] == 500

    def test_save_as_template(self, db, auth_headers):
        cat = _seed_category(db)
        _seed_product(db, category_id=cat.id)

        resp = client.post("/product-db/api/solutions",
                           json={"name": "Template Source"}, headers=auth_headers)
        sol_id = resp.json()["solution"]["id"]

        # Create snapshot first
        client.put(f"/product-db/api/solutions/{sol_id}/bom-snapshot",
                   json={"snapshot": {"cells": {"A1": {"v": "test"}}}},
                   headers=auth_headers)

        # Save as template
        resp = client.post(
            f"/product-db/api/solutions/{sol_id}/bom-snapshot/save-as-template",
            json={"name": "My Template"}, headers=auth_headers
        )
        assert resp.status_code in (200, 201)
        assert "副本" in resp.json()["template"]["name"] or resp.json()["template"]["name"] == "My Template"

    def test_export_bom_xlsx_with_snapshot(self, db, auth_headers):
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)

        resp = client.post("/product-db/api/solutions",
                           json={"name": "Export BOM"}, headers=auth_headers)
        sol_id = resp.json()["solution"]["id"]

        client.post(f"/product-db/api/solutions/{sol_id}/items", json={
            "product_id": p.id, "quantity": 2, "unit_price": 300
        }, headers=auth_headers)

        resp = client.get(f"/product-db/api/solutions/{sol_id}/bom-snapshot/export-xlsx",
                          headers=auth_headers)
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]

    def test_export_bom_xlsx_without_snapshot(self, db, auth_headers):
        """Export should fall back to basic BOM when no snapshot exists."""
        cat = _seed_category(db)
        p = _seed_product(db, category_id=cat.id)

        resp = client.post("/product-db/api/solutions",
                           json={"name": "No Snap"}, headers=auth_headers)
        sol_id = resp.json()["solution"]["id"]

        client.post(f"/product-db/api/solutions/{sol_id}/items", json={
            "product_id": p.id, "quantity": 1, "unit_price": 100
        }, headers=auth_headers)

        resp = client.get(f"/product-db/api/solutions/{sol_id}/bom-snapshot/export-xlsx",
                          headers=auth_headers)
        assert resp.status_code == 200


# ============================================================
# Products: AI Fetch URL with redirect (69% → ~75%)
# ============================================================
class TestProductsAIFetchURL:
    @patch("httpx.get")
    @patch("app.services.ai_engine.engine")
    def test_ai_fetch_url_with_redirect(self, mock_engine, mock_get, auth_headers):
        mock_engine.api_key = ""

        # First response: 302 redirect
        mock_resp_redirect = MagicMock()
        mock_resp_redirect.status_code = 302
        mock_resp_redirect.headers = {"Location": "https://example.com/final"}

        # Second response: 200 with content
        mock_resp_final = MagicMock()
        mock_resp_final.status_code = 200
        mock_resp_final.text = "<html><title>Product Page</title><body>UG65 Gateway IP67</body></html>"
        mock_resp_final.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_resp_redirect, mock_resp_final]

        resp = client.post("/product-db/api/products/ai-fetch", json={
            "url": "https://example.com/redirect"
        }, headers=auth_headers)
        assert resp.status_code in (200, 201)

    def test_ai_fetch_invalid_url_format(self, auth_headers):
        resp = client.post("/product-db/api/products/ai-fetch", json={
            "url": "ftp://invalid.com"
        }, headers=auth_headers)
        assert resp.status_code == 400

    @patch("httpx.get")
    @patch("app.services.ai_engine.engine")
    def test_ai_fetch_url_empty_body(self, mock_engine, mock_get, auth_headers):
        mock_engine.api_key = ""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body></body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        resp = client.post("/product-db/api/products/ai-fetch", json={
            "url": "https://example.com/empty"
        }, headers=auth_headers)
        assert resp.status_code == 400

    @patch("httpx.get")
    @patch("app.services.ai_engine.engine")
    def test_ai_fetch_url_http_error(self, mock_engine, mock_get, auth_headers):
        mock_engine.api_key = ""
        import httpx as _httpx
        mock_get.side_effect = _httpx.HTTPError("Connection refused")

        resp = client.post("/product-db/api/products/ai-fetch", json={
            "url": "https://example.com/fail"
        }, headers=auth_headers)
        assert resp.status_code == 400


# ============================================================
# Products: AI Fetch File (69% → ~73%)
# ============================================================
class TestProductsAIFetchFile:
    def test_ai_fetch_file_txt(self, auth_headers):
        resp = client.post("/product-db/api/products/ai-fetch-file",
                           files={"file": ("spec.txt", io.BytesIO(b"UG65 LoRaWAN Gateway IP67"), "text/plain")},
                           headers=auth_headers)
        assert resp.status_code in (200, 201)

    def test_ai_fetch_file_unsupported(self, auth_headers):
        resp = client.post("/product-db/api/products/ai-fetch-file",
                           files={"file": ("test.mp4", io.BytesIO(b"fake video"), "video/mp4")},
                           headers=auth_headers)
        assert resp.status_code == 400


# ============================================================
# Agent: Hermes Proxy mock (49% → ~60%)
# ============================================================
class TestAgentHermesProxy:
    @patch("httpx.AsyncClient.stream")
    def test_agent_chat_connection_error(self, mock_stream, auth_headers):
        """Hermes connection error should return error SSE."""
        import httpx as _httpx

        async def raise_connect(*args, **kwargs):
            raise _httpx.ConnectError("Cannot connect")

        mock_stream.side_effect = raise_connect

        resp = client.post("/product-db/api/agent/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True
        }, headers=auth_headers)
        assert resp.status_code == 200
        body = resp.text
        assert "error" in body.lower() or "DONE" in body

    @patch("httpx.AsyncClient.stream")
    def test_agent_chat_non_200(self, mock_stream, auth_headers):
        """Hermes returns non-200 → error in SSE."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 500
        mock_resp.aread = AsyncMock(return_value=b'{"error": "internal"}')

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_stream.return_value = mock_ctx

        resp = client.post("/product-db/api/agent/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert "error" in resp.text.lower() or "500" in resp.text
