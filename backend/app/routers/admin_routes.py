"""Admin routes — user management, field visibility, AI prompt, usage stats, logs."""
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.utils.helpers import get_or_404
from app.auth import hash_password, get_current_user
from app.models.user import User
from app.models.login_log import LoginLog
from app.schemas.auth import (
    CreateUserRequest, UpdateUserRequest, ResetPasswordRequest,
    FieldVisibilityUpdate, AIPromptUpdate,
)
from app.utils.escape import escape_like, LIKE_ESCAPE
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
        q = q.filter(User.username.ilike(f"%{escape_like(search)}%", escape=LIKE_ESCAPE))
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
    u = get_or_404(db, User, uid, "User not found")
    apply_partial_update(u, data, ["email", "role", "is_active"])
    if data.password:
        u.password_hash = hash_password(data.password)
    db.commit()
    return {"user": u.to_dict()}


@router.put("/admin/users/{uid}/password")
def reset_user_password(uid: int, data: ResetPasswordRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    u = get_or_404(db, User, uid, "User not found")
    if len(data.password) < 8:
        raise HTTPException(400, "密码至少8位")
    u.password_hash = hash_password(data.password)
    db.commit()
    return {"ok": True}


@router.delete("/admin/users/{uid}")
def delete_user(uid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    u = get_or_404(db, User, uid, "User not found")
    if u.id == user.id:
        raise HTTPException(400, "不能删除自己")
    db.delete(u)
    db.commit()
    return {"ok": True}


def _get_usernames(db: Session, user_ids: set) -> dict:
    """Build user_id → username map."""
    if not user_ids:
        return {}
    from app.models.user import User
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    return {u.id: u.username for u in users}


@router.get("/admin/login-logs")
def list_login_logs(user_id: int = None, page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    q = db.query(LoginLog).order_by(LoginLog.created_at.desc())
    if user_id:
        q = q.filter_by(user_id=user_id)
    total = q.count()
    logs = q.offset((page-1)*per_page).limit(per_page).all()
    uid_map = _get_usernames(db, {l.user_id for l in logs if l.user_id})
    return {"logs": [{**l.to_dict(), "username": uid_map.get(l.user_id, "")} for l in logs], "total": total, "page": page, "per_page": per_page}


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
    "ai_keyword_prompt": "你是产品数据库搜索助手。将用户输入解析为搜索参数，返回JSON。\\n\\n【核心规则】\\n查看下方数据库中的产品名称/型号/描述，提取真实存在的关键词。数据库中有\"空气质量检测仪\"但没有\"空气质量传感器\"→用\"空气质量\"。数据库中有\"温湿度传感器\"→用\"温湿度\"。\\n\\n【JSON字段】\\n- keywords: string[] — 产品关键词(从数据库真实词汇中提取, 品牌名除外)\\n- brand: string|null — 品牌/厂商名(用户说\"星纵\"/\"Milesight\"/\"海信\"等厂牌时填入)\\n- category: string|null — 品类名(用户说\"网关\"/\"传感器\"等品类时填入)\\n- comm_method: string/null — 通讯方式(LoRaWAN/WiFi/Ethernet/4G/5G/RS485等)\\n- protocol: string|null — 协议(MQTT/HTTP/ModbusRTU/BACnet等)\\n- power: string|null — 供电方式(DC/PoE/Battery/USB-C/AC等)\\n- min_price: number|null — 最低价格\\n- max_price: number|null — 最高价格\\n- sort_by: \"price_asc\"|\"price_desc\"|null\\n\\n【同义词映射】\\n漏水→水浸, 液位→水浸, 感应器→传感器, 探测器→传感器, 烟雾→烟感, 空开→智能空开, 无线→WiFi\\n\\n【示例】\\n空气质量传感器 → {\"keywords\":[\"空气质量\"],\"brand\":null,\"category\":null,\"comm_method\":null,\"protocol\":null,\"power\":null,\"min_price\":null,\"max_price\":null,\"sort_by\":null}\\n星纵 → {\"keywords\":[],\"brand\":\"星纵\",\"category\":null,\"comm_method\":null,\"protocol\":null,\"power\":null,\"min_price\":null,\"max_price\":null,\"sort_by\":null}\\n漏水感应器+网关 → {\"keywords\":[\"水浸\",\"网关\"],\"brand\":null,\"category\":null,\"comm_method\":null,\"protocol\":null,\"power\":null,\"min_price\":null,\"max_price\":null,\"sort_by\":null}\\n星纵500元以下的LoRaWAN传感器 → {\"keywords\":[\"传感器\"],\"brand\":\"星纵\",\"category\":\"传感器\",\"comm_method\":\"LoRaWAN\",\"protocol\":null,\"power\":null,\"min_price\":null,\"max_price\":500,\"sort_by\":\"price_asc\"}\\n支持Modbus的DC供电网关 → {\"keywords\":[\"网关\"],\"brand\":null,\"category\":\"网关\",\"comm_method\":null,\"protocol\":\"ModbusRTU\",\"power\":\"DC\",\"min_price\":null,\"max_price\":null,\"sort_by\":null}\\n\\n只返回JSON，无其他内容。",
    "ai_extract_prompt": "你是物联网产品信息提取助手。根据网页内容提取产品结构化信息或者下方的产品规格文本，提取所有可用信息，输出为严格 JSON 格式。",
    "agent_prompt": "你是 PDB，产品数据库系统的 AI 助手。\n\n## 行为准则\n- 查产品必须 web_extract REST API\n- 推荐产品给出品类、通讯方式、规格、价格\n- 对比产品用表格\n- 中文回答，简洁可操作\n\n## 核心规则（最高优先级）\n- API 地址：{{API_BASE}}\n- 每条请求 URL 末尾加 &token={{TOKEN}}\n- 不跳过 API，不猜测，不编造数据\n- 用户上传的文件在 {{UPLOAD_DIR}} 目录下\n\n### 通讯方式 ID\nEthernet=1 RS485=2 LoRaWAN=8 WiFi=9 4G=10 5G=11 NB-IoT=12 Zigbee=13 BLE=14\n\n## 产品查询\n- 搜索：{{API_BASE}}/products?search=关键词&token={{TOKEN}}\n- 按通讯方式：{{API_BASE}}/products?comm_method=8&token={{TOKEN}}\n- 按厂商：先查厂商ID {{API_BASE}}/dicts/manufacturers?per_page=100&token={{TOKEN}} → 再用 {{API_BASE}}/products?manufacturer_id=ID&token={{TOKEN}}\n- 详情：{{API_BASE}}/products/<ID>?token={{TOKEN}}\n\n## 方案 CRUD（写操作先预览让用户确认）\n- 列表：GET {{API_BASE}}/solutions?token={{TOKEN}}\n- 创建：POST {{API_BASE}}/solutions?token={{TOKEN}}  Body: {\"name\":\"方案名\",\"description\":\"描述\",\"product_ids\":[1,2,3],\"customer_name\":\"客户\"}\n- 查看：GET {{API_BASE}}/solutions/<ID>?token={{TOKEN}}\n- 更新：PUT {{API_BASE}}/solutions/<ID>?token={{TOKEN}}  Body: {\"name\":\"新名\"}\n- 删除：DELETE {{API_BASE}}/solutions/<ID>?token={{TOKEN}}\n\n## 报价单 CRUD（写操作先预览让用户确认）\n- 列表：GET {{API_BASE}}/quotations?token={{TOKEN}}\n- 创建：POST {{API_BASE}}/quotations?token={{TOKEN}}  Body: {\"solution_id\":方案ID,\"name\":\"报价单名\",\"customer_name\":\"客户\",\"items\":[{\"product_id\":1,\"quantity\":10,\"unit_price\":100}]}\n- 查看：GET {{API_BASE}}/quotations/<ID>?token={{TOKEN}}\n- 更新：PUT {{API_BASE}}/quotations/<ID>?token={{TOKEN}}\n- 删除：DELETE {{API_BASE}}/quotations/<ID>?token={{TOKEN}}\n\n返回 JSON：{\"items\"|\"products\"|\"solutions\"|\"quotations\": [...], \"total\": N}",
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


# --- LLM Provider Config ---

_LLM_CONFIG_DEFAULTS = {
    "primary": {
        "provider": "deepseek", "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "chat_model": "deepseek-v4-flash", "keyword_model": "deepseek-chat",
        "extract_model": "deepseek-chat",
    },
    "vision": {
        "provider": "xiaomi", "name": "Xiaomi Mimo",
        "base_url": "https://api.xiaomimimo.com/v1",
        "model": "mimo-v2.5",
    },
}

def _load_llm_config(db: Session) -> dict:
    """Load LLM config from system_settings, merge with defaults. API key comes from .env only."""
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="llm_config").first()
    if s and s.value:
        try:
            stored = json.loads(s.value)
            result = {}
            for k in ("primary", "vision"):
                merged = {**_LLM_CONFIG_DEFAULTS.get(k, {}), **stored.get(k, {})}
                merged.pop("api_key", None)  # never expose DB-stored key
                result[k] = merged
            return result
        except (json.JSONDecodeError, TypeError):
            pass
    return {k: dict(v) for k, v in _LLM_CONFIG_DEFAULTS.items()}


@router.get("/admin/llm-config")
def get_llm_config(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    return {"config": _load_llm_config(db), "defaults": _LLM_CONFIG_DEFAULTS}


@router.put("/admin/llm-config")
def update_llm_config(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="llm_config").first()
    if not s:
        s = SystemSetting(key="llm_config", description="LLM provider configuration")
        db.add(s)
    # Strip api_key — it comes from .env only, never stored in DB
    cfg = data.get("config", {})
    for k in cfg:
        if isinstance(cfg[k], dict):
            cfg[k].pop("api_key", None)
    s.value = json.dumps(cfg, ensure_ascii=False)
    db.commit()
    return {"ok": True}


@router.post("/admin/llm-config/test")
def test_llm_config(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Test LLM provider connectivity + fetch available models, store to DB."""
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    cfg = data.get("config", {})
    provider = data.get("provider", "primary")
    # API key always comes from .env, never from request body
    from app.services.ai_engine import engine
    from app.config import settings as app_settings
    key = app_settings.VISION_API_KEY if provider == "vision" else engine.api_key
    if not key:
        raise HTTPException(400, "AI_GATEWAY_KEY or VISION_API_KEY not configured in .env")

    import httpx
    base = cfg["base_url"]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    models = []

    # 1) Chat test
    test_model = cfg.get("model") or cfg.get("chat_model", "gpt-3.5-turbo")
    try:
        resp = httpx.post(f"{base}/chat/completions", headers=headers,
            json={"model": test_model, "messages": [{"role":"user","content":"hi"}], "max_tokens":5}, timeout=15)
        if resp.status_code != 200:
            detail = resp.json().get("error", {}).get("message", resp.text[:100])
            raise HTTPException(400, f"API returned {resp.status_code}: {detail}")
    except httpx.ConnectError as e:
        raise HTTPException(400, f"Connection failed: {str(e)[:100]}")
    except httpx.TimeoutException:
        raise HTTPException(400, "Connection timed out")

    # 2) Fetch available models
    try:
        mr = httpx.get(f"{base}/models", headers=headers, timeout=15)
        if mr.status_code == 200:
            raw = mr.json().get("data", [])
            models = sorted([m["id"] for m in raw if m.get("id")], key=lambda x: x.lower())
    except Exception:
        pass  # models list is best-effort

    # 3) Store to DB
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="llm_models").first()
    if not s:
        s = SystemSetting(key="llm_models", description="Available LLM models by provider")
        db.add(s)
    stored = {}
    if s.value:
        try: stored = json.loads(s.value)
        except: pass
    if models:
        stored[provider] = models
    else:
        stored.pop(provider, None)
    s.value = json.dumps(stored, ensure_ascii=False)
    db.commit()

    return {"ok": True, "message": f"{provider} OK ({test_model})", "models": models}


@router.get("/admin/llm-models")
def get_llm_models(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Get cached available LLM models."""
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="llm_models").first()
    if s and s.value:
        try: return {"models": json.loads(s.value)}
        except: pass
    return {"models": {}}


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
        "by_op": [{"operation": op, "count": c} for op, c in by_op],
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
    uid_map = _get_usernames(db, {l.user_id for l in logs if l.user_id})
    return {"logs": [{**l.to_dict(), "username": uid_map.get(l.user_id, "")} for l in logs], "total": total, "page": page, "per_page": per_page}
