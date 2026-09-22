"""Round 15 回归：`/api/health/detailed`（R78）。

运维可见性端点：聚合本应用（DB 连通性）与 Hermes（版本/平台/活跃 agent/readiness）。

两条关键契约：
- **仅 admin**：Hermes 侧带出版本号与活跃 agent 数，属内部拓扑，不能像 `/api/health` 那样公开。
- **任一侧故障都返回 200**：这个端点的用途是判断「哪一侧坏了」，把上游故障翻成 5xx
  会让「Hermes 挂了」和「整个服务挂了」长得一样。
"""
import os
import tempfile

_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["DEV_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-32charmin"

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.user import User
from app.auth import hash_password, create_token
from tests.conftest import create_test_schema, drop_test_schema

client = TestClient(app)
URL = "/product-db/api/health/detailed"

HERMES_BODY = {
    "status": "ok",
    "version": "0.21.4",
    "platforms": ["api_server", "feishu"],
    "active_agents": 1,
    "readiness": {"ready": True},
}


class _FakeResp:
    def __init__(self, status_code=200, body=None, bad_json=False):
        self.status_code = status_code
        self._body = body
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._body


class _FakeClient:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._exc:
            raise self._exc
        return self._resp


def _setup():
    drop_test_schema()
    create_test_schema()
    db = SessionLocal()
    try:
        db.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
        db.add(User(username="viewer", password_hash=hash_password("viewer"), role="user"))
        db.commit()
    finally:
        db.close()


def _headers(username: str):
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username=username).first()
        return {"Authorization": f"Bearer {create_token(u.id, u.username)}"}
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _schema():
    _setup()
    yield
    drop_test_schema()


def _patch_hermes(monkeypatch, resp=None, exc=None):
    from app.routers import agent as agent_module
    fake = _FakeClient(resp=resp, exc=exc)
    monkeypatch.setattr(agent_module, "_get_http_client", lambda: fake)
    return fake


class TestHealthDetailed:
    def test_public_health_is_unchanged(self):
        """公开的 /api/health 不受影响：不带凭据也能拿到 200。"""
        r = client.get("/product-db/api/health")
        assert r.status_code == 200 and r.json() == {"status": "ok"}

    def test_detailed_rejects_bad_token(self):
        """带无效凭据必须 401。

        （「完全不带凭据」在测试环境走不通：`DEV_MODE=true` 时无凭据会直接当成 admin，
        另有 tests 专门覆盖 DEV_MODE 的这一行为。）
        """
        r = client.get(URL, headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 401

    def test_detailed_is_admin_only(self):
        """普通用户 403 —— 响应里有版本号与活跃 agent 数，属内部拓扑。"""
        r = client.get(URL, headers=_headers("viewer"))
        assert r.status_code == 403

    def test_returns_both_sides(self, monkeypatch):
        _patch_hermes(monkeypatch, resp=_FakeResp(200, HERMES_BODY))
        r = client.get(URL, headers=_headers("admin"))
        assert r.status_code == 200
        body = r.json()
        assert body["app"] == {"status": "ok", "db": "ok"}
        assert body["hermes"]["version"] == "0.21.4"
        assert body["hermes"]["active_agents"] == 1

    def test_hermes_call_uses_health_detailed_path_and_short_timeout(self, monkeypatch):
        fake = _patch_hermes(monkeypatch, resp=_FakeResp(200, HERMES_BODY))
        client.get(URL, headers=_headers("admin"))
        url, kwargs = fake.calls[0]
        assert url.endswith("/health/detailed")
        # 探活不能沿用 300s 的对话超时
        assert kwargs["timeout"].read == 5.0

    def test_hermes_unreachable_still_200(self, monkeypatch):
        _patch_hermes(monkeypatch, exc=httpx.ConnectError("refused"))
        r = client.get(URL, headers=_headers("admin"))
        assert r.status_code == 200
        body = r.json()
        assert body["app"]["status"] == "ok", "Hermes 挂了不该让本应用看起来也挂了"
        assert body["hermes"]["status"] == "unreachable"

    def test_hermes_401_still_200(self, monkeypatch):
        """没配 gateway key 时 Hermes 回 401 —— 要能看出是「未授权」而不是「服务挂了」。"""
        _patch_hermes(monkeypatch, resp=_FakeResp(401, {"error": {"code": "gateway_auth_failed"}}))
        body = client.get(URL, headers=_headers("admin")).json()
        assert body["hermes"]["status"] == "error"
        assert body["hermes"]["http_status"] == 401

    def test_hermes_non_json_body(self, monkeypatch):
        _patch_hermes(monkeypatch, resp=_FakeResp(200, bad_json=True))
        body = client.get(URL, headers=_headers("admin")).json()
        assert body["hermes"]["status"] == "error"
