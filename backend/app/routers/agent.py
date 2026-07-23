"""Hermes Agent proxy — SSE streaming passthrough to Hermes API server.

Frontend calls this endpoint; backend forwards to Hermes and streams back the
OpenAI-compatible SSE response.  Auth via JWT (same as all other API routes).
"""

from __future__ import annotations

import json
import logging
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth import get_current_user
from app.config import settings, DB_FILESYSTEM_PATH
from app.models.ai_usage_log import AIUsageLog
from app.schemas.ai import AgentChatRequest, AgentApprovalRequest
from app.utils.escape import escape_like, LIKE_ESCAPE
from app.database import get_db
from app.services.storage import save_file, UPLOAD_DIR
from app.services.approval_manager import approval_manager

logger = logging.getLogger(__name__)

router = APIRouter()

HERMES_CHAT_URL = f"{settings.HERMES_API_URL.rstrip('/')}/v1/chat/completions"
HERMES_TIMEOUT = httpx.Timeout(300.0, connect=10.0)

_AGENT_PROMPT_DEFAULT = "你是 pdb，产品数据库系统的 AI 助手。"

ALLOWED_UPLOAD_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif", "image/bmp",
    "text/plain", "text/csv", "application/json", "text/markdown",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "application/vnd.ms-excel",  # xls
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "text/xml", "application/xml",
}
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB


def _get_agent_prompt(db):
    """Load agent_prompt from system_settings, fallback to import default."""
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="agent_prompt").first()
    if s and s.value:
        return s.value
    # Fallback to the module-level default in admin_routes
    try:
        from app.routers.admin_routes import _PROMPT_DEFAULTS
        return _PROMPT_DEFAULTS.get("agent_prompt", _AGENT_PROMPT_DEFAULT)
    except Exception:
        return _AGENT_PROMPT_DEFAULT


@router.post("/agent/cleanup-uploads")
async def agent_cleanup_uploads(user=Depends(get_current_user)):
    """Delete upload files older than 7 days."""
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    import time
    cutoff = time.time() - 7 * 86400
    cleaned = 0
    for f in UPLOAD_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()
            cleaned += 1
    logger.info("agent_cleanup: removed %d old uploads", cleaned)
    return {"cleaned": cleaned}


@router.get("/agent/config")
async def agent_config(user=Depends(get_current_user)):
    """Return agent configuration including database path, API base, and upload dir."""
    api_base = settings.AGENT_API_BASE or f"http://127.0.0.1:{8000 if settings.DEV_MODE else 8002}"
    return {
        "db_path": DB_FILESYSTEM_PATH,
        "api_base": f"{api_base}/product-db/api",
        "upload_dir": str(UPLOAD_DIR.resolve()),
    }


@router.get("/agent/prompt")
async def agent_prompt(user=Depends(get_current_user), db=Depends(get_db)):
    """Return the Hermes agent system prompt (admin-editable, DB-backed)."""
    return {"prompt": _get_agent_prompt(db)}


def _build_auth_header() -> dict:
    """Return Authorization header dict if an API key is configured."""
    key = settings.HERMES_API_KEY.strip()
    if key:
        return {"Authorization": f"Bearer {key}"}
    return {}


