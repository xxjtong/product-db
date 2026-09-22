"""Round 11 回归：二档批量清理（R74）。

- `PUT /quotations/{id}/bom` 改收 Pydantic schema：类型不符明确 422
- 字典更新支持清空**可空**字段，NOT NULL 字段仍安全跳过
- 字典列表按 SQL 分页取数（不再是全表读进来再切）
- 同品类下 `spec_key` 不可重复（create / update 都拦）
- `/ai/chat` 的用量累加器在 `done` 之前就写好（中断轮靠它记账）
- 被 Hermes 忽略的 `AGENT_TOOLS` 已删除
"""
import os
import tempfile
import asyncio

_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["DEV_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-32charmin"

from unittest.mock import patch

from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models.user import User
from app.models.category import Category, CategorySpecDefinition
from app.models.dictionary import DictCommMethod
from app.models.quotation import Quotation
from app.models.ai_models import AIConversation
from app.auth import hash_password, create_token
from tests.conftest import create_test_schema, drop_test_schema
import app.routers.ai as ai_router
import app.routers.agent as agent_router

client = TestClient(app)
API = "/product-db/api"


def _setup():
    create_test_schema()
    db = SessionLocal()
    if not db.query(User).filter_by(username="admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
        db.commit()
    db.close()


def _headers():
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username="admin").first()
        return {"Authorization": f"Bearer {create_token(u.id, u.username)}"}
    finally:
        db.close()


def _new_quotation(title="BOM测试"):
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username="admin").first()
        qt = Quotation(quote_number=f"QT-TEST-{title}", title=title, created_by=u.id)
        db.add(qt)
        db.commit()
        db.refresh(qt)
        return qt.id
    finally:
        db.close()


class TestBomSchemaValidation:
    def setup_method(self):
        _setup()

    def teardown_method(self):
        drop_test_schema()

    def test_bad_type_is_rejected_with_422(self):
        """qty 传非数字 → 明确 422（原先裸 dict 会被 number_or 静默兜成默认值）。"""
        qid = _new_quotation()
        r = client.put(f"{API}/quotations/{qid}/bom", headers=_headers(),
                       json={"rows": [{"name": "A", "qty": "不是数字"}]})
        assert r.status_code == 422

    def test_missing_fields_default(self):
        qid = _new_quotation()
        r = client.put(f"{API}/quotations/{qid}/bom", headers=_headers(),
                       json={"rows": [{"name": "只有名字"}]})
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_qty_zero_is_kept(self):
        """0 是合法值（本次不采购但保留该行），不能被兜成 1。"""
        qid = _new_quotation()
        r = client.put(f"{API}/quotations/{qid}/bom", headers=_headers(),
                       json={"rows": [{"name": "A", "qty": 0, "price": 100}]})
        assert r.status_code == 200 and r.json()["total"] == 0

    def test_extra_fields_ignored(self):
        qid = _new_quotation()
        r = client.put(f"{API}/quotations/{qid}/bom", headers=_headers(),
                       json={"rows": [{"name": "A", "qty": 1, "price": 10, "未知字段": "x"}]})
        assert r.status_code == 200 and r.json()["total"] == 10


class TestDictUpdateClearable:
    def setup_method(self):
        _setup()
        db = SessionLocal()
        db.add(DictCommMethod(name="以太网", method_type="wired", description="原描述"))
        db.commit()
        self.did = db.query(DictCommMethod).filter_by(name="以太网").first().id
        db.close()

    def teardown_method(self):
        drop_test_schema()

    def test_nullable_field_can_be_cleared(self):
        """显式传 null 即清空（原先跳过 None，字段只能改不能清）。"""
        r = client.put(f"{API}/dicts/comm-methods/{self.did}", headers=_headers(),
                       json={"description": None})
        assert r.status_code == 200
        db = SessionLocal()
        try:
            assert db.get(DictCommMethod, self.did).description is None
        finally:
            db.close()

    def test_not_null_field_is_left_alone(self):
        """method_type 是 NOT NULL：传 null 不能把它写成 NULL（那会 500）。"""
        r = client.put(f"{API}/dicts/comm-methods/{self.did}", headers=_headers(),
                       json={"method_type": None, "description": "改描述"})
        assert r.status_code == 200
        db = SessionLocal()
        try:
            row = db.get(DictCommMethod, self.did)
            assert row.method_type == "wired", "NOT NULL 字段保持原值"
            assert row.description == "改描述"
        finally:
            db.close()


