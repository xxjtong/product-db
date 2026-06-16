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
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

HERMES_CHAT_URL = f"{settings.HERMES_API_URL.rstrip('/')}/v1/chat/completions"
HERMES_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


def _build_auth_header() -> dict:
    """Return Authorization header dict if an API key is configured."""
    key = settings.HERMES_API_KEY.strip()
    if key:
        return {"Authorization": f"Bearer {key}"}
    return {}


@router.post("/agent/chat")
async def agent_chat(
    request: Request,
    db: Session = Depends(get_db),
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