@router.post("/agent/upload")
async def agent_upload(
    request: Request,
    user=Depends(get_current_user),
):
    """Upload a file for Agent context. Returns a public URL Hermes can fetch."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(400, "Expected multipart/form-data")

    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(400, "No file provided")

    import mimetypes
    guessed = mimetypes.guess_type(file.filename or "")[0]
    mime_type = file.content_type or ""
    # Prefer guessed type over generic octet-stream from browser/curl
    if not mime_type or mime_type == "application/octet-stream":
        mime_type = guessed or mime_type or "application/octet-stream"

    if mime_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(400, f"File type not allowed: {mime_type}")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024}MB)")

    # Save to uploads dir with UUID filename
    import uuid
    ext = (file.filename or "file").rsplit(".", 1)[-1] if "." in (file.filename or "") else ""
    stored_name = f"{uuid.uuid4().hex}"
    if ext:
        stored_name += f".{ext}"
    stored_path = UPLOAD_DIR / stored_name
    stored_path.write_bytes(contents)

    # Build public URL — use configured API base or derive from request
    from urllib.parse import urlparse
    api_base = settings.AGENT_API_BASE
    if api_base:
        base_host = api_base.rstrip("/")
    else:
        base_host = str(request.base_url).rstrip("/")

    file_url = f"{base_host}/product-db/api/uploads/{stored_name}"

    logger.info("agent_upload: %s → %s (%d bytes)", file.filename, stored_name, len(contents))
    return {
        "url": file_url,
        "filename": file.filename,
        "size": len(contents),
        "type": mime_type,
    }


@router.post("/agent/approval/{task_id}")
async def agent_approval(
    task_id: str,
    data: AgentApprovalRequest,
    user=Depends(get_current_user),
):
    """Human decision on a pending agent tool call."""
    approved = data.approved
    reason = data.reason

    ok = approval_manager.decide(task_id, approved, reason)
    if not ok:
        raise HTTPException(404, "Approval task not found")
    return {"ok": True, "task_id": task_id}


@router.get("/agent/approvals")
async def agent_approvals(user=Depends(get_current_user)):
    """List pending approval tasks."""
    pending = approval_manager.get_pending()
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "tool_name": t.tool_name,
                "tool_label": t.tool_label,
                "summary": t.summary,
                "details": t.details,
                "tool_input": t.tool_input,
            }
            for t in pending
        ]
    }


@router.post("/agent/test-approval")
async def agent_test_approval(user=Depends(get_current_user)):
    """Create a test approval task for UI testing."""
    task = approval_manager.create(
        tool_name="create_quotation",
        tool_label="创建报价单",
        tool_input={"solution_id": 26, "total_price": 636301.50, "customer": "岭南大学"},
        summary="为方案「岭南大学新科学楼 IoT」创建报价单，总价 ¥636,301.50",
        details={"message": "已根据 IoT QTY 需求匹配 11 款产品"},
    )
    return {"task_id": task.task_id}


# ── Product-db tool definitions for Hermes ──────────────

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "在产品数据库中搜索产品。可按关键词、品类、通讯方式、价格等条件筛选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词(匹配产品名称/型号/描述)"},
                    "category_id": {"type": "integer", "description": "品类ID"},
                    "comm_method_id": {"type": "integer", "description": "通讯方式ID: 1=Ethernet,2=RS485,8=LoRaWAN,9=WiFi,10=4G,11=5G,13=Zigbee"},
                    "manufacturer_name": {"type": "string", "description": "厂商名称"},
                    "min_price": {"type": "number", "description": "最低价格"},
                    "max_price": {"type": "number", "description": "最高价格"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_detail",
            "description": "获取单个产品的完整规格参数。",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "integer", "description": "产品ID"}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_quotation",
            "description": "从方案创建报价单。⚠️ 写操作，需要用户审批才能执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "solution_id": {"type": "integer", "description": "方案ID"},
                    "customer_name": {"type": "string", "description": "客户名称"},
                    "items": {"type": "array", "items": {"type": "object"}, "description": "报价项目列表"},
                },
                "required": ["solution_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_solution",
            "description": "创建新的IoT解决方案。⚠️ 写操作，需要用户审批才能执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "方案名称"},
                    "description": {"type": "string", "description": "方案描述"},
                    "product_ids": {"type": "array", "items": {"type": "integer"}, "description": "产品ID列表"},
                },
                "required": ["name"],
            },
        },
    },
]

_WRITE_TOOLS = {"create_quotation", "create_solution"}


async def _execute_tool(tool_name: str, tool_args: dict, user_id: int) -> dict:
    """Execute a read-only tool against the product database. Returns result dict."""
    from app.database import SessionLocal
    from app.models.product import Product
    from app.models.dictionary import Manufacturer, DictCommMethod
    from sqlalchemy import or_
    from sqlalchemy.orm import joinedload

    db = SessionLocal()
    try:
        if tool_name == "search_products":
            q = db.query(Product).options(joinedload(Product.manufacturer), joinedload(Product.category))
            keyword = tool_args.get("keyword", "").strip()
            if keyword:
                like = f"%{escape_like(keyword)}%"
                q = q.filter(or_(
                    Product.name.ilike(like),
                    Product.model.ilike(like),
                    Product.description.ilike(like),
                ))
            if tool_args.get("category_id"):
                q = q.filter(Product.category_id == tool_args["category_id"])
            if tool_args.get("manufacturer_name"):
                mfgs = db.query(Manufacturer.id).filter(Manufacturer.name.ilike(f"%{escape_like(tool_args['manufacturer_name'])}%", escape=LIKE_ESCAPE)).all()
                q = q.filter(Product.manufacturer_id.in_([m[0] for m in mfgs]))
            if tool_args.get("min_price") is not None:
                q = q.filter(Product.base_price >= tool_args["min_price"])
            if tool_args.get("max_price") is not None:
                q = q.filter(Product.base_price <= tool_args["max_price"])
            if tool_args.get("comm_method_id"):
                q = q.filter(Product.comm_methods.any(method_id=tool_args["comm_method_id"]))
            products = q.limit(20).all()
            return {
                "total": len(products),
                "items": [{"id": p.id, "name": p.name, "model": p.model or "", "base_price": p.base_price, "description": (p.description or "")[:200], "manufacturer": p.manufacturer.name if p.manufacturer else "", "category": p.category.name if p.category else ""} for p in products],
            }

        elif tool_name == "get_product_detail":
            p = db.query(Product).options(
                joinedload(Product.manufacturer), joinedload(Product.category), joinedload(Product.comm_methods)
            ).filter_by(id=tool_args["product_id"]).first()
            if p:
                method_ids = [m.method_id for m in p.comm_methods]
                method_map: dict[int, str] = {}
                if method_ids:
                    method_map = {m.id: m.name for m in db.query(DictCommMethod).filter(DictCommMethod.id.in_(method_ids)).all()}
                return {
                    "id": p.id, "name": p.name, "model": p.model,
                    "base_price": p.base_price, "description": p.description, "specs": p.specs,
                    "comm_methods": [
                        {"method_id": m.method_id, "method_name": method_map.get(m.method_id, "")}
                        for m in p.comm_methods
                    ],
                }
            return {"error": "Product not found"}

        return {"error": f"Unknown tool: {tool_name}"}
    finally:
        db.close()


async def _call_hermes(client, model: str, messages: list, stream: bool = True, tools: list | None = None):
    """Single pass: call Hermes and stream text lines back (SSE format)."""
    headers = {
        "Content-Type": "application/json",
        **_build_auth_header(),
    }
    payload = {"model": model, "messages": messages, "stream": stream}
    if tools:
        payload["tools"] = tools

    try:
        if client is None:
            async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as c:
                async with c.stream("POST", HERMES_CHAT_URL, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        yield f"data: {json.dumps({'error': f'Hermes returned {resp.status_code}'})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    async for line in resp.aiter_lines():
                        yield line + "\n"
        else:
            async with client.stream("POST", HERMES_CHAT_URL, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    yield f"data: {json.dumps({'error': f'Hermes returned {resp.status_code}'})}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                async for line in resp.aiter_lines():
                    yield line + "\n"
    except httpx.ConnectError:
        yield f"data: {json.dumps({'error': 'Cannot connect to Hermes agent server'})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception:
        yield f"data: {json.dumps({'error': 'Agent stream interrupted'})}\n\n"
        yield "data: [DONE]\n\n"


def _log_agent_usage(user_id: int, model: str, tokens_in: int, tokens_out: int,
                     duration_ms: int, success: bool = True):
    """Persist agent token usage to ai_usage_logs via a fresh DB session."""
    try:
        from app.database import SessionLocal
        sdb = SessionLocal()
        try:
            sdb.add(AIUsageLog(
                user_id=user_id, operation="agent_chat", model=model,
                tokens_in=tokens_in, tokens_out=tokens_out,
                duration_ms=duration_ms, success=success,
            ))
            sdb.commit()
        finally:
            sdb.close()
    except Exception:
        pass


async def _stream_with_usage(gen, user_id: int, model: str):
    """Wrap an SSE line generator, extract token usage, log after [DONE]."""
    start_time = time.time()
    usage_in = 0
    usage_out = 0
    success = True
    try:
        async for line in gen:
            # Extract usage from chunks with top-level "usage" key (OpenAI format)
            if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                try:
                    chunk = json.loads(line[6:].strip())
                    if "usage" in chunk:
                        u = chunk["usage"]
                        usage_in = u.get("prompt_tokens", 0)
                        usage_out = u.get("completion_tokens", 0)
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
            yield line
    except Exception:
        success = False
        raise
    finally:
        duration_ms = int((time.time() - start_time) * 1000)
        _log_agent_usage(user_id, model, usage_in, usage_out, duration_ms, success)


@router.post("/agent/chat")
async def agent_chat(
    data: AgentChatRequest,
    user=Depends(get_current_user),
):
    """Proxy a chat request to Hermes, intercepting write-op tool calls for approval.

    Returns: SSE text/event-stream from Hermes /v1/chat/completions,
             with approval_required events injected for write-op tool calls.
    """
    messages = data.messages
    if not messages or not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="Missing or invalid 'messages' field")

    stream = data.stream
    model = data.model

    # Test trigger: inject approval for "测试审批" before calling Hermes
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, list):
                last_user_msg = " ".join(p.get("text", "") for p in c if p.get("type") == "text")
            else:
                last_user_msg = str(c)
            break

    if "测试审批" in last_user_msg:
        task = approval_manager.create(
            tool_name="create_quotation",
            tool_label="创建报价单",
            tool_input={"solution_id": 26, "total_price": 636301.50, "customer": "岭南大学"},
            summary="为方案「岭南大学新科学楼 IoT」创建报价单，总价 ¥636,301.50",
            details={"message": "已根据 IoT QTY 需求匹配产品"},
        )
        # Emit approval event, wait, then continue
        async def _stream_approval():
            yield f"data: {json.dumps({'type': 'approval_required', 'task_id': task.task_id, 'tool_name': task.tool_name, 'tool_label': task.tool_label, 'summary': task.summary, 'details': task.details, 'tool_input': task.tool_input}, ensure_ascii=False)}\n\n"
            decision = await approval_manager.wait_for_decision(task.task_id)
            yield f"data: {json.dumps({'type': 'approval_result', 'task_id': task.task_id, 'approved': decision.get('approved', False), 'reason': decision.get('reason', '')}, ensure_ascii=False)}\n\n"
            if decision.get("approved"):
                messages.append({"role": "tool", "tool_call_id": f"test_{task.task_id}", "content": json.dumps({"status": "approved", "message": "用户已授权"})})
            else:
                messages.append({"role": "tool", "tool_call_id": f"test_{task.task_id}", "content": json.dumps({"error": "用户拒绝"})})
                yield f"data: {json.dumps({'error': '操作被用户拒绝'})}\n\n"
                yield "data: [DONE]\n\n"
                return
            # Continue to Hermes
            async for line in _stream_with_usage(
                _call_hermes(None, model, messages, stream, tools=AGENT_TOOLS),
                user.id, model,
            ):
                yield line

        return StreamingResponse(_stream_approval(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Normal chat — single pass, streaming with tool definitions
    logger.info("agent_chat: proxying %d messages to %s", len(messages), HERMES_CHAT_URL)
    return StreamingResponse(
        _stream_with_usage(
            _call_hermes(None, model, messages, stream, tools=AGENT_TOOLS),
            user.id, model,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
