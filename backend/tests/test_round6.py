"""Round 6 回归：导入幂等 + agent 自测审批钩子的两处修复。

覆盖：
- 导入按「名称 + 型号」去重（同批内重复、与库中重复、大小写变体）
- 导入厂商大小写不敏感（Acme / acme 不再各建一条）
- agent 的「测试审批」自测钩子限 admin
- 审批通过后追加的是合法消息（原先凭空塞 role:"tool" 会被 Hermes 400 拒掉）
"""
import os
import tempfile
from unittest.mock import patch, AsyncMock

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
from app.models.dictionary import Manufacturer
from app.auth import hash_password, create_token
from tests.conftest import create_test_schema, drop_test_schema

client = TestClient(app)
API = "/product-db/api"

# 列映射：0=名称 1=型号 2=品类 3=厂商 4=价格
MAPPING = {"0": "name", "1": "model", "2": "category", "3": "manufacturer", "4": "price"}


def _setup_db():
    create_test_schema()
    db = SessionLocal()
    if not db.query(User).filter_by(username="admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
    if not db.query(User).filter_by(username="normal").first():
        db.add(User(username="normal", password_hash=hash_password("normal123"), role="user"))
    if not db.query(Category).filter_by(name="网关").first():
        db.add(Category(name="网关", slug="gw-import", level=1, sort_order=0))
    db.commit()
    db.close()


def _headers(username: str):
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username=username).first()
        return {"Authorization": f"Bearer {create_token(u.id, u.username)}"}
    finally:
        db.close()


def _do_import(rows, headers=None):
    return client.post(f"{API}/products/import-confirm", headers=headers or _headers("admin"),
                       json={"mapping": MAPPING, "rows": rows})


# ============================================================
# 导入幂等
# ============================================================
class TestImportIdempotency:
    def setup_method(self):
        _setup_db()

    def teardown_method(self):
        drop_test_schema()

    def test_same_file_imported_twice_does_not_duplicate(self):
        rows = [
            ["温湿度传感器", "WS-1", "网关", "Acme", "100"],
            ["网关主机", "GW-1", "网关", "Acme", "200"],
        ]
        first = _do_import(rows)
        assert first.status_code == 200
        assert first.json() == {"imported": 2, "skipped": 0}

        second = _do_import(rows)
        assert second.status_code == 200
        assert second.json() == {"imported": 0, "skipped": 2}, "重复导入必须全部跳过"

        db = SessionLocal()
        try:
            assert db.query(Product).count() == 2
        finally:
            db.close()

    def test_duplicate_rows_within_one_batch_are_skipped(self):
        rows = [
            ["重复产品", "DUP-1", "网关", "Acme", "1"],
            ["重复产品", "DUP-1", "网关", "Acme", "1"],
        ]
        resp = _do_import(rows)
        assert resp.json() == {"imported": 1, "skipped": 1}

    def test_case_variant_counts_as_duplicate(self):
        _do_import([["Product X", "PX-1", "网关", "Acme", "1"]])
        resp = _do_import([["product x", "px-1", "网关", "Acme", "1"]])
        assert resp.json() == {"imported": 0, "skipped": 1}
        db = SessionLocal()
        try:
            assert db.query(Product).count() == 1
        finally:
            db.close()

    def test_same_name_different_model_is_not_duplicate(self):
        """去重键是「名称+型号」：同名不同型号是不同产品，不能被误跳过。"""
        _do_import([["同系列", "S-1", "网关", "Acme", "1"]])
        resp = _do_import([["同系列", "S-2", "网关", "Acme", "1"]])
        assert resp.json() == {"imported": 1, "skipped": 0}
        db = SessionLocal()
        try:
            assert db.query(Product).count() == 2
        finally:
            db.close()

    def test_manufacturer_match_is_case_insensitive(self):
        _do_import([
            ["甲产品", "M-1", "网关", "Acme", "1"],
            ["乙产品", "M-2", "网关", "acme", "1"],
            ["丙产品", "M-3", "网关", "ACME", "1"],
        ])
        db = SessionLocal()
        try:
            names = [m.name for m in db.query(Manufacturer).all()]
            assert len(names) == 1, f"大小写变体应复用同一厂商，实际 {names}"
            # 三条产品都挂到同一个厂商上
            assert db.query(Product).filter(Product.manufacturer_id.isnot(None)).count() == 3
        finally:
            db.close()

    def test_existing_manufacturer_reused_across_imports(self):
        db = SessionLocal()
        db.add(Manufacturer(name="星纵"))
        db.commit()
        db.close()
        _do_import([["新产品", "N-1", "网关", "星纵", "1"]])
        db = SessionLocal()
        try:
            assert db.query(Manufacturer).filter_by(name="星纵").count() == 1
        finally:
            db.close()


