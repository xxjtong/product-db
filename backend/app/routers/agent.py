"""Hermes Agent proxy — SSE streaming passthrough to Hermes API server.

Frontend calls this endpoint; backend forwards to Hermes and streams back the
OpenAI-compatible SSE response.  Auth via JWT (same as all other API routes).
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth import get_current_user
from app.config import settings, DB_FILESYSTEM_PATH
from app.database import get_db
from app.services.storage import save_file, UPLOAD_DIR

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

EXTRACTABLE_TYPES = {
    "text/plain", "text/csv", "application/json", "text/markdown",
    "text/xml", "application/xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


def _extract_file_text(path, filename: str, mime_type: str) -> str:
    """Extract text content from uploaded file for LLM context."""
    if mime_type in ("text/plain", "text/csv", "application/json", "text/markdown", "text/xml", "application/xml"):
        return path.read_text(errors="replace")[:50000]

    if "excel" in mime_type or "spreadsheet" in mime_type or filename.endswith((".xlsx", ".xls")):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            lines = []
            for name in wb.sheetnames:
                ws = wb[name]
                lines.append(f"=== Sheet: {name} ===")
                for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 200), values_only=True):
                    cells = [str(c) if c is not None else "" for c in row]
                    if any(c.strip() for c in cells):
                        lines.append(" | ".join(cells))
                lines.append("")
            return "\n".join(lines)[:50000]
        except Exception as e:
            return f"[无法解析Excel文件: {e}]"

    if "pdf" in mime_type or filename.endswith(".pdf"):
        try:
            import subprocess, tempfile
            result = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=30)
            return result.stdout[:50000] or "[PDF提取结果为空]"
        except Exception as e:
            return f"[无法解析PDF文件: {e}]"

    if "wordprocessing" in mime_type or filename.endswith(".docx"):
        try:
            from docx import Document
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs)[:50000]
        except Exception as e:
            return f"[无法解析DOCX文件: {e}]"

    return ""


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


@router.get("/agent/config")
async def agent_config(user=Depends(get_current_user)):
    """Return agent configuration including database path and API base URL."""
    api_base = settings.AGENT_API_BASE or f"http://127.0.0.1:{8000 if settings.DEV_MODE else 8002}"
    return {
        "db_path": DB_FILESYSTEM_PATH,
        "api_base": f"{api_base}/product-db/api",
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

    # Extract text content for LLM context
    text_content = ""
    if mime_type in EXTRACTABLE_TYPES or stored_name.rsplit(".", 1)[-1].lower() in ("xlsx", "xls", "csv", "txt", "json", "pdf", "docx", "xml", "md"):
        text_content = _extract_file_text(stored_path, file.filename or "", mime_type)

    logger.info("agent_upload: %s → %s (%d bytes, text %d chars)", file.filename, stored_name, len(contents), len(text_content))
    return {
        "url": file_url,
        "filename": file.filename,
        "size": len(contents),
        "type": mime_type,
        "text": text_content,
    }


@router.post("/agent/chat")
async def agent_chat(
    request: Request,
    user=Depends(get_current_user),
):
    """Proxy a chat request to the Hermes Agent API server (SSE passthrough).

    Body (JSON):
        messages: list of {"role": "...", "content": "..."}
        stream: true (required; non-streaming not supported)
        model: optional model name override

    Returns: SSE text/event-stream from Hermes /v1/chat/completions
    """
    body = await request.json()

    messages = body.get("messages")
    if not messages or not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="Missing or invalid 'messages' field")

    stream = body.get("stream", True)
    model = body.get("model", "hermes-agent")

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }

    headers = {
        "Content-Type": "application/json",
        **_build_auth_header(),
    }

    logger.info("agent_chat: proxying %d messages to %s", len(messages), HERMES_CHAT_URL)

    async def _stream():
        try:
            async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    HERMES_CHAT_URL,
                    json=payload,
                    headers=headers,
                ) as resp:
                    if resp.status_code != 200:
                        body_text = await resp.aread()
                        logger.warning(
                            "agent_chat: Hermes returned %s: %s",
                            resp.status_code,
                            body_text[:500],
                        )
                        yield f"data: {json.dumps({'error': f'Hermes returned {resp.status_code}'})}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    async for chunk in resp.aiter_bytes():
                        yield chunk
        except httpx.ConnectError:
            logger.exception("agent_chat: cannot connect to Hermes at %s", HERMES_CHAT_URL)
            yield f"data: {json.dumps({'error': 'Cannot connect to Hermes agent server'})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("agent_chat: stream error")
            yield f"data: {json.dumps({'error': 'Agent stream interrupted'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
