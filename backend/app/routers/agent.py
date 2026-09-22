"""Hermes Agent proxy — SSE streaming passthrough to Hermes API server.

Frontend calls this endpoint; backend forwards to Hermes and streams back the
OpenAI-compatible SSE response.  Auth via JWT (same as all other API routes).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth import get_current_user, require_admin
from app.config import settings, DB_FILESYSTEM_PATH
from app.models.ai_usage_log import AIUsageLog
from app.schemas.ai import AgentChatRequest, AgentApprovalRequest, AgentSuggestionsRequest
from app.database import get_db
from app.services.storage import save_file, UPLOAD_DIR, read_limited, detect_upload_extension
from app.services.approval_manager import approval_manager
from app.services.ai_engine import engine, DEFAULT_MODEL

logger = logging.getLogger(__name__)

router = APIRouter()

HERMES_CHAT_URL = f"{settings.HERMES_API_URL.rstrip('/')}/v1/chat/completions"
HERMES_TIMEOUT = httpx.Timeout(300.0, connect=10.0)

_AGENT_PROMPT_DEFAULT = (
    "你是 PDB，产品数据库系统的 AI 助手。"
    "只处理产品数据库（PDB）相关业务；与业务无关的请求（闲聊、写作、翻译、通用知识、"
    "与 PDB 无关的编程/运维任务）一律礼貌拒绝，一句话说明你只能协助 PDB 业务并给出可做的业务示例，不要展开。"
)

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
    except Exception as e:
        logger.warning("读取默认 agent 提示词失败，使用内置兜底: %s", e)
        return _AGENT_PROMPT_DEFAULT


@router.post("/agent/cleanup-uploads")
async def agent_cleanup_uploads(user=Depends(get_current_user), db=Depends(get_db)):
    """Delete orphaned upload files older than 7 days.

    Only files NOT referenced by any product/file/image row are removed.
    Product documents and images live in the same directory, so a broad
    sweep would silently destroy them (see production 2026-06 data loss).
    """
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    import time
    from app.models.product import Product
    from app.models.product_file import ProductFile
    from app.models.mapping import ProductImage

    referenced = set()
    for (url,) in db.query(Product.image_url).filter(
        Product.image_url.like("/product-db/api/uploads/%")
    ).all():
        if url:
            referenced.add(url.rsplit("/", 1)[-1])
    for (url,) in db.query(ProductFile.file_url).filter(
        ProductFile.file_url.like("/product-db/api/uploads/%")
    ).all():
        if url:
            referenced.add(url.rsplit("/", 1)[-1])
    for (url,) in db.query(ProductImage.url).filter(
        ProductImage.url.like("/product-db/api/uploads/%")
    ).all():
        if url:
            referenced.add(url.rsplit("/", 1)[-1])

    cutoff = time.time() - 7 * 86400
    cleaned = 0
    for f in UPLOAD_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff and f.name not in referenced:
            f.unlink()
            cleaned += 1
    logger.info("agent_cleanup: removed %d orphaned uploads (kept %d referenced)", cleaned, len(referenced))
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

    try:
        contents = await read_limited(file, MAX_UPLOAD_SIZE)
    except ValueError:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024}MB)")

    # 扩展名由服务端按文件内容决定，绝不用客户端给的 Content-Type / 文件名扩展名：
    # 否则可以传一个叫 x.html 的文件（Content-Type 谎报为 image/png）落盘，
    # 再借 uploads 的静态托管诱导管理员打开 → 同源 XSS 读到 localStorage 里的 JWT。
    ext = detect_upload_extension(contents, file.filename or "")
    if not ext:
        raise HTTPException(400, "无法识别的文件类型：内容与允许的类型不匹配")

    # Save to uploads dir with UUID filename
    import uuid
    stored_name = f"{uuid.uuid4().hex}{ext}"
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

    # 返回服务端判定出的类型，而不是客户端声明值
    canonical_type = mimetypes.guess_type(stored_name)[0] or mime_type
    logger.info("agent_upload: %s → %s (%d bytes)", file.filename, stored_name, len(contents))
    return {
        "url": file_url,
        "filename": file.filename,
        "size": len(contents),
        "type": canonical_type,
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

    task = approval_manager.get(task_id)
    if not task:
        raise HTTPException(404, "Approval task not found")
    if user.role != "admin" and task.user_id != user.id:
        raise HTTPException(403, "无权审批该任务")

    ok = approval_manager.decide(task_id, approved, reason)
    if not ok:
        raise HTTPException(404, "Approval task not found")
    return {"ok": True, "task_id": task_id}


@router.get("/agent/approvals")
async def agent_approvals(user=Depends(get_current_user)):
    """List pending approval tasks.

    普通用户只能看到**自己**的待审批任务（tool_input 含业务明细，跨用户可见属越权）；
    管理员看全部，与 `decide` 的权限判断保持一致（R55）。
    """
    pending = approval_manager.get_pending(None if user.role == "admin" else user.id)
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
async def agent_test_approval(user=Depends(require_admin)):
    """Create a test approval task for UI testing. 仅管理员（会往审批队列里塞假任务）。"""
    task = approval_manager.create(
        tool_name="create_quotation",
        tool_label="创建报价单",
        tool_input={"solution_id": 26, "total_price": 636301.50, "customer": "岭南大学"},
        summary="为方案「岭南大学新科学楼 IoT」创建报价单，总价 ¥636,301.50",
        details={"message": "已根据 IoT QTY 需求匹配 11 款产品"},
        user_id=user.id,
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
                     duration_ms: int, success: bool = True, operation: str = "agent_chat"):
    """Persist agent token usage to ai_usage_logs via a fresh DB session."""
    try:
        from app.database import SessionLocal
        sdb = SessionLocal()
        try:
            sdb.add(AIUsageLog(
                user_id=user_id, operation=operation, model=model,
                tokens_in=tokens_in, tokens_out=tokens_out,
                duration_ms=duration_ms, success=success,
            ))
            sdb.commit()
        finally:
            sdb.close()
    except Exception as e:
        # 用量统计静默丢失会让 AI 计费口径对不上，至少留痕
        logger.warning("Failed to log agent usage: %s", e)


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
    """把对话原样转发给 Hermes，并把它的 SSE 流原样回传。

    ⚠️ 这里**不是**审批/工具执行的边界：
    - `messages`（含 system）由客户端拼好后发上来，服务端不加任何 system —— 想改行为
      必须改 `AgentView.vue` 或做服务端注入，改提示词不算数（R59 结论）
    - `AGENT_TOOLS` 只是"声明"给模型，product-db **不执行**工具；写操作靠 prompt 里
      "先预览让用户确认"的软约束 + Hermes 自身权限，没有服务端拦截
    - 唯一会注入 `approval_required` 的路径是下面那段 `"测试审批"` 自测钩子
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
            user_id=user.id,
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


