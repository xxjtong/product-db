"""Round 8 回归：报价单创建收敛为公共模块 + AI 改预览确认 + 用量记来源（R71）。

覆盖：
- services/quotation_service：preview 不落库、preview 与 create 结果一致、快照完整
- extra_items（预览里展示的补充产品）并入方案；方案已有产品不重复添加
- POST /quotations 复用同一实现；solution_id 不存在时回 404（不再静默给空单）
- /ai/chat 的工具裁剪：无方案上下文 → 只读；有权限 → 带写工具；无权 → 只读
- AIUsageLog.source 记录入口来源
"""
import os
import tempfile
import json
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
from app.models.solution import Solution, SolutionItem
from app.models.quotation import Quotation, QuotationItem
from app.models.ai_usage_log import AIUsageLog
from app.auth import hash_password, create_token
from tests.conftest import create_test_schema, drop_test_schema

client = TestClient(app)
API = "/product-db/api"


def _setup_db():
    create_test_schema()
    db = SessionLocal()
    if not db.query(User).filter_by(username="admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
    if not db.query(User).filter_by(username="u1").first():
        db.add(User(username="u1", password_hash=hash_password("password1"), role="user"))
    if not db.query(User).filter_by(username="u2").first():
        db.add(User(username="u2", password_hash=hash_password("password1"), role="user"))
    cat = db.query(Category).filter_by(name="网关").first()
    if not cat:
        cat = Category(name="网关", slug="gw-quote", level=1, sort_order=0)
        db.add(cat)
        db.commit()
    db.commit()
    return cat.id


def _headers(username: str):
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username=username).first()
        return {"Authorization": f"Bearer {create_token(u.id, u.username)}"}
    finally:
        db.close()


def _seed_product(name="测试产品", model="TEST-001", price=100, specs=None):
    db = SessionLocal()
    try:
        p = Product(name=name, model=model, category_id=_setup_db(),
                    base_price=price, cost_price=price * 0.6,
                    specs=specs if specs is not None else {"防护等级": "IP67"})
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


def _seed_solution(name="测试方案", owner="admin", items=None):
    db = SessionLocal()
    try:
        owner_id = db.query(User).filter_by(username=owner).first().id
        sol = Solution(name=name, client_name="某某公司", created_by=owner_id)
        db.add(sol)
        db.commit()
        db.refresh(sol)
        for pid, qty, price, disc in (items or []):
            db.add(SolutionItem(solution_id=sol.id, product_id=pid, quantity=qty,
                                unit_price=price, discount_rate=disc))
        db.commit()
        return sol.id
    finally:
        db.close()


