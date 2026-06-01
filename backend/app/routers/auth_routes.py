"""Authentication routes — login, logout, profile, user management."""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import hash_password, verify_password, create_token, get_current_user
from app.models.user import User
from app.models.login_log import LoginLog
from app.schemas.auth import (
    LoginRequest, TokenResponse, UserResponse,
    CreateUserRequest, UpdateUserRequest, UpdateProfileRequest,
)
import httpx

router = APIRouter()


def _lookup_ip_region(ip: str) -> str:
    """Look up IP region via ipapi.co."""
    if not ip or ip.startswith("127.") or ip.startswith("192.168.") or ip == "::1":
        return "本地"
    try:
        resp = httpx.get(f"https://ipapi.co/{ip}/json/", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            city = data.get("city", "")
            country = data.get("country_name", "")
            return f"{city}, {country}" if city else country
    except Exception:
        pass
    return ""


@router.post("/auth/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=data.username).first()
    ip = request.client.host if request.client else ""

    if not user or not verify_password(data.password, user.password_hash):
        db.add(LoginLog(user_id=None, ip_address=ip, success="0",
                        user_agent=request.headers.get("User-Agent", "")))
        db.commit()
        raise HTTPException(401, "用户名或密码错误")

    if not user.is_active:
        raise HTTPException(403, "账户已被禁用")

    # Auto-upgrade legacy SHA256 hash to bcrypt
    if not user.password_hash.startswith("$2"):
        user.password_hash = hash_password(data.password)

    region = _lookup_ip_region(ip)
    db.add(LoginLog(user_id=user.id, ip_address=ip, region=region, success="1",
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
def register(data: dict, request: Request, db: Session = Depends(get_db)):
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="registration_open").first()
    if not s or s.value != "true":
        raise HTTPException(403, "注册功能未开放")
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if len(username) < 2 or len(password) < 6:
        raise HTTPException(400, "用户名至少2位，密码至少6位")
    if db.query(User).filter_by(username=username).first():
        raise HTTPException(400, "用户名已存在")
    u = User(username=username, password_hash=hash_password(password),
             role="user", email=(data.get("email") or ""))
    db.add(u)
    db.commit()
    db.refresh(u)
    ip = request.client.host if request.client else ""
    db.add(LoginLog(user_id=u.id, ip_address=ip, success="1",
                    user_agent=request.headers.get("User-Agent", "")))
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


# --- Admin user management ---

@router.get("/admin/users")
def list_users(search: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    q = db.query(User)
    if search:
        q = q.filter(User.username.ilike(f"%{search}%"))
    users = q.order_by(User.id).all()
    return {"users": [u.to_dict() for u in users]}


@router.post("/admin/users")
def create_user(data: CreateUserRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    if db.query(User).filter_by(username=data.username).first():
        raise HTTPException(400, "用户名已存在")
    u = User(username=data.username, password_hash=hash_password(data.password),
             role=data.role, email=data.email)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"user": u.to_dict()}


@router.put("/admin/users/{uid}")
def update_user(uid: int, data: UpdateUserRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    for f in ["email", "role", "is_active"]:
        val = getattr(data, f, None)
        if val is not None:
            setattr(u, f, val)
    if data.password:
        u.password_hash = hash_password(data.password)
    db.commit()
    return {"user": u.to_dict()}


@router.put("/admin/users/{uid}/password")
def reset_user_password(uid: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    pwd = data.get("password", "")
    if len(pwd) < 8:
        raise HTTPException(400, "密码至少8位")
    u.password_hash = hash_password(pwd)
    db.commit()
    return {"ok": True}


@router.delete("/admin/users/{uid}")
def delete_user(uid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == user.id:
        raise HTTPException(400, "不能删除自己")
    db.delete(u)
    db.commit()
    return {"ok": True}


@router.get("/admin/login-logs")
def list_login_logs(user_id: int = None, limit: int = 50, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    q = db.query(LoginLog).order_by(LoginLog.created_at.desc())
    if user_id:
        q = q.filter_by(user_id=user_id)
    logs = q.limit(min(limit, 200)).all()
    return {"logs": [l.to_dict() for l in logs]}


# --- Field visibility ---

@router.get("/admin/fields")
def get_fields(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.field_setting import FieldSetting
    settings = db.query(FieldSetting).all()
    if not settings:
        for name in ["cost_price", "manufacturer_name", "supplier_name", "product_url"]:
            db.add(FieldSetting(field_name=name, user_visible=True))
        db.commit()
        settings = db.query(FieldSetting).all()
    return {"fields": {s.field_name: s.user_visible for s in settings}}


@router.put("/admin/fields")
def update_fields(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.field_setting import FieldSetting
    from app.services.field_visibility import _cache
    for field_name, visible in data.items():
        s = db.query(FieldSetting).filter_by(field_name=field_name).first()
        if s:
            s.user_visible = bool(visible)
        else:
            db.add(FieldSetting(field_name=field_name, user_visible=bool(visible)))
    db.commit()
    _cache["ts"] = 0  # invalidate cache
    return {"ok": True}


# --- AI Prompt Management ---

DEFAULT_AI_PROMPT = """你是产品数据库AI助手。帮助用户查询产品、推荐方案、录入产品信息。
数据库包含 IoT 产品和设施管理产品。
用中文简洁回答，查产品时调用 search_products 工具。"""


@router.get("/admin/prompt")
def get_ai_prompt(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="ai_system_prompt").first()
    return {"prompt": s.value if s else DEFAULT_AI_PROMPT, "is_default": not s}


@router.put("/admin/prompt")
def update_ai_prompt(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="ai_system_prompt").first()
    if not s:
        s = SystemSetting(key="ai_system_prompt")
        db.add(s)
    s.value = data.get("prompt", "")
    # Clear AI sessions to force new prompt on next chat
    from app.models.ai_models import AIConversation
    db.query(AIConversation).delete()
    db.commit()
    return {"ok": True}


@router.delete("/admin/prompt")
def reset_ai_prompt(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="ai_system_prompt").first()
    if s:
        db.delete(s)
        db.commit()
    return {"prompt": DEFAULT_AI_PROMPT}


# --- AI Usage Stats ---

@router.get("/admin/ai-usage")
def get_ai_usage(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.ai_usage_log import AIUsageLog
    from sqlalchemy import func

    total = db.query(func.count(AIUsageLog.id)).scalar() or 0
    success_count = db.query(func.count(AIUsageLog.id)).filter(AIUsageLog.success == "1").scalar() or 0
    avg_time = db.query(func.avg(AIUsageLog.duration_ms)).scalar() or 0

    recent = db.query(AIUsageLog).order_by(AIUsageLog.created_at.desc()).limit(50).all()
    by_op = db.query(AIUsageLog.operation, func.count(AIUsageLog.id)).group_by(AIUsageLog.operation).all()

    return {
        "summary": {"total": total, "success": success_count, "avg_duration_ms": round(avg_time, 1)},
        "by_operation": [{"operation": op, "count": c} for op, c in by_op],
        "recent": [r.to_dict() for r in recent],
    }


# --- Download Security ---

@router.get("/admin/download-logs")
def get_download_logs(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.download_log import DownloadLog
    logs = db.query(DownloadLog).order_by(DownloadLog.created_at.desc()).limit(50).all()
    return {"logs": [l.to_dict() for l in logs]}
