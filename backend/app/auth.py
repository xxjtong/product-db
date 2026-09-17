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


def client_ip(request) -> str:
    """Best-effort client IP.

    X-Forwarded-For 只在**直连对端是可信代理**（默认本机 nginx）时才采信。否则
    客户端只要自己发一个 XFF 就能改变限流 key —— 实测可绕过全局 200/day 限流与
    登录爆破限流（10 次/300 秒），并把伪造的 IP/地区写进 login_logs 审计。

    采信时取**最右侧**一跳：nginx 用 `$proxy_add_x_forwarded_for` 追加真实地址，
    客户端自带的内容留在左侧（不可信）。`X-Real-IP` 由 nginx 从 `$remote_addr`
    直接赋值，优先级更高。
    """
    if not request:
        return ""
    peer = request.client.host if request.client else ""

    trusted = {p.strip() for p in settings.TRUSTED_PROXIES.split(",") if p.strip()}
    if peer and peer in trusted:
        real = (request.headers.get("x-real-ip") or "").strip()
        if real:
            return real
        hops = [h.strip() for h in (request.headers.get("x-forwarded-for") or "").split(",") if h.strip()]
        if hops:
            return hops[-1]
    return peer


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
            # 必须和 hash_password 一样截断到 72 字节：bcrypt 对 >72 字节的输入会抛
            # ValueError，旧实现只在哈希时截断、校验时不截断 → 超过 72 字节的密码
            # 注册成功但永远登录失败，且异常被下面的 except 吞成「密码错误」
            return _bcrypt.checkpw(plain.encode()[:72], hashed.encode())
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


def require_admin(user=Depends(get_current_user)):
    """主数据写操作只允许管理员（品类/厂商/供应商/字典/BOM 模板）。

    背景：这些接口原用 check_ownership(..., strict=False)，而它对 created_by IS NULL
    的历史行**直接放行**；生产上主数据几乎全是 NULL（manufacturers 48/48、
    suppliers 55/55、dict_sensor_metrics 36/36…，见 R31），等于任何登录用户都能
    改删全站共用数据。业务数据（产品/方案/报价单）不受影响，仍按归属校验。
    """
    if getattr(user, "role", "") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可修改主数据")
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