# ============================================================
# service：preview 与 create
# ============================================================
class TestQuotationService:
    def setup_method(self):
        self.cat_id = _setup_db()

    def teardown_method(self):
        drop_test_schema()

    def test_preview_does_not_write_anything(self):
        from app.services.quotation_service import preview_quotation
        pid = _seed_product(price=100)
        sol_id = _seed_solution(items=[(pid, 2, 100, 100)])

        db = SessionLocal()
        try:
            sol = db.get(Solution, sol_id)
            preview = preview_quotation(db, sol)
            assert preview["count"] == 1
            assert preview["total"] == 200.0
            assert db.query(Quotation).count() == 0
            assert db.query(QuotationItem).count() == 0
        finally:
            db.close()

    def test_preview_matches_created_quotation(self):
        """用户看到的预览必须就是最终生成的内容 —— 两者共用同一套条目计算。"""
        from app.services.quotation_service import preview_quotation, create_quotation_from_solution
        p1 = _seed_product("产品甲", "P-A", price=100)
        p2 = _seed_product("产品乙", "P-B", price=250)
        sol_id = _seed_solution(items=[(p1, 2, 100, 100), (p2, 1, 250, 90)])

        db = SessionLocal()
        try:
            sol = db.get(Solution, sol_id)
            extra = [{"product_id": _seed_product("产品丙", "P-C", price=50), "quantity": 4}]
            preview = preview_quotation(db, sol, extra)
            user = db.query(User).filter_by(username="admin").first()
            qt = create_quotation_from_solution(db, sol, user, extra_items=extra)
            db.commit()

            assert qt.total_amount == preview["total"]
            created = db.query(QuotationItem).filter_by(quotation_id=qt.id)\
                .order_by(QuotationItem.sort_order).all()
            assert len(created) == len(preview["items"]) == 3
            for row, prev in zip(created, preview["items"]):
                assert row.product_id == prev["product_id"]
                assert float(row.amount) == prev["amount"]
        finally:
            db.close()

    def test_discount_participates_in_amount(self):
        from app.services.quotation_service import preview_quotation
        pid = _seed_product(price=100)
        sol_id = _seed_solution(items=[(pid, 2, 100, 90)])   # 九折
        db = SessionLocal()
        try:
            preview = preview_quotation(db, db.get(Solution, sol_id))
            assert preview["total"] == 180.0
        finally:
            db.close()

    def test_snapshot_is_complete(self):
        """快照必须是完整 to_dict（含 specs）—— 原先 AI 那条只存 name/model/sku，
        导致 AI 建的报价单导出时「功能描述」列缺规格参数。"""
        from app.services.quotation_service import create_quotation_from_solution
        pid = _seed_product(price=100, specs={"防护等级": "IP67", "尺寸": "100x50"})
        sol_id = _seed_solution(items=[(pid, 1, 100, 100)])
        db = SessionLocal()
        try:
            sol = db.get(Solution, sol_id)
            user = db.query(User).filter_by(username="admin").first()
            qt = create_quotation_from_solution(db, sol, user)
            db.commit()
            item = db.query(QuotationItem).filter_by(quotation_id=qt.id).first()
            assert item.product_snapshot.get("specs") == {"防护等级": "IP67", "尺寸": "100x50"}
            assert item.product_snapshot.get("name") == "测试产品"
        finally:
            db.close()

    def test_create_records_creator_and_number(self):
        from app.services.quotation_service import create_quotation_from_solution
        pid = _seed_product(price=100)
        sol_id = _seed_solution(items=[(pid, 1, 100, 100)])
        db = SessionLocal()
        try:
            sol = db.get(Solution, sol_id)
            user = db.query(User).filter_by(username="admin").first()
            qt = create_quotation_from_solution(db, sol, user)
            db.commit()
            assert qt.created_by == user.id
            assert qt.quote_number.startswith("QT-")
            assert qt.title == "测试方案"
            assert qt.client_name == "某某公司"
        finally:
            db.close()

    def test_extra_items_are_added_to_solution_once(self):
        """extra_items 里方案已有的产品不重复添加、不改数量。"""
        from app.services.quotation_service import create_quotation_from_solution
        pid = _seed_product(price=100)
        new_pid = _seed_product("补充产品", "EXT-1", price=30)
        sol_id = _seed_solution(items=[(pid, 2, 100, 100)])
        db = SessionLocal()
        try:
            sol = db.get(Solution, sol_id)
            user = db.query(User).filter_by(username="admin").first()
            create_quotation_from_solution(db, sol, user, extra_items=[
                {"product_id": pid, "quantity": 99},      # 已在方案里 → 忽略
                {"product_id": new_pid, "quantity": 3},   # 新增
                {"product_id": 999999, "quantity": 1},    # 不存在 → 忽略
            ])
            db.commit()
            rows = db.query(SolutionItem).filter_by(solution_id=sol_id).all()
            by_pid = {r.product_id: float(r.quantity) for r in rows}
            assert len(rows) == 2
            assert by_pid[pid] == 2, "方案里已有的产品数量不得被覆盖"
            assert by_pid[new_pid] == 3
        finally:
            db.close()

    def test_preview_reports_pending_new_items(self):
        from app.services.quotation_service import preview_quotation
        new_pid = _seed_product("待并入产品", "NEW-1", price=30)
        sol_id = _seed_solution(items=[])
        db = SessionLocal()
        try:
            preview = preview_quotation(db, db.get(Solution, sol_id),
                                        [{"product_id": new_pid, "quantity": 2}])
            assert [n["product_id"] for n in preview["new_items"]] == [new_pid]
            assert preview["total"] == 60.0
            assert db.query(SolutionItem).filter_by(solution_id=sol_id).count() == 0, "预览不得改方案"
        finally:
            db.close()