# ============================================================
# agent 自测审批钩子
# ============================================================
class TestAgentApprovalHook:
    def setup_method(self):
        _setup_db()

    def teardown_method(self):
        drop_test_schema()

    @staticmethod
    def _capturing_hermes(captured: dict):
        def fake(model, messages, tools=None):
            captured["messages"] = [dict(m) for m in messages]
            async def empty():
                return
                yield  # pragma: no cover —— 使其成为 async generator
            return empty()
        return fake

    def test_non_admin_cannot_trigger_approval(self):
        """普通用户发「测试审批」不该凭空插出审批卡 —— 只当普通对话转发。"""
        from app.routers import agent as agent_router
        captured = {}
        with patch.object(agent_router, "_call_hermes", self._capturing_hermes(captured)):
            resp = client.post(f"{API}/agent/chat",
                               json={"messages": [{"role": "user", "content": "测试审批"}]},
                               headers=_headers("normal"))
        assert resp.status_code == 200
        assert "approval_required" not in resp.text
        assert "messages" in captured, "应走正常转发路径"

    def test_admin_can_trigger_approval(self):
        from app.routers import agent as agent_router
        captured = {}
        with patch.object(agent_router.approval_manager, "wait_for_decision",
                          AsyncMock(return_value={"approved": False, "reason": "测试拒绝"})), \
             patch.object(agent_router, "_call_hermes", self._capturing_hermes(captured)):
            resp = client.post(f"{API}/agent/chat",
                               json={"messages": [{"role": "user", "content": "测试审批"}]},
                               headers=_headers("admin"))
        assert resp.status_code == 200
        assert "approval_required" in resp.text
        assert "approval_result" in resp.text
        assert "messages" not in captured, "拒绝分支不该继续调 Hermes"

    def test_approved_flow_sends_no_dangling_tool_message(self):
        """审批通过后追加的消息必须合法。

        原先追加的是 role:"tool" + 编造的 tool_call_id，而前面没有带 tool_calls 的
        assistant 消息与之配对 —— OpenAI 兼容接口会 400，用户审批通过后反而没回复。
        """
        from app.routers import agent as agent_router
        captured = {}
        with patch.object(agent_router.approval_manager, "wait_for_decision",
                          AsyncMock(return_value={"approved": True, "reason": ""})), \
             patch.object(agent_router, "_call_hermes", self._capturing_hermes(captured)):
            resp = client.post(f"{API}/agent/chat",
                               json={"messages": [{"role": "user", "content": "测试审批"}]},
                               headers=_headers("admin"))
        assert resp.status_code == 200
        assert "approval_result" in resp.text

        sent = captured.get("messages")
        assert sent, "通过分支应继续调 Hermes"
        roles = [m["role"] for m in sent]
        assert "tool" not in roles, f"不得出现无配对的 role:tool 消息，实际 {roles}"
        # 授权结果以 user 消息追加，且是最后一条
        assert roles[-1] == "user"
        assert "已批准" in sent[-1]["content"]
        # tool_calls 与 tool_call_id 都不该被捏造出来
        assert all("tool_call_id" not in m for m in sent)
