"""Round 10 回归：`/ai/chat` 的 DB 上下文分档（R73 问题 3）。

目标：**首轮全量（冷启动选型）、后续轮精简**，避免每轮把整库产品重发一遍
（实测单轮 input 一度到 51.7k tokens）。

- `_build_db_context(db, full=True)` 含全部产品 `[ID]`；`full=False` 只有词表
- 两档缓存互不污染
- `ai_chat` 首轮传 `full_db_context=True`，第二轮传 `False`
"""
import os
import tempfile
import json

_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["DEV_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-32charmin"

import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models.user import User
from app.models.product import Product
from app.models.category import Category
from app.models.ai_models import AIConversation
from app.auth import hash_password, create_token
from tests.conftest import create_test_schema, drop_test_schema
import app.routers.ai as ai_router

client = TestClient(app)
API = "/product-db/api"


@pytest.fixture(autouse=True)
def _clear_db_ctx_cache():
    """`_build_db_context` 有 300s TTL 缓存，跨用例会串（尤其造数据前后）。"""
    for k in ("full", "compact"):
        ai_router._db_ctx_cache[k] = {"ts": 0.0, "value": ""}
    yield
    for k in ("full", "compact"):
        ai_router._db_ctx_cache[k] = {"ts": 0.0, "value": ""}


@pytest.fixture
def db():
    create_test_schema()
    d = SessionLocal()
    if not d.query(User).filter_by(username="admin").first():
        d.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
    cat = d.query(Category).filter_by(name="网关").first()
    if not cat:
        cat = Category(name="网关", slug="gw-ctx", level=1, sort_order=0)
        d.add(cat)
        d.commit()
    if not d.query(Product).filter_by(model="CTX-1").first():
        d.add(Product(name="上下文测试产品", model="CTX-1", category_id=cat.id,
                      base_price=100, description="用于验证上下文分档", status="active"))
        d.commit()
    try:
        yield d
    finally:
        d.close()
        drop_test_schema()


def _headers():
    d = SessionLocal()
    try:
        u = d.query(User).filter_by(username="admin").first()
        return {"Authorization": f"Bearer {create_token(u.id, u.username)}"}
    finally:
        d.close()


class TestDbContextTiers:
    def test_full_tier_includes_products(self, db):
        ctx = ai_router._build_db_context(db, full=True)
        assert "[ID:" in ctx
        assert "上下文测试产品" in ctx

    def test_compact_tier_excludes_products(self, db):
        ctx = ai_router._build_db_context(db, full=False)
        assert "[ID:" not in ctx, "精简档不该含产品清单"
        assert "上下文测试产品" not in ctx
        # 但词表要在，否则模型不知道能搜什么
        assert "品类" in ctx and "厂商" in ctx and "传感器指标" in ctx
        assert "search_products" in ctx, "要提示改用工具检索"

    def test_caches_do_not_leak_between_tiers(self, db):
        """先取精简档再取全量档，全量档必须仍是全量（缓存不能串）。"""
        compact = ai_router._build_db_context(db, full=False)
        full = ai_router._build_db_context(db, full=True)
        assert "[ID:" not in compact
        assert "[ID:" in full

    def test_compact_is_smaller(self, db):
        """精简档必须真的更小 —— 这是省 token 的全部意义。

        用足够多的产品来比：只有一两个产品时，精简档那句提示语本身就可能比
        产品清单还长（真实库是 396 个产品，全量档 25k+ tokens）。
        """
        cat = db.query(Category).first()
        for i in range(20):
            db.add(Product(name=f"批量产品{i}", model=f"BULK-{i}", category_id=cat.id,
                           base_price=10, description="产品描述" * 20, status="active"))
        db.commit()

        compact = ai_router._build_db_context(db, full=False)
        full = ai_router._build_db_context(db, full=True)
        assert len(compact) < len(full)
        assert len(full) > 1000, "全量档应随产品数增长"


class TestFirstTurnUsesFullContext:
    @staticmethod
    def _fake_run_agent(captured: list):
        async def fake(messages, db, conv_id, user_id=None,
                       tool_definitions=None, full_db_context=True):
            captured.append(full_db_context)
            yield {"event": "text", "text": "好的"}
            yield {"event": "done", "tokens": {"in": 1, "out": 1}}
        return fake

    def test_first_turn_full_then_compact(self):
        create_test_schema()
        d = SessionLocal()
        if not d.query(User).filter_by(username="admin").first():
            d.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
            d.commit()
        d.close()

        captured: list = []
        with patch.object(ai_router, "run_agent", self._fake_run_agent(captured)):
            r1 = client.post(f"{API}/ai/chat", headers=_headers(),
                             json={"input": "找温湿度传感器"})
            assert r1.status_code == 200

            d = SessionLocal()
            conv = d.query(AIConversation).order_by(AIConversation.id.desc()).first()
            conv_id = conv.id
            d.close()

            r2 = client.post(f"{API}/ai/chat", headers=_headers(),
                             json={"input": "再便宜点的呢", "conversation_id": conv_id})
            assert r2.status_code == 200

        assert captured == [True, False], f"首轮应全量、次轮应精简，实际 {captured}"
        drop_test_schema()