# ============================================================
# POST /quotations 走同一实现
# ============================================================
class TestQuotationEndpointReusesService:
    def setup_method(self):
        self.cat_id = _setup_db()

    def teardown_method(self):
        drop_test_schema()

    def test_create_with_extra_items(self):
        pid = _seed_product(price=100)
        extra_pid = _seed_product("附加产品", "EXT-2", price=20)
        sol_id = _seed_solution(items=[(pid, 1, 100, 100)])

        resp = client.post(f"{API}/quotations", headers=_headers("admin"),
                           json={"solution_id": sol_id,
                                 "extra_items": [{"product_id": extra_pid, "quantity": 5}]})
        assert resp.status_code == 201
        qt = resp.json()["quotation"]
        assert qt["total_amount"] == 200.0     # 100 + 20*5
        db = SessionLocal()
        try:
            assert db.query(SolutionItem).filter_by(solution_id=sol_id).count() == 2
        finally:
            db.close()

    def test_missing_solution_returns_404(self):
        """以前 `if sol:` 为假会静默创建空白报价单，调用方以为复制了方案。"""
        resp = client.post(f"{API}/quotations", headers=_headers("admin"),
                           json={"solution_id": 999999})
        assert resp.status_code == 404

    def test_blank_quotation_without_solution_still_works(self):
        resp = client.post(f"{API}/quotations", headers=_headers("admin"),
                           json={"title": "空白报价单"})
        assert resp.status_code == 201
        assert resp.json()["quotation"]["title"] == "空白报价单"

    def test_foreign_solution_is_rejected(self):
        pid = _seed_product(price=100)
        sol_id = _seed_solution(name="u1的方案", owner="u1", items=[(pid, 1, 100, 100)])
        resp = client.post(f"{API}/quotations", headers=_headers("u2"),
                           json={"solution_id": sol_id})
        assert resp.status_code == 403


# ============================================================
# /ai/chat 的工具裁剪 + 来源记录
# ============================================================
class TestAiChatToolScoping:
    def setup_method(self):
        self.cat_id = _setup_db()

    def teardown_method(self):
        drop_test_schema()

    @staticmethod
    def _fake_chat(captured: list):
        async def fake(messages, **kwargs):
            captured.append(kwargs)
            return {"choices": [{"message": {"content": "好的"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        return fake

    def _chat(self, payload, username="admin"):
        with patch("app.routers.ai.settings.AI_GATEWAY_KEY", "test-key"), \
             patch("app.routers.ai.engine.chat", self._fake_chat(self.calls)):
            resp = client.post(f"{API}/ai/chat", headers=_headers(username), json=payload)
        return resp

    def test_no_solution_context_gets_readonly_tools(self):
        self.calls = []
        resp = self._chat({"input": "有哪些网关", "source": "floating"})
        assert resp.status_code == 200
        tool_sets = [c.get("tools") for c in self.calls if c.get("tools") is not None]
        assert tool_sets, "应至少有一次带 tools 的调用"
        names = [t["function"]["name"] for t in tool_sets[0]]
        assert "create_quotation" not in names, "无方案上下文时不得给写工具"
        assert "search_products" in names

    def test_owned_solution_context_gets_write_tool(self):
        pid = _seed_product(price=100)
        sol_id = _seed_solution(items=[(pid, 1, 100, 100)])
        self.calls = []
        resp = self._chat({"input": "生成报价单", "source": "solution", "solution_id": sol_id})
        assert resp.status_code == 200
        tool_sets = [c.get("tools") for c in self.calls if c.get("tools") is not None]
        names = [t["function"]["name"] for t in tool_sets[0]]
        assert "create_quotation" in names

    def test_foreign_solution_context_falls_back_to_readonly(self):
        pid = _seed_product(price=100)
        sol_id = _seed_solution(name="u1的方案", owner="u1", items=[(pid, 1, 100, 100)])
        self.calls = []
        resp = self._chat({"input": "生成报价单", "solution_id": sol_id}, username="u2")
        assert resp.status_code == 200
        tool_sets = [c.get("tools") for c in self.calls if c.get("tools") is not None]
        names = [t["function"]["name"] for t in tool_sets[0]]
        assert "create_quotation" not in names, "无权方案不得拿到写工具"

    def test_source_is_recorded_in_usage_log(self):
        self.calls = []
        resp = self._chat({"input": "你好", "source": "solution"})
        assert resp.status_code == 200
        db = SessionLocal()
        try:
            row = db.query(AIUsageLog).filter_by(operation="chat").order_by(AIUsageLog.id.desc()).first()
            assert row is not None
            assert row.source == "solution"
        finally:
            db.close()

    def test_readonly_tool_set_definition(self):
        from app.services.ai_tools import TOOL_DEFINITIONS, READ_ONLY_TOOL_DEFINITIONS
        assert len(READ_ONLY_TOOL_DEFINITIONS) == len(TOOL_DEFINITIONS) - 1
        assert "create_quotation" not in [t["function"]["name"] for t in READ_ONLY_TOOL_DEFINITIONS]
