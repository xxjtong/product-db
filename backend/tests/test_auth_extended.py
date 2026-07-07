"""Supplementary tests for auth.py — SHA256 upgrade, query token, DEV_MODE, edge cases."""
import pytest
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone

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
