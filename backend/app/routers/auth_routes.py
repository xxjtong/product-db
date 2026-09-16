"""Authentication routes — login, logout, profile, user management."""
import json
import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import hash_password, verify_password, create_token, get_current_user, client_ip
from app.models.user import User
from app.models.login_log import LoginLog
from app.schemas.auth import (
    LoginRequest, TokenResponse, UserResponse,
    CreateUserRequest, UpdateUserRequest, UpdateProfileRequest,
    RegistrationRequest, ResetPasswordRequest, FieldVisibilityUpdate, AIPromptUpdate,
)
from app.config import settings
import httpx

router = APIRouter()


# IP → (过期时间戳, 地区)。同一 IP 的地区一天内不会变，缓存既省外部调用，
# 也避免登录路径每次都阻塞在第三方请求上（该调用最长 3s，且在登录必经路径上）。
_ip_region_cache: dict = {}
_IP_REGION_TTL = 86400      # 成功结果缓存 1 天
_IP_REGION_FAIL_TTL = 300   # 失败也短暂缓存，防止每次都去撞配额
_IP_REGION_CACHE_MAX = 2048  # 登录接口匿名可达，防止缓存被大量不同 IP 撑爆


def _lookup_ip_region(ip: str) -> str:
    """Look up IP region via ipapi.co (best-effort, cached).

    失败必须留下可见痕迹：ipapi.co 免费额度耗尽时返回的是 HTTP 200 + 纯文本付费
    提示（不是 JSON）。早期实现直接 `resp.json()`，抛出的 JSONDecodeError 被裸
    `except Exception` 吞掉且只记 DEBUG（生产日志 sink 是 INFO）—— 结果是「地区」
    静默变空：2026-09 实测某日 189 条登录记录中 188 条为空，无人察觉。
    """
    if settings.DISABLE_IP_LOOKUP:
        return ""
    if not ip or ip.startswith("127.") or ip.startswith("192.168.") or ip.startswith("10.") or ip in ("::1", "testclient"):
        return "本地"

    now = time.time()
    cached = _ip_region_cache.get(ip)
    if cached and cached[0] > now:
        return cached[1]

    log = logging.getLogger("uvicorn")
    region = ""
    try:
        resp = httpx.get(f"https://ipapi.co/{ip}/json/", timeout=3)
        ctype = (resp.headers.get("content-type") or "").lower()
        if resp.status_code != 200:
            log.warning("IP 地区查询 %s 返回 HTTP %s，本次地区留空", ip, resp.status_code)
        elif "json" not in ctype:
            # 免费额度耗尽时 ipapi.co 走这一支：200 + 纯文本
            log.warning("IP 地区查询 %s 返回非 JSON 响应（ipapi.co 配额耗尽？）：%.80s", ip, resp.text)
        else:
            data = resp.json()
            city = data.get("city") or ""
            country = data.get("country_name") or ""
            region = f"{city}, {country}" if city else country
            if not region:
                log.warning("IP 地区查询 %s 未返回城市/国家：%.120s", ip, resp.text)
    except Exception as e:
        log.warning("IP 地区查询失败 %s：%s", ip, e)

    if len(_ip_region_cache) >= _IP_REGION_CACHE_MAX:
        _ip_region_cache.clear()
    _ip_region_cache[ip] = (now + (_IP_REGION_TTL if region else _IP_REGION_FAIL_TTL), region)
    return region


def _check_rate_limit(ip: str, db: Session) -> bool:
    """Return True if rate limit exceeded."""
    from datetime import timedelta
    from app.models.login_log import LoginLog
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.LOGIN_RATE_WINDOW)
    count = db.query(LoginLog).filter(
        LoginLog.ip_address == ip,
        LoginLog.success == False,
        LoginLog.created_at >= cutoff,
    ).count()
    return count >= settings.LOGIN_RATE_LIMIT


@router.post("/auth/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if _check_rate_limit(ip, db):
        raise HTTPException(429, "登录尝试过于频繁，请稍后再试")
    user = db.query(User).filter_by(username=data.username).first()

    if not user or not verify_password(data.password, user.password_hash):
        db.add(LoginLog(user_id=None, ip_address=ip, success=False,
                        user_agent=request.headers.get("User-Agent", ""),
                        region=_lookup_ip_region(ip)))
        db.commit()
        raise HTTPException(401, "用户名或密码错误")

    if not user.is_active:
        raise HTTPException(403, "账户已被禁用")

    # Auto-upgrade legacy SHA256 hash to bcrypt
    if not user.password_hash.startswith("$2"):
        user.password_hash = hash_password(data.password)

    region = _lookup_ip_region(ip)
    db.add(LoginLog(user_id=user.id, ip_address=ip, region=region, success=True,
                    user_agent=request.headers.get("User-Agent", "")))
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    token = create_token(user.id, user.username)
    return {"token": token, "user": user.to_dict()}


@router.get("/auth/me", response_model=UserResponse)
def get_me(user=Depends(get_current_user)):
    return {"user": user.to_dict()}


@router.put("/auth/profile", response_model=UserResponse)
def update_profile(data: UpdateProfileRequest, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    if data.email is not None:
        user.email = data.email
    if data.password:
        # Require current password for security
        if not data.current_password or not verify_password(data.current_password, user.password_hash):
            raise HTTPException(400, "当前密码错误")
        if len(data.password) < 8:
            raise HTTPException(400, "密码至少8位")
        user.password_hash = hash_password(data.password)
    db.commit()
    return {"user": user.to_dict()}


# --- Registration ---

@router.get("/auth/registration-status")
def registration_status(db: Session = Depends(get_db)):
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="registration_open").first()
    return {"open": s.value == "true" if s else False}


@router.post("/auth/register")
def register(data: RegistrationRequest, request: Request, db: Session = Depends(get_db)):
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="registration_open").first()
    if not s or s.value != "true":
        raise HTTPException(403, "注册功能未开放")
    username = data.username.strip()
    password = data.password
    if len(username) < 2 or len(password) < 8:
        raise HTTPException(400, "用户名至少2位，密码至少8位")
    if db.query(User).filter_by(username=username).first():
        raise HTTPException(400, "用户名已存在")
    u = User(username=username, password_hash=hash_password(password),
             role="user", email=data.email)
    db.add(u)
    db.commit()
    db.refresh(u)
    ip = client_ip(request)
    db.add(LoginLog(user_id=u.id, ip_address=ip, success=True,
                    user_agent=request.headers.get("User-Agent", ""),
                    region=_lookup_ip_region(ip)))
    db.commit()
    token = create_token(u.id, u.username)
    return {"token": token, "user": u.to_dict()}


# --- Session / JWT renewal ---

@router.get("/auth/session")
def get_session(user=Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.field_visibility import get_field_visibility
    from app.models.system_setting import SystemSetting

    s = db.query(SystemSetting).filter_by(key="registration_open").first()
    return {
        "user": user.to_dict(),
        "field_visibility": {} if user.role == 'admin' else get_field_visibility(db),
        "registration_open": s.value == "true" if s else False,
    }