class TestDictListPagination:
    def setup_method(self):
        _setup()
        db = SessionLocal()
        for i in range(7):
            db.add(DictCommMethod(name=f"方式{i}", method_type="wired"))
        db.commit()
        db.close()

    def teardown_method(self):
        drop_test_schema()

    def test_per_page_limits_rows_but_total_is_full(self):
        r = client.get(f"{API}/dicts/comm-methods?page=1&per_page=3", headers=_headers())
        assert r.status_code == 200
        body = r.json()
        assert len(body["comm_methods"]) == 3
        assert body["total"] == 7

    def test_second_page(self):
        r = client.get(f"{API}/dicts/comm-methods?page=3&per_page=3", headers=_headers())
        assert len(r.json()["comm_methods"]) == 1


class TestSpecKeyUnique:
    def setup_method(self):
        _setup()
        db = SessionLocal()
        cat = Category(name="网关", slug="gw-spec", level=1, sort_order=0)
        db.add(cat)
        db.commit()
        self.cid = cat.id
        db.close()

    def teardown_method(self):
        drop_test_schema()

    def _payload(self, key="port_count"):
        return {"spec_key": key, "display_name": "端口数", "spec_type": "number"}

    def test_duplicate_spec_key_rejected(self):
        assert client.post(f"{API}/categories/{self.cid}/spec-definitions",
                           headers=_headers(), json=self._payload()).status_code == 201
        r = client.post(f"{API}/categories/{self.cid}/spec-definitions",
                        headers=_headers(), json=self._payload())
        assert r.status_code == 400
        assert "已存在" in r.json()["detail"]

    def test_update_onto_existing_key_rejected(self):
        client.post(f"{API}/categories/{self.cid}/spec-definitions",
                    headers=_headers(), json=self._payload("a_key"))
        client.post(f"{API}/categories/{self.cid}/spec-definitions",
                    headers=_headers(), json=self._payload("b_key"))
        db = SessionLocal()
        sid = db.query(CategorySpecDefinition).filter_by(spec_key="b_key").first().id
        db.close()
        r = client.put(f"{API}/categories/{self.cid}/spec-definitions/{sid}",
                       headers=_headers(), json={"spec_key": "a_key"})
        assert r.status_code == 400

    def test_same_key_in_other_category_is_fine(self):
        other = Category(name="传感器", slug="sensor-spec", level=1, sort_order=0)
        db = SessionLocal()
        db.add(other)
        db.commit()
        oid = other.id
        db.close()
        assert client.post(f"{API}/categories/{self.cid}/spec-definitions",
                           headers=_headers(), json=self._payload()).status_code == 201
        assert client.post(f"{API}/categories/{oid}/spec-definitions",
                           headers=_headers(), json=self._payload()).status_code == 201


class TestUsageSink:
    def setup_method(self):
        _setup()

    def teardown_method(self):
        drop_test_schema()

    def test_sink_filled_before_done(self):
        """用量在 `done` 事件之前就写进 sink —— 中断时 `done` 发不出去也能记账。"""
        db = SessionLocal()
        try:
            u = db.query(User).filter_by(username="admin").first()
            conv = AIConversation(user_id=u.id, title="用量测试")
            db.add(conv)
            db.commit()
            db.refresh(conv)
            conv_id = conv.id
        finally:
            db.close()

        async def fake_chat(messages, **kw):
            return {"choices": [{"message": {"content": "{}"}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 3}}

        async def run():
            sink = {"in": 0, "out": 0}
            db2 = SessionLocal()
            try:
                with patch("app.routers.ai.settings.AI_GATEWAY_KEY", "k"), \
                     patch("app.routers.ai.engine.chat", fake_chat):
                    agen = ai_router.run_agent([{"role": "user", "content": "hi"}],
                                               db2, conv_id, user_id=1, usage_sink=sink)
                    for _ in range(60):
                        try:
                            await agen.__anext__()
                        except StopAsyncIteration:
                            break
                        if sink["in"]:
                            break
                    await agen.aclose()
            finally:
                db2.close()
            return sink

        sink = asyncio.run(run())
        assert sink["in"] >= 11, f"sink 应已累计到已跑轮次的用量，实际 {sink}"


class TestAgentToolsRemoved:
    def test_agent_tools_is_gone(self):
        assert not hasattr(agent_router, "AGENT_TOOLS"), "被 Hermes 忽略的声明已删除"