# --- 快捷答复（追问建议）----------------------------------
# 主对话结束后，前端再发一次小请求拿 3 条追问按钮。刻意与 /agent/chat 分开：
# 主流程是 SSE 透传（不能插入额外事件），而且这个请求失败也不能影响对话。
#
# 用本项目自己的 DeepSeek 引擎，**不要走 Hermes**：Hermes 每次会带上它自己的 agent
# 系统提示词（实测 prompt_tokens 15.8k），为了 3 个按钮把整轮成本翻倍不划算；
# DeepSeek 直连同样内容只要几百 token，也快得多。

_SUGGESTION_MAX_TURNS = 6      # 只回看最近几轮，长对话不整个塞进去
_SUGGESTION_MAX_CHARS = 800    # 单条消息截断，防止把长文档回复再喂一遍
_SUGGESTION_TIMEOUT = 20.0     # 只是出几个按钮，不能让用户干等

_SUGGESTION_PROMPT = (
    "根据下面的对话，预测用户接下来最可能问的 3 件事，用来做「快捷答复」按钮。\n"
    "要求：每条不超过 20 个字；站在用户口吻（问句或指令）；不要重复已经问过的内容；不要解释。\n"
    '只输出 JSON 数组，不要代码块、不要任何多余文字。'
    '例如：["列出相关产品","生成报价单","导出 Excel"]'
)


def _parse_suggestions(text: str) -> list[str]:
    """从模型回复里抠出 JSON 数组。

    模型经常多余地加解释或 ```json 包裹，所以只认第一段 [...]；解析不出来就当没有建议，
    绝不把原文透给用户（历史教训：标记泄露会直接显示在气泡里）。
    """
    match = re.search(r"\[.*\]", text or "", re.S)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        s = str(item).strip().strip('"').replace("\n", " ")
        if s and len(s) <= 30:
            out.append(s)
    return out[:3]


@router.post("/agent/suggestions")
async def agent_suggestions(data: AgentSuggestionsRequest, user=Depends(get_current_user)):
    """基于最近对话生成 3 条快捷追问；任何异常都返回空数组。

    这是锦上添花的功能：模型不可用、超时、返回垃圾格式，都不该让用户看到报错，
    更不该影响主对话，所以这里不抛异常。
    """
    if not data.messages or not isinstance(data.messages, list):
        return {"suggestions": []}

    history = []
    for m in data.messages[-_SUGGESTION_MAX_TURNS:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if isinstance(content, list):   # 多模态：只取文本部分
            content = " ".join(
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        text = str(content or "").strip()[:_SUGGESTION_MAX_CHARS]
        if text:
            history.append({"role": role, "content": text})
    if not history:
        return {"suggestions": []}

    if not engine.api_key:
        logger.info("agent_suggestions: 未配置 AI_GATEWAY_KEY，跳过生成")
        return {"suggestions": []}

    start = time.time()
    try:
        body = await asyncio.wait_for(
            engine.chat(
                [{"role": "system", "content": _SUGGESTION_PROMPT}, *history],
                temperature=0.4, max_tokens=200,
            ),
            timeout=_SUGGESTION_TIMEOUT,
        )
        text = (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        usage = body.get("usage") or {}
        # 这次调用的 token 也要记账，否则用量统计口径对不上
        _log_agent_usage(
            user.id, body.get("model") or DEFAULT_MODEL,
            usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
            int((time.time() - start) * 1000), operation="agent_suggestions",
        )
        suggestions = _parse_suggestions(text)
        logger.info("agent_suggestions: 生成 %d 条", len(suggestions))
        return {"suggestions": suggestions}
    except Exception as e:
        logger.warning("agent_suggestions 失败（不影响主对话）: %s", e)
        return {"suggestions": []}
