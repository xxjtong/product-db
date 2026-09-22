"""Round 5 回归：计数限流模块化 + 审计/数据一致性修复。

覆盖：
- services/rate_limit 两种原语（DB 失败计数 / 进程内频次计数）
- #1 注册限流 + 注册不再写 login_logs（审计口径）
- #2 禁用账户的登录尝试要落审计并计入失败计数
- #3 /ai/chat 流中断后不会留下孤立的 user 消息
- #4 update_product 允许清空 specs/urls/custom_fields
- #5 字典/供应商删除前校验产品引用
- #7 admin 建号/改密的密码长度下限
"""
import os
import tempfile
import json
from unittest.mock import patch

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
from app.models.dictionary import Manufacturer, DictCommMethod
from app.models.mapping import ProductCommMethod
from app.models.login_log import LoginLog
from app.models.ai_models import AIConversation, AIMessage
from app.auth import hash_password, create_token
from tests.conftest import create_test_schema, drop_test_schema

client = TestClient(app)
API = "/product-db/api"


def _setup_db():
    create_test_schema()
    db = SessionLocal()
    if not db.query(User).filter_by(username="admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
        db.commit()
    db.close()


def _headers(db):
    admin = db.query(User).filter_by(username="admin").first()
    return {"Authorization": f"Bearer {create_token(admin.id, admin.username)}"}


# ============================================================
# services/rate_limit —— 两种原语
# ============================================================
class TestRateLimitModule:
    def setup_method(self):
        _setup_db()

    def teardown_method(self):
        drop_test_schema()

    def test_db_primitive_counts_failures_per_ip(self):
        from app.services import rate_limit
        db = SessionLocal()
        try:
            rate_limit.record_failure(db, ip="1.1.1.1", user_agent="ua")
            rate_limit.record_failure(db, ip="1.1.1.1", user_agent="ua")
            rate_limit.record_failure(db, ip="2.2.2.2", user_agent="ua")
            assert rate_limit.count_failures(db, "1.1.1.1", 300) == 2
            assert rate_limit.count_failures(db, "2.2.2.2", 300) == 1
            assert rate_limit.is_rate_limited(db, "1.1.1.1", limit=3, window=300) is False
            assert rate_limit.is_rate_limited(db, "1.1.1.1", limit=2, window=300) is True
        finally:
            db.close()

    def test_db_primitive_ignores_success_rows(self):
        """限流只数失败行 —— 成功登录不该占用失败额度。"""
        from app.services import rate_limit
        db = SessionLocal()
        try:
            db.add(LoginLog(ip_address="3.3.3.3", success=True))
            db.commit()
            assert rate_limit.count_failures(db, "3.3.3.3", 300) == 0
        finally:
            db.close()

    def test_memory_primitive_check_and_hit_blocks_at_limit(self):
        from app.services import rate_limit
        for i in range(3):
            assert rate_limit.check_and_hit("k", limit=3, window=60) is False, f"第{i+1}次不该被拦"
        assert rate_limit.check_and_hit("k", limit=3, window=60) is True
        # 超限后不继续计数：窗口滑出即可自然恢复
        assert rate_limit.count("k", 60) == 3

    def test_memory_primitive_isolated_by_key(self):
        from app.services import rate_limit
        for _ in range(3):
            rate_limit.check_and_hit("a", limit=3, window=60)
        assert rate_limit.check_and_hit("b", limit=3, window=60) is False

    def test_memory_primitive_window_expiry(self):
        from app.services import rate_limit
        for _ in range(2):
            rate_limit.hit("w", 60)
        assert rate_limit.count("w", 60) == 2
        # 窗口为 0 秒：所有历史命中都已过期
        assert rate_limit.count("w", 0) == 0

    def test_reset_clears_one_or_all(self):
        from app.services import rate_limit
        rate_limit.hit("x", 60)
        rate_limit.hit("y", 60)
        rate_limit.reset("x")
        assert rate_limit.count("x", 60) == 0
        assert rate_limit.count("y", 60) == 1
        rate_limit.reset()
        assert rate_limit.count("y", 60) == 0


# ============================================================
# #1 注册：限流 + 审计口径
# ============================================================
class TestRegisterRateLimitAndAudit:
    def setup_method(self):
        _setup_db()
        db = SessionLocal()
        from app.models.system_setting import SystemSetting
        db.add(SystemSetting(key="registration_open", value="true"))
        db.commit()
        db.close()

    def teardown_method(self):
        drop_test_schema()

    def test_register_success_writes_no_login_log(self):
        """注册既不是登录也不是登录失败，不该进 login_logs（此前写了一条 success=True）。"""
        resp = client.post(f"{API}/auth/register", json={
            "username": "newbie1", "password": "pass12345", "email": "n1@t.com",
        })
        assert resp.status_code == 200
        db = SessionLocal()
        try:
            assert db.query(LoginLog).count() == 0
        finally:
            db.close()

    def test_register_is_rate_limited_per_ip(self):
        from app.config import settings
        for i in range(settings.REGISTER_RATE_LIMIT):
            r = client.post(f"{API}/auth/register", json={
                "username": f"bulk{i}", "password": "pass12345", "email": f"b{i}@t.com",
            })
            assert r.status_code == 200, f"第{i+1}次注册应成功，实际 {r.status_code}"
        r = client.post(f"{API}/auth/register", json={
            "username": "bulk_overflow", "password": "pass12345", "email": "bo@t.com",
        })
        assert r.status_code == 429

    def test_register_attempts_do_not_consume_login_failure_bucket(self):
        """注册失败不能占用登录失败额度 —— 否则正常用户注册一次就少一次登录机会。"""
        client.post(f"{API}/auth/register", json={
            "username": "admin", "password": "pass12345", "email": "dup@t.com",
        })  # 400 用户名已存在
        db = SessionLocal()
        try:
            assert db.query(LoginLog).count() == 0
        finally:
            db.close()


# ============================================================
# #2 禁用账户登录落审计
# ============================================================
class TestDisabledAccountAudit:
    def setup_method(self):
        _setup_db()
        db = SessionLocal()
        db.add(User(username="banned", password_hash=hash_password("pass12345"),
                    role="user", is_active=False))
        db.commit()
        db.close()

    def teardown_method(self):
        drop_test_schema()

    def test_disabled_login_writes_failure_log(self):
        resp = client.post(f"{API}/auth/login", json={
            "username": "banned", "password": "pass12345",
        })
        assert resp.status_code == 403
        db = SessionLocal()
        try:
            log = db.query(LoginLog).order_by(LoginLog.id.desc()).first()
            assert log is not None, "禁用账户的登录尝试必须落审计"
            assert log.success is False
            assert log.user_id == db.query(User).filter_by(username="banned").first().id
        finally:
            db.close()

    def test_disabled_login_counts_toward_rate_limit(self):
        """反复尝试已禁用账户同样会触发限流（此前这批尝试完全不可见）。"""
        from app.config import settings
        for _ in range(settings.LOGIN_RATE_LIMIT):
            client.post(f"{API}/auth/login", json={"username": "banned", "password": "pass12345"})
        resp = client.post(f"{API}/auth/login", json={"username": "banned", "password": "pass12345"})
        assert resp.status_code == 429


# ============================================================
# #3 SSE 中断不留孤立 user 消息
# ============================================================
class TestInterruptedChatKeepsPair:
    def setup_method(self):
        _setup_db()

    def teardown_method(self):
        drop_test_schema()

    def test_stream_error_writes_placeholder_assistant(self):
        from app.routers import ai as ai_router

        async def boom(*args, **kwargs):
            raise RuntimeError("llm down")
            yield  # pragma: no cover —— 使其成为 async generator

        db = SessionLocal()
        headers = _headers(db)
        db.close()

        with patch.object(ai_router, "run_agent", boom):
            resp = client.post(f"{API}/ai/chat", json={"input": "查一下温湿度传感器"},
                               headers=headers)
        assert resp.status_code == 200  # SSE 已开始，错误以事件形式回传
        assert "error" in resp.text

        db = SessionLocal()
        try:
            conv = db.query(AIConversation).first()
            msgs = db.query(AIMessage).filter_by(conversation_id=conv.id)\
                .order_by(AIMessage.id).all()
            roles = [m.role for m in msgs]
            assert roles == ["user", "assistant"], f"user/assistant 必须成对，实际 {roles}"
            assert ai_router._INTERRUPTED_REPLY in msgs[1].content
        finally:
            db.close()

    def test_normal_reply_is_not_padded(self):
        """正常路径不该被补占位 —— replied 标记要准。"""
        from app.routers import ai as ai_router

        async def ok(*args, **kwargs):
            yield {"event": "text", "text": "好的"}
            yield {"event": "done", "tokens": {"in": 1, "out": 1}}

        db = SessionLocal()
        headers = _headers(db)
        db.close()

        with patch.object(ai_router, "run_agent", ok):
            resp = client.post(f"{API}/ai/chat", json={"input": "你好"}, headers=headers)
        assert resp.status_code == 200

        db = SessionLocal()
        try:
            conv = db.query(AIConversation).first()
            msgs = db.query(AIMessage).filter_by(conversation_id=conv.id).all()
            assert [m.role for m in msgs] == ["user"]
            assert ai_router._INTERRUPTED_REPLY not in "".join(m.content or "" for m in msgs)
        finally:
            db.close()


# ============================================================
# #4 产品 JSON 字段可清空
# ============================================================
class TestProductJsonFieldsClearable:
    def setup_method(self):
        _setup_db()
        db = SessionLocal()
        cat = Category(name="网关", slug="gw", level=1, sort_order=0)
        db.add(cat)
        db.commit()
        p = Product(name="测试网关", model="GW-1", category_id=cat.id,
                    specs={"防护等级": "IP67"}, urls={"manual": "http://a/b"},
                    custom_fields={"产地": "深圳"})
        db.add(p)
        db.commit()
        self.pid = p.id
        db.close()

    def teardown_method(self):
        drop_test_schema()

    def test_empty_dict_payload_clears_json_fields(self):
        db = SessionLocal()
        headers = _headers(db)
        db.close()
        resp = client.put(f"{API}/products/{self.pid}", headers=headers, json={
            "specs": {}, "urls": {}, "custom_fields": {},
        })
        assert resp.status_code == 200
        db = SessionLocal()
        try:
            p = db.get(Product, self.pid)
            assert not p.specs, f"specs 应被清空，实际 {p.specs}"
            assert not p.urls
            assert not p.custom_fields
        finally:
            db.close()

    def test_omitted_field_is_left_untouched(self):
        """不传的字段不能被顺手清掉 —— 这是 partial update 的基本契约。"""
        db = SessionLocal()
        headers = _headers(db)
        db.close()
        resp = client.put(f"{API}/products/{self.pid}", headers=headers,
                          json={"description": "只改描述"})
        assert resp.status_code == 200
        db = SessionLocal()
        try:
            p = db.get(Product, self.pid)
            assert p.specs == {"防护等级": "IP67"}
            assert p.custom_fields == {"产地": "深圳"}
        finally:
            db.close()


# ============================================================
# #5 字典/供应商删除前的引用校验
# ============================================================
class TestDictDeleteReferenceGuard:
    def setup_method(self):
        _setup_db()
        db = SessionLocal()
        cat = Category(name="网关", slug="gw2", level=1, sort_order=0)
        db.add(cat)
        db.commit()
        self.cat_id = cat.id
        db.close()

    def teardown_method(self):
        drop_test_schema()

    def _headers(self):
        db = SessionLocal()
        h = _headers(db)
        db.close()
        return h

    def test_manufacturer_in_use_returns_409(self):
        db = SessionLocal()
        m = Manufacturer(name="星纵")
        db.add(m)
        db.commit()
        db.add(Product(name="P", model="M1", category_id=self.cat_id, manufacturer_id=m.id))
        db.commit()
        mid = m.id
        db.close()
        resp = client.delete(f"{API}/dicts/manufacturers/{mid}", headers=self._headers())
        assert resp.status_code == 409
        assert "引用" in resp.json()["detail"]

    def test_unused_manufacturer_can_be_deleted(self):
        db = SessionLocal()
        m = Manufacturer(name="闲置厂商")
        db.add(m)
        db.commit()
        mid = m.id
        db.close()
        resp = client.delete(f"{API}/dicts/manufacturers/{mid}", headers=self._headers())
        assert resp.status_code == 200

    def test_comm_method_in_use_returns_409(self):
        """CASCADE 的映射表最危险：不加这道闸，删字典会静默删掉产品的通讯方式。"""
        db = SessionLocal()
        cm = DictCommMethod(name="LoRaWAN", method_type="wireless")
        db.add(cm)
        db.commit()
        p = Product(name="P2", model="M2", category_id=self.cat_id)
        db.add(p)
        db.commit()
        db.add(ProductCommMethod(product_id=p.id, method_id=cm.id))
        db.commit()
        cmid = cm.id
        db.close()
        resp = client.delete(f"{API}/dicts/comm-methods/{cmid}", headers=self._headers())
        assert resp.status_code == 409
        # 映射行必须还在
        db = SessionLocal()
        try:
            assert db.query(ProductCommMethod).filter_by(method_id=cmid).count() == 1
        finally:
            db.close()

    def test_supplier_in_use_returns_409(self):
        db = SessionLocal()
        s = Supplier(name="供应商甲")
        db.add(s)
        db.commit()
        db.add(Product(name="P3", model="M3", category_id=self.cat_id, supplier_id=s.id))
        db.commit()
        sid = s.id
        db.close()
        resp = client.delete(f"{API}/suppliers/{sid}", headers=self._headers())
        assert resp.status_code == 409


# ============================================================
# #7 admin 建号/改密的密码下限
# ============================================================
class TestAdminPasswordPolicy:
    def setup_method(self):
        _setup_db()

    def teardown_method(self):
        drop_test_schema()

    def _headers(self):
        db = SessionLocal()
        h = _headers(db)
        db.close()
        return h

    def test_short_password_rejected_on_create(self):
        resp = client.post(f"{API}/admin/users", headers=self._headers(), json={
            "username": "shorty", "password": "1234567", "role": "user",
        })
        assert resp.status_code == 400
        assert "8" in resp.json()["detail"]

    def test_short_password_rejected_on_update(self):
        db = SessionLocal()
        u = User(username="target", password_hash=hash_password("pass12345"), role="user")
        db.add(u)
        db.commit()
        uid = u.id
        db.close()
        resp = client.put(f"{API}/admin/users/{uid}", headers=self._headers(),
                          json={"password": "123"})
        assert resp.status_code == 400

    def test_valid_password_still_accepted(self):
        resp = client.post(f"{API}/admin/users", headers=self._headers(), json={
            "username": "okuser", "password": "goodpass123", "role": "user",
        })
        assert resp.status_code == 200
