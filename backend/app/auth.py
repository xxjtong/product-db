import hashlib
import bcrypt as _bcrypt
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.database import get_db
from app.models.user import User
from sqlalchemy.orm import Session

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    # bcrypt has a 72-byte limit on password length
    return _bcrypt.hashpw(
        password.encode()[:72],
        _bcrypt.gensalt(),
    ).decode()


def verify_password(plain: str, hashed: str) -> bool:
    # Try bcrypt first
    if hashed.startswith("$2"):
        try:
            return _bcrypt.checkpw(plain.encode(), hashed.encode())
        except (ValueError, TypeError):
            return False
    # Legacy SHA256 hash format: salt$hexdigest
    # Auto-upgraded to bcrypt on successful login (see auth_routes.py)
    try:
        from loguru import logger
        logger.warning("SHA256 legacy password hash used — will auto-upgrade to bcrypt on login")
        salt, h = hashed.split("$", 1)
        return h == hashlib.sha256((salt + plain).encode()).hexdigest()
    except (ValueError, AttributeError):
        return False


def create_token(user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
    token: str = Query(None),
    request: Request = None,
) -> User:
    if not credentials and token:
        # Token in query string: only allowed for GET (read-only) requests.
        # Passing JWT in URL exposes it to logs, referrers, and proxies.
        if request and request.method != "GET":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token auth only allowed for GET requests",
            )
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = int(payload.get("sub"))
            user = db.get(User, user_id)
            if user and user.is_active:
                return user
        except (jwt.PyJWTError, ValueError, TypeError):
            pass
    if not credentials:
        if not settings.DEV_MODE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        from loguru import logger
        user = db.query(User).filter_by(username="admin").first()
        if not user:
            logger.warning("DEV_MODE: auto-creating admin/admin user — NEVER use in production")
            user = User(username="admin", password_hash=hash_password("admin"), role="admin")
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    try:
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


_admin_ids_cache: tuple = ()

def _get_admin_ids(session) -> list:
    """Get admin user IDs with 30s TTL cache."""
    global _admin_ids_cache
    import time as _time
    ts, ids = _admin_ids_cache or (0, [])
    now = _time.time()
    if now - ts > 30:
        from app.models.user import User as _AuthUser
        ids = [u.id for u in session.query(_AuthUser.id).filter(_AuthUser.role == "admin").all()]
        _admin_ids_cache = (now, ids)
    return ids or [1]


def filter_by_ownership(query, model, user, strict: bool = False):
    """Filter query by ownership.

    strict=False (default): admin sees all, others see own + admin + legacy (NULL).
    strict=True: admin sees all, others see ONLY their own (created_by == user.id).
    """
    if user.role == "admin":
        return query
    from sqlalchemy import or_
    if strict:
        return query.filter(model.created_by == user.id)
    admin_ids = _get_admin_ids(query.session)
    return query.filter(or_(model.created_by == None, model.created_by == user.id, model.created_by.in_(admin_ids)))


def check_ownership(resource, user, strict: bool = False):
    """Raise 403 if user doesn't own this resource.

    strict=False (default): admin always passes, NULL=legacy allowed, admin-owned allowed.
    strict=True: admin always passes, others can only access their own (NULL denied).
    """
    if user.role == "admin":
        return
    created_by = getattr(resource, 'created_by', None)
    if created_by is None:
        if strict:
            raise HTTPException(403, "Access denied: legacy resource requires admin")
        return
    if created_by != user.id:
        if not strict:
            from sqlalchemy.orm import object_session
            sess = object_session(resource)
            if sess and created_by in _get_admin_ids(sess):
                return
        raise HTTPException(403, "Access denied: not your resource")
