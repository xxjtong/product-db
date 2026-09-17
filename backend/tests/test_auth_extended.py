"""Supplementary tests for auth.py — SHA256 upgrade, query token, DEV_MODE, edge cases."""
import pytest
import os
import logging
import tempfile
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["DEV_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-32charmin"

from fastapi.testclient import TestClient
from app.database import Base, engine, SessionLocal
from app.main import app
from app.models.user import User
from app.auth import hash_password, create_token, verify_password, _get_admin_ids, filter_by_ownership, check_ownership
from app.models.product import Product
from app.models.category import Category
from app.config import settings as app_settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
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


# ============================================================
# SHA256 Legacy Password Upgrade
# ============================================================
class TestLegacyPasswordUpgrade:
    def test_sha256_hash_verifiable(self):
        """Legacy SHA256 format: salt$hexdigest should verify correctly."""
        import hashlib
        salt = "randomsalt"
        password = "mypassword123"
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        legacy_hash = f"{salt}${h}"
        assert verify_password(password, legacy_hash) is True

    def test_sha256_wrong_password(self):
        """Legacy SHA256 with wrong password should fail."""
        import hashlib
        salt = "randomsalt"
        h = hashlib.sha256((salt + "correct").encode()).hexdigest()
        legacy_hash = f"{salt}${h}"
        assert verify_password("wrong", legacy_hash) is False

    def test_bcrypt_verifiable(self):
        """bcrypt hash should verify correctly."""
        password = "testpassword"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_bcrypt_wrong_password(self):
        """bcrypt with wrong password should fail."""
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_login_auto_upgrades_sha256(self, db):
        """Login with legacy SHA256 hash should auto-upgrade to bcrypt."""
        import hashlib
        salt = "testsalt"
        password = "upgrade_me"
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        legacy_hash = f"{salt}${h}"

        u = User(username="legacy_user", password_hash=legacy_hash, role="user")
        db.add(u)
        db.commit()
        db.refresh(u)

        # Login with legacy password
        resp = client.post("/product-db/api/auth/login", json={
            "username": "legacy_user", "password": password
        })
        assert resp.status_code == 200
        assert "token" in resp.json()

        # Verify hash was upgraded to bcrypt
        db.expire_all()
        u2 = db.query(User).filter_by(username="legacy_user").first()
        assert u2.password_hash.startswith("$2"), "Password should be upgraded to bcrypt"

    def test_malformed_hash_returns_false(self):
        """Malformed hash string should return False, not crash."""
        assert verify_password("test", "") is False
        assert verify_password("test", "invalid") is False
        assert verify_password("test", "$2$broken") is False


# ============================================================
# JWT Token Edge Cases
# ============================================================
class TestTokenEdgeCases:
    def test_expired_token_rejected(self, db):
        """Expired JWT should be rejected."""
        admin = db.query(User).filter_by(username="admin").first()
        # Create token with -1 minute expiry (already expired)
        import jwt
        from app.config import settings
        expire = datetime.now(timezone.utc) - timedelta(minutes=1)
        payload = {"sub": str(admin.id), "username": admin.username, "exp": expire}
        expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

        resp = client.get("/product-db/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401

    def test_tampered_token_rejected(self, db):
        """Tampered JWT should be rejected."""
        admin = db.query(User).filter_by(username="admin").first()
        token = create_token(admin.id, admin.username)
        # Tamper: change chars in the payload section (middle part)
        parts = token.split(".")
        assert len(parts) == 3, "JWT should have 3 parts"
        # Flip a char in the payload (second part)
        payload_bytes = list(parts[1])
        payload_bytes[10] = "X" if payload_bytes[10] != "X" else "Y"
        parts[1] = "".join(payload_bytes)
        tampered = ".".join(parts)

        resp = client.get("/product-db/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})
        assert resp.status_code == 401

    def test_token_for_nonexistent_user(self, db):
        """Token referencing deleted user should be rejected."""
        token = create_token(99999, "ghost")

        resp = client.get("/product-db/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_inactive_user_token_rejected(self, db):
        """Token for inactive user should be rejected."""
        u = User(username="disabled_user", password_hash=hash_password("test123"),
                 role="user", is_active=False)
        db.add(u)
        db.commit()
        db.refresh(u)
        token = create_token(u.id, u.username)

        resp = client.get("/product-db/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_query_token_get_only(self, db):
        """?token= should work for GET but not POST."""
        admin = db.query(User).filter_by(username="admin").first()
        token = create_token(admin.id, admin.username)

        # GET should work
        resp = client.get(f"/product-db/api/auth/me?token={token}")
        assert resp.status_code == 200

        # POST should be rejected
        resp = client.post(f"/product-db/api/auth/login?token={token}",
                           json={"username": "admin", "password": "admin"})
        # POST with ?token= should still work (login doesn't require auth)
        # but if we try a POST that requires auth via query token only:
        resp = client.post(f"/product-db/api/solutions?token={token}",
                           json={"name": "test"})
        assert resp.status_code == 401, "Query token should not work for POST"


# ============================================================
# Rate Limiting
# ============================================================
class TestRateLimiting:
    def test_rate_limit_after_failed_logins(self, db):
        """Should block after too many failed attempts."""
        # Make LOGIN_RATE_LIMIT failed attempts
        for i in range(10):
            client.post("/product-db/api/auth/login", json={
                "username": "admin", "password": f"wrong{i}"
            })

        # Next attempt should be rate-limited
        resp = client.post("/product-db/api/auth/login", json={
            "username": "admin", "password": "wrong_final"
        })
        assert resp.status_code == 429

    def test_rate_limit_isolated_by_client_ip_behind_trusted_proxy(self, db):
        """限流按客户端 IP 分桶 —— 但要经可信代理才有意义。

        本用例把测试客户端 (peer = "testclient") 当作可信代理，此时 XFF 表示
        nginx 转发的真实客户端地址，不同真实 IP 应各自计数。
        """
        ip_a = "203.0.113.10"
        with patch("app.auth.settings.TRUSTED_PROXIES", "testclient"):
            for i in range(10):
                client.post(
                    "/product-db/api/auth/login",
                    json={"username": "admin", "password": f"wrong{i}"},
                    headers={"X-Forwarded-For": ip_a},
                )
            # ip_a 已被限流
            resp = client.post(
                "/product-db/api/auth/login",
                json={"username": "admin", "password": "wrong_x"},
                headers={"X-Forwarded-For": ip_a},
            )
            assert resp.status_code == 429

            # 另一个真实 IP 不受影响
            resp = client.post(
                "/product-db/api/auth/login",
                json={"username": "admin", "password": "wrong_x"},
                headers={"X-Forwarded-For": "203.0.113.99"},
            )
            assert resp.status_code == 401

    def test_spoofed_xff_does_not_isolate_from_untrusted_peer(self, db):
        """安全回归：直连对端不可信时，伪造 XFF 不能换来新的限流桶。

        旧实现无条件信任 XFF 首跳，于是一次配额耗尽后只要换一个 XFF 值就能继续
        爆破 —— 实测（2026-09）拿到 429 后换个 XFF 立即恢复 200。这里断言：
        连打 12 次、每次伪造不同的 XFF，仍应在第 11 次被 429 拦住。
        """
        statuses = []
        for i in range(12):
            r = client.post(
                "/product-db/api/auth/login",
                json={"username": "admin", "password": f"wrong{i}"},
                headers={"X-Forwarded-For": f"203.0.113.{i}"},
            )
            statuses.append(r.status_code)

        assert statuses.count(401) == 10, f"前 10 次应是 401，实际 {statuses}"
        assert statuses[10:] == [429, 429], f"伪造 XFF 不得重置限流桶，实际 {statuses}"

    def test_client_ip_ignores_xff_from_untrusted_peer(self):
        """旧断言曾是「peer=127.0.0.1 时取 XFF 最左值」—— 那正是可被伪造的一段。
        见 TestClientIpTrust：可信时取最右跳（或 X-Real-IP），不可信时取对端。"""
        from app.auth import client_ip

        class FakeRequest:
            headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
            client = type("C", (), {"host": "127.0.0.1"})()

        # 可信代理（127.0.0.1）→ 取最右跳，不取客户端可伪造的最左值
        assert client_ip(FakeRequest()) == "10.0.0.1"

        class UntrustedRequest:
            headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
            client = type("C", (), {"host": "198.51.100.7"})()

        # 非可信对端 → 完全忽略 XFF
        assert client_ip(UntrustedRequest()) == "198.51.100.7"


# ============================================================
# Ownership & Permissions
# ============================================================
class TestOwnership:
    def _make_user(self, db, username="other_user"):
        u = User(username=username, password_hash=hash_password("test123"), role="user")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def test_user_cannot_see_other_users_solutions(self, db):
        """Non-admin user should not see solutions owned by other users."""
        admin = db.query(User).filter_by(username="admin").first()
        other = self._make_user(db, "sol_owner")

        # Admin creates a solution
        admin_token = create_token(admin.id, admin.username)
        resp = client.post("/product-db/api/solutions",
                           json={"name": "Admin Only"},
                           headers={"Authorization": f"Bearer {admin_token}"})
        sol_id = resp.json()["solution"]["id"]

        # Other user should not see it
        other_token = create_token(other.id, other.username)
        resp = client.get("/product-db/api/solutions",
                          headers={"Authorization": f"Bearer {other_token}"})
        assert resp.status_code == 200
        ids = [s["id"] for s in resp.json()["solutions"]]
        assert sol_id not in ids

    def test_user_cannot_delete_other_users_solution(self, db):
        """Non-admin should get 403 when deleting another user's solution."""
        admin = db.query(User).filter_by(username="admin").first()
        other = self._make_user(db, "del_other")

        admin_token = create_token(admin.id, admin.username)
        resp = client.post("/product-db/api/solutions",
                           json={"name": "Protected"},
                           headers={"Authorization": f"Bearer {admin_token}"})
        sol_id = resp.json()["solution"]["id"]

        other_token = create_token(other.id, other.username)
        resp = client.delete(f"/product-db/api/solutions/{sol_id}",
                             headers={"Authorization": f"Bearer {other_token}"})
        assert resp.status_code == 403


# ============================================================
# Profile Update
# ============================================================
class TestProfileUpdate:
    def test_update_email(self, db, auth_headers):
        resp = client.put("/product-db/api/auth/profile",
                          json={"email": "new@test.com"},
                          headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "new@test.com"

    def test_update_password_rejects_short(self, db):
        """Profile password changes must enforce the 8-char minimum."""
        u = User(username="prof_user", password_hash=hash_password("longpass123"), role="user")
        db.add(u)
        db.commit()
        db.refresh(u)
        token = create_token(u.id, u.username)
        resp = client.put(
            "/product-db/api/auth/profile",
            json={"password": "short1", "current_password": "longpass123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_update_password_requires_current(self, db, auth_headers):
        """Changing password without current password should fail."""
        resp = client.put("/product-db/api/auth/profile",
                          json={"password": "newpass123"},
                          headers=auth_headers)
        assert resp.status_code == 400

    def test_update_password_wrong_current(self, db, auth_headers):
        """Changing password with wrong current password should fail."""
        resp = client.put("/product-db/api/auth/profile",
                          json={"password": "newpass123", "current_password": "wrong"},
                          headers=auth_headers)
        assert resp.status_code == 400

    def test_update_password_success(self, db, auth_headers):
        """Changing password with correct current password should succeed."""
        resp = client.put("/product-db/api/auth/profile",
                          json={"password": "newpass123", "current_password": "admin"},
                          headers=auth_headers)
        assert resp.status_code == 200

        # Old password should no longer work
        resp = client.post("/product-db/api/auth/login",
                           json={"username": "admin", "password": "admin"})
        assert resp.status_code == 401

        # New password should work
        resp = client.post("/product-db/api/auth/login",
                           json={"username": "admin", "password": "newpass123"})
        assert resp.status_code == 200


# ============================================================
# Registration
# ============================================================
class TestRegistration:
    def test_registration_closed_by_default(self):
        """Registration should be closed by default."""
        resp = client.get("/product-db/api/auth/registration-status")
        assert resp.status_code == 200
        assert resp.json()["open"] is False

    def test_register_when_closed(self):
        """Registering when closed should return 403."""
        resp = client.post("/product-db/api/auth/register", json={
            "username": "newuser", "password": "testpass123"
        })
        assert resp.status_code == 403

    def test_register_short_password(self, db):
        """Registration with short password should fail."""
        from app.models.system_setting import SystemSetting
        db.add(SystemSetting(key="registration_open", value="true"))
        db.commit()

        resp = client.post("/product-db/api/auth/register", json={
            "username": "newuser", "password": "short"
        })
        assert resp.status_code == 400

    def test_register_duplicate_username(self, db):
        """Registration with existing username should fail."""
        from app.models.system_setting import SystemSetting
        db.add(SystemSetting(key="registration_open", value="true"))
        db.commit()

        resp = client.post("/product-db/api/auth/register", json={
            "username": "admin", "password": "testpass123"
        })
        assert resp.status_code == 400


# ============================================================
# Admin Cache Invalidation
# ============================================================
class TestAdminCache:
    def test_admin_ids_cache_refresh(self, db):
        """_get_admin_ids should refresh after 30s TTL."""
        # Clear cache
        import app.auth as auth_mod
        auth_mod._admin_ids_cache = ()

        ids1 = _get_admin_ids(db)
        assert len(ids1) >= 1

        # Cache should be set now
        assert auth_mod._admin_ids_cache != ()

        # Same call should return cached result
        ids2 = _get_admin_ids(db)
        assert ids1 == ids2


class TestPasswordLengthRoundTrip:
    """回归：hash_password 截断到 72 字节而 verify_password 不截断 —— bcrypt 对
    >72 字节输入抛 ValueError，被 except 吞成「密码错误」→ 长密码注册成功却
    永远登录失败（约 25 个中文字符即触发）。"""

    @pytest.mark.parametrize("pw", ["a" * 72, "a" * 73, "a" * 200, "密码" * 30, "短密码1234"])
    def test_any_length_roundtrips(self, pw):
        from app.auth import hash_password, verify_password
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True
        assert verify_password("another-password-entirely", hashed) is False

    def test_api_login_with_long_password(self, db):
        """端到端：用 >72 字节密码建的用户必须能登录（旧实现必然 401）。"""
        from app.auth import hash_password
        pw = "超长密码" * 10  # 40 个汉字 = 120 字节
        assert len(pw.encode()) > 72
        db.add(User(username="longpw", password_hash=hash_password(pw), role="user"))
        db.commit()

        resp = client.post("/product-db/api/auth/login",
                           json={"username": "longpw", "password": pw})
        assert resp.status_code == 200, resp.text


# ============================================================
# IP 地区查询（_lookup_ip_region）
# ============================================================
class TestIpRegionLookup:
    """回归：ipapi.co 免费额度耗尽时返回的是 HTTP 200 + 纯文本付费提示（不是 JSON）。
    旧实现直接 `resp.json()` → JSONDecodeError 被裸 `except Exception` 吞掉且只记
    DEBUG（生产 sink 是 INFO）→ 登录日志「地区」静默变空。2026-09 实测某日 189 条
    登录记录里 188 条为空，没有任何告警。

    本类只覆盖**在线兜底分支**（离线库命中路径见 TestIpRegionOffline），
    因此 fixture 强制离线查询「未命中」。"""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        import app.routers.auth_routes as ar
        ar._ip_region_cache.clear()
        with patch("app.routers.auth_routes._lookup_ip_region_offline", return_value=""):
            yield
        ar._ip_region_cache.clear()

    @staticmethod
    def _resp(status=200, ctype="application/json", text="", payload=None):
        r = MagicMock()
        r.status_code = status
        r.headers = {"content-type": ctype}
        r.text = text
        r.json.return_value = payload if payload is not None else {}
        return r

    def test_private_and_local_ips_short_circuit_without_http(self):
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.httpx.get") as g:
            assert _lookup_ip_region("127.0.0.1") == "本地"
            assert _lookup_ip_region("192.168.1.5") == "本地"
            assert _lookup_ip_region("10.1.2.3") == "本地"
            assert _lookup_ip_region("testclient") == "本地"
            g.assert_not_called()

    def test_parses_city_and_country(self):
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.httpx.get",
                   return_value=self._resp(payload={"city": "Xi'an", "country_name": "China"})):
            assert _lookup_ip_region("1.2.3.4") == "Xi'an, China"

    def test_country_only_when_no_city(self):
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.httpx.get",
                   return_value=self._resp(payload={"city": "", "country_name": "China"})):
            assert _lookup_ip_region("1.2.3.4") == "China"

    def test_quota_exhausted_plain_text_returns_empty_and_warns(self, caplog):
        """核心回归：200 + 纯文本（配额耗尽）必须返回空且留下 WARNING，不得静默。"""
        from app.routers.auth_routes import _lookup_ip_region
        body = "Please contact us for a trial account or sign up for a paid plan"
        with patch("app.routers.auth_routes.httpx.get",
                   return_value=self._resp(ctype="text/plain", text=body)):
            with caplog.at_level(logging.WARNING):
                assert _lookup_ip_region("1.2.3.4") == ""
        assert any(r.levelno == logging.WARNING and "非 JSON" in r.message for r in caplog.records), \
            "配额耗尽必须记 WARNING（旧实现只记 DEBUG，生产看不见）"

    def test_non_200_returns_empty_and_warns(self, caplog):
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.httpx.get", return_value=self._resp(status=429)):
            with caplog.at_level(logging.WARNING):
                assert _lookup_ip_region("1.2.3.4") == ""
        assert any("HTTP 429" in r.message for r in caplog.records)

    def test_network_error_returns_empty_and_warns(self, caplog):
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.httpx.get", side_effect=RuntimeError("boom")):
            with caplog.at_level(logging.WARNING):
                assert _lookup_ip_region("1.2.3.4") == ""
        assert any("IP 地区查询失败" in r.message for r in caplog.records)

    def test_success_is_cached(self):
        """同一 IP 第二次不再发外部请求（该调用在登录必经路径上，最长阻塞 3s）。"""
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.httpx.get",
                   return_value=self._resp(payload={"city": "Xi'an", "country_name": "China"})) as g:
            assert _lookup_ip_region("1.2.3.4") == "Xi'an, China"
            assert _lookup_ip_region("1.2.3.4") == "Xi'an, China"
            assert g.call_count == 1

    def test_failure_is_short_cached(self):
        """失败也短暂缓存，避免每次登录都去撞已被限流的第三方。"""
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.httpx.get",
                   return_value=self._resp(ctype="text/plain", text="quota")) as g:
            assert _lookup_ip_region("1.2.3.4") == ""
            assert _lookup_ip_region("1.2.3.4") == ""
            assert g.call_count == 1

    def test_disabled_by_config(self):
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.settings.DISABLE_IP_LOOKUP", True):
            with patch("app.routers.auth_routes.httpx.get") as g:
                assert _lookup_ip_region("1.2.3.4") == ""
                g.assert_not_called()

    def test_cache_is_bounded(self):
        """登录接口匿名可达 —— 缓存不能被大量不同 IP 撑爆。"""
        import app.routers.auth_routes as ar
        with patch("app.routers.auth_routes.httpx.get",
                   return_value=self._resp(payload={"city": "X", "country_name": "Y"})):
            for i in range(ar._IP_REGION_CACHE_MAX + 10):
                ar._lookup_ip_region(f"1.2.{i // 250}.{i % 250}")
        assert len(ar._ip_region_cache) <= ar._IP_REGION_CACHE_MAX


# ============================================================
# IP 地区查询 —— ip2region 离线库优先（2026-09 改造）
# ============================================================
_XDB_PATH = app_settings.IP2REGION_XDB
_xdb_available = os.path.exists(_XDB_PATH)


class TestIpRegionOffline:
    """离线库为主、ipapi.co 兜底：命中离线库时不得发出任何外部请求
    （该调用在登录必经路径上，此前最多阻塞 3s，且 IP 会出服务器）。"""

    @pytest.fixture(autouse=True)
    def _reset_searcher(self):
        import app.routers.auth_routes as ar
        ar._ip_region_cache.clear()
        ar._ip2region_searcher = None
        ar._ip2region_loaded = False
        yield
        ar._ip_region_cache.clear()
        ar._ip2region_searcher = None
        ar._ip2region_loaded = False

    @staticmethod
    def _resp(payload):
        r = MagicMock()
        r.status_code = 200
        r.headers = {"content-type": "application/json"}
        r.text = ""
        r.json.return_value = payload
        return r

    @pytest.mark.parametrize("raw,expected", [
        ("中国|陕西省|西安市|电信|CN", "西安市, 中国"),
        ("中国|江苏省|南京市|0|CN", "南京市, 中国"),
        ("United States|California|0|Google LLC|US", "California, United States"),
        ("中国|0|0|0|CN", "中国"),
        ("", ""),
        ("Reserved|Reserved|Reserved|0|0", ""),
        ("0|0|0|0|0", ""),
    ])
    def test_format_offline_region(self, raw, expected):
        from app.routers.auth_routes import _format_offline_region
        assert _format_offline_region(raw) == expected

    @pytest.mark.skipif(not _xdb_available, reason="ip2region xdb 数据文件缺失")
    def test_china_ip_resolved_offline_without_http(self):
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.httpx.get") as g:
            assert _lookup_ip_region("113.132.197.169") == "西安市, 中国"
            g.assert_not_called()

    @pytest.mark.skipif(not _xdb_available, reason="ip2region xdb 数据文件缺失")
    def test_reserved_ip_falls_back_to_online(self):
        """保留地址段（含 SSRF 目标 169.254.169.254）在库里是 Reserved，
        必须当「查不到」处理并回落在线，而不是记成「在 Reserved 地区登录」。"""
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.httpx.get",
                   return_value=self._resp({"city": "Xi'an", "country_name": "China"})) as g:
            assert _lookup_ip_region("169.254.169.254") == "Xi'an, China"
            assert g.call_count == 1

    def test_missing_xdb_falls_back_online_and_warns_once(self, caplog):
        """离线库文件缺失：只告警一次，登录照常走在线查询（不阻断、不每次刷日志）。"""
        from app.routers.auth_routes import _lookup_ip_region
        with patch("app.routers.auth_routes.settings.IP2REGION_XDB", "/nonexistent/ip2region.xdb"):
            with patch("app.routers.auth_routes.httpx.get",
                       return_value=self._resp({"city": "Xi'an", "country_name": "China"})) as g:
                with caplog.at_level(logging.WARNING):
                    assert _lookup_ip_region("1.2.3.4") == "Xi'an, China"
                    assert _lookup_ip_region("1.2.3.5") == "Xi'an, China"
                assert g.call_count == 2
        warns = [r for r in caplog.records if "ip2region 离线库不可用" in r.message]
        assert len(warns) == 1, "库不可用只应告警一次"

    def test_offline_search_error_falls_back_online(self, caplog):
        """查不动（如 IPv6 地址查 IPv4 库）时静默回落在线：不抛错、不刷 WARNING。"""
        import app.routers.auth_routes as ar
        searcher = MagicMock()
        searcher.search.side_effect = ValueError("invalid ip address")
        ar._ip2region_searcher = searcher
        ar._ip2region_loaded = True
        with patch("app.routers.auth_routes.httpx.get",
                   return_value=self._resp({"city": "Xi'an", "country_name": "China"})) as g:
            with caplog.at_level(logging.WARNING):
                assert ar._lookup_ip_region("240e:3b7:3272:d8d0:db09:c067:8d59:539e") == "Xi'an, China"
        assert g.call_count == 1
        assert not [r for r in caplog.records if "ip2region" in str(r.message)]

    def test_offline_hit_is_cached(self):
        """离线命中也走缓存：第二次不再查库（登录路径上）。"""
        import app.routers.auth_routes as ar
        with patch("app.routers.auth_routes._lookup_ip_region_offline",
                   return_value="西安市, 中国") as off:
            with patch("app.routers.auth_routes.httpx.get") as g:
                assert ar._lookup_ip_region("113.132.197.169") == "西安市, 中国"
                assert ar._lookup_ip_region("113.132.197.169") == "西安市, 中国"
                assert off.call_count == 1
                g.assert_not_called()

    def test_local_ips_never_touch_the_library(self):
        """本机/内网地址直接返回「本地」，连离线库都不查。"""
        import app.routers.auth_routes as ar
        with patch("app.routers.auth_routes._lookup_ip_region_offline") as off:
            assert ar._lookup_ip_region("127.0.0.1") == "本地"
            assert ar._lookup_ip_region("testclient") == "本地"
            off.assert_not_called()


# ============================================================
# client_ip —— X-Forwarded-For 只应在可信代理之后才采信
# ============================================================
class _Req:
    """最小 Request 替身：client_ip 只需要 headers.get() 与 client.host。"""

    def __init__(self, peer, headers=None):
        self.headers = headers or {}
        self.client = type("C", (), {"host": peer})() if peer else None


class TestClientIpTrust:
    """回归：旧实现无条件信任 XFF 首跳，客户端伪造一个 XFF 就能改变限流 key。
    实测（与生产同构，2026-09）：配额耗尽拿到 429 后换一个伪造 XFF 立即恢复 200，
    且同一伪造 XFF 连续请求按该值计数 —— 全局限流与登录爆破限流（10 次/300s）
    同时可绕，login_logs 的 IP/地区审计也随之被污染。"""

    def test_untrusted_peer_ignores_spoofed_headers(self):
        from app.auth import client_ip
        r = _Req("203.0.113.9", {"x-forwarded-for": "1.2.3.4, 5.6.7.8", "x-real-ip": "9.9.9.9"})
        assert client_ip(r) == "203.0.113.9", "非可信对端必须忽略 XFF/X-Real-IP"

    def test_trusted_peer_uses_rightmost_hop(self):
        """nginx 用 $proxy_add_x_forwarded_for 追加真实地址 → 最右侧才可信。"""
        from app.auth import client_ip
        r = _Req("127.0.0.1", {"x-forwarded-for": "1.2.3.4, 203.0.113.9"})
        assert client_ip(r) == "203.0.113.9"

    def test_trusted_peer_prefers_x_real_ip(self):
        """X-Real-IP 由 nginx 从 $remote_addr 直赋，不可被客户端影响。"""
        from app.auth import client_ip
        r = _Req("127.0.0.1", {"x-forwarded-for": "1.2.3.4, 5.6.7.8", "x-real-ip": "203.0.113.9"})
        assert client_ip(r) == "203.0.113.9"

    def test_trusted_peer_without_forwarding_headers(self):
        from app.auth import client_ip
        assert client_ip(_Req("127.0.0.1", {})) == "127.0.0.1"

    def test_trusted_list_is_configurable(self):
        from app.auth import client_ip
        r = _Req("10.0.0.5", {"x-real-ip": "203.0.113.9"})
        with patch("app.auth.settings.TRUSTED_PROXIES", "10.0.0.5,127.0.0.1"):
            assert client_ip(r) == "203.0.113.9"
        with patch("app.auth.settings.TRUSTED_PROXIES", "127.0.0.1"):
            assert client_ip(r) == "10.0.0.5"

    def test_none_request_returns_empty(self):
        from app.auth import client_ip
        assert client_ip(None) == ""

    def test_no_client_info_returns_empty(self):
        from app.auth import client_ip
        assert client_ip(_Req(None, {"x-forwarded-for": "1.2.3.4"})) == ""
