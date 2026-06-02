"""Admin routes — user management, field visibility, AI prompt, usage stats, logs."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import hash_password, get_current_user
from app.models.user import User
from app.models.login_log import LoginLog
from app.schemas.auth import (
    CreateUserRequest, UpdateUserRequest, ResetPasswordRequest,
    FieldVisibilityUpdate, AIPromptUpdate,
)
from app.utils.escape import escape_like
from app.utils.helpers import apply_partial_update

router = APIRouter()

DEFAULT_AI_PROMPT = """你是产品数据库AI助手。帮助用户查询产品、推荐方案、录入产品信息。
数据库包含 IoT 产品和设施管理产品。
用中文简洁回答，查产品时调用 search_products 工具。"""


# --- Admin user management ---

@router.get("/admin/users")
def list_users(search: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.ai_usage_log import AIUsageLog
    from sqlalchemy import func
    q = db.query(User)
    if search:
        q = q.filter(User.username.ilike(f"%{escape_like(search)}%"))
    users = q.order_by(User.id).all()
    result = []
    for u in users:
        d = u.to_dict()
        d["ai_count"] = db.query(AIUsageLog).filter_by(user_id=u.id).count()
        d["ai_tokens"] = db.query(func.sum(AIUsageLog.tokens_in + AIUsageLog.tokens_out)).filter_by(user_id=u.id).scalar() or 0
        result.append(d)
    return {"users": result}


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
    apply_partial_update(u, data, ["email", "role", "is_active"])
    if data.password:
        u.password_hash = hash_password(data.password)
    db.commit()
    return {"user": u.to_dict()}


@router.put("/admin/users/{uid}/password")
def reset_user_password(uid: int, data: ResetPasswordRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    if len(data.password) < 8:
        raise HTTPException(400, "密码至少8位")
    u.password_hash = hash_password(data.password)
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
def update_fields(data: FieldVisibilityUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.field_setting import FieldSetting
    from app.services.field_visibility import _cache
    for field_name, visible in (data.model_extra or {}).items():
        s = db.query(FieldSetting).filter_by(field_name=field_name).first()
        if s:
            s.user_visible = bool(visible)
        else:
            db.add(FieldSetting(field_name=field_name, user_visible=bool(visible)))
    db.commit()
    _cache["ts"] = 0
    return {"ok": True}


# --- AI Prompts & Models ---

_PROMPT_DEFAULTS = {
    "ai_system_prompt": "你是产品数据库AI助手。帮助用户查询产品、推荐方案、录入产品信息。\n数据库包含 IoT 产品和设施管理产品。\n用中文简洁回答，查产品时调用 search_products 工具。",
    "ai_keyword_prompt": "从用户查询提取搜索参数，返回JSON: {\"keyword\":\"关键词\",\"category\":\"品类\",\"comm_method\":\"通讯方式\"}。品类从:网关/传感器/节点终端/安防/工具/执行器/蜂窝设备 中选择。只返回JSON。",
    "ai_extract_prompt": "你是一个物联网产品信息提取助手。根据网页内容提取产品结构化信息，输出必须是有效 JSON。",
}
_MODEL_DEFAULTS = {"ai_chat_model": "deepseek-chat", "ai_keyword_model": "deepseek-chat", "ai_extract_model": "deepseek-chat"}

@router.get("/admin/ai-settings")
def get_ai_settings(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.system_setting import SystemSetting
    result = {"prompts": {}, "models": {}}
    for s in db.query(SystemSetting).all():
        if s.key in _PROMPT_DEFAULTS: result["prompts"][s.key] = s.value
        elif s.key in _MODEL_DEFAULTS: result["models"][s.key] = s.value
    return result

@router.put("/admin/ai-settings")
def update_ai_settings(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.system_setting import SystemSetting
    for kv in [data.get("prompts", {}), data.get("models", {})]:
        for key, value in kv.items():
            s = db.query(SystemSetting).filter_by(key=key).first()
            if not s: s = SystemSetting(key=key); db.add(s)
            s.value = value
    if data.get("prompts"):
        from app.models.ai_models import AIConversation; db.query(AIConversation).delete()
    db.commit()
    return {"ok": True}


# --- AI Usage Stats ---

@router.get("/admin/ai-usage")
def get_ai_usage(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.ai_usage_log import AIUsageLog
    from sqlalchemy import func
    total = db.query(func.count(AIUsageLog.id)).scalar() or 0
    success_count = db.query(func.count(AIUsageLog.id)).filter(AIUsageLog.success == True).scalar() or 0
    avg_time = db.query(func.avg(AIUsageLog.duration_ms)).scalar() or 0
    total_tokens_in = db.query(func.sum(AIUsageLog.tokens_in)).scalar() or 0
    total_tokens_out = db.query(func.sum(AIUsageLog.tokens_out)).scalar() or 0
    recent = db.query(AIUsageLog).order_by(AIUsageLog.created_at.desc()).limit(50).all()
    by_op = db.query(AIUsageLog.operation, func.count(AIUsageLog.id)).group_by(AIUsageLog.operation).all()
    return {
        "summary": {
            "total": total, "success": success_count, "avg_duration_ms": round(avg_time, 1),
            "total_tokens_in": total_tokens_in, "total_tokens_out": total_tokens_out,
        },
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
