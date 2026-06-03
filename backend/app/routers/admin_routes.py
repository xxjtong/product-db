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
    user_ids = [u.id for u in users]
    # Batch-aggregate AI usage stats (avoid N+1)
    from sqlalchemy import func as sa_func
    count_rows = db.query(AIUsageLog.user_id, sa_func.count().label("cnt")).filter(
        AIUsageLog.user_id.in_(user_ids)
    ).group_by(AIUsageLog.user_id).all()
    token_rows = db.query(AIUsageLog.user_id, sa_func.sum(AIUsageLog.tokens_in + AIUsageLog.tokens_out).label("tok")).filter(
        AIUsageLog.user_id.in_(user_ids)
    ).group_by(AIUsageLog.user_id).all()
    counts = {row.user_id: row.cnt for row in count_rows}
    totals = {row.user_id: row.tok or 0 for row in token_rows}
    result = []
    for u in users:
        d = u.to_dict()
        d["ai_count"] = counts.get(u.id, 0)
        d["ai_tokens"] = totals.get(u.id, 0)
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
def list_login_logs(user_id: int = None, page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    q = db.query(LoginLog).order_by(LoginLog.created_at.desc())
    if user_id:
        q = q.filter_by(user_id=user_id)
    total = q.count()
    logs = q.offset((page-1)*per_page).limit(per_page).all()
    return {"logs": [l.to_dict() for l in logs], "total": total, "page": page, "per_page": per_page}


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
    "ai_system_prompt": "你是产品数据库AI助手。帮助用户查询产品、推荐方案、录入产品信息。\n数据库包含 IoT 产品和设施管理产品。\n用中文简洁回答。使用工具查询时，回复中不要提及工具名称或调用过程，直接呈现查询结果。",
    "ai_keyword_prompt": "你是一个搜索关键词优化器。根据用户查询和数据库实际情况，找到最匹配的搜索关键词。\n规则（按优先级）：\n1. keyword必须来自数据库已有词汇。不存在的词必须替换为最接近的已有词\n2. 映射表: 漏水→水浸, 漏水检测→水浸, 液位检测→水浸, 烟雾→烟感, 感应器→传感器, 探测器→传感器, 空开→智能空开, 无线→WiFi\n3. 如果用户查询含多个产品（如用+连接），keyword中用+连接各产品关键词，不要用空格替代+\n4. 品类选最相关的一个，通讯方式/协议/供电/厂商/价格有则填\n返回JSON: {\"keyword\":\"关键词\",\"category\":\"品类\",\"comm_method\":\"通讯方式\",\"protocol\":\"协议\",\"power\":\"供电方式\",\"manufacturer\":\"厂商\",\"min_price\":null,\"max_price\":null,\"sort_by\":null}，只返回JSON。\n字段说明:\n- keyword/category/comm_method: 基础搜索，有则填\n- protocol: 通讯协议，如MQTT/HTTP/ModbusRTU\n- power: 供电方式，如DC/PoE/Battery\n- manufacturer: 厂商名称，必须来自数据库已有厂商\n- min_price/max_price: 价格区间，数字类型，用户未提则null\n- sort_by: price_asc(价格升序)/price_desc(价格降序)，用户未提则null",
    "ai_extract_prompt": "你是一个物联网产品信息提取助手。根据网页内容提取产品结构化信息，输出必须是有效 JSON。",
}
_MODEL_DEFAULTS = {"ai_chat_model": "deepseek-v4-flash", "ai_keyword_model": "deepseek-v4-flash", "ai_extract_model": "deepseek-v4-flash"}

@router.get("/admin/ai-settings")
def get_ai_settings(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.system_setting import SystemSetting
    result = {"prompts": dict(_PROMPT_DEFAULTS), "models": dict(_MODEL_DEFAULTS)}
    result["prompt_defaults"] = dict(_PROMPT_DEFAULTS)
    result["model_defaults"] = dict(_MODEL_DEFAULTS)
    for s in db.query(SystemSetting).all():
        if s.key in _PROMPT_DEFAULTS:
            result["prompts"][s.key] = s.value
        elif s.key in _MODEL_DEFAULTS:
            result["models"][s.key] = s.value
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
    recent = db.query(AIUsageLog).order_by(AIUsageLog.created_at.desc()).limit(10).all()
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
def get_download_logs(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.download_log import DownloadLog
    q = db.query(DownloadLog).order_by(DownloadLog.created_at.desc())
    total = q.count()
    logs = q.offset((page-1)*per_page).limit(per_page).all()
    return {"logs": [l.to_dict() for l in logs], "total": total, "page": page, "per_page": per_page}
    return {"logs": [l.to_dict() for l in logs]}
