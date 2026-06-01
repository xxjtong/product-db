"""AI Product Assistant — SSE chat endpoint that proxies to Hermes Gateway."""
from __future__ import annotations
import json
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.auth import get_current_user
from app.config import settings
from app.models.user import User

router = APIRouter()


def _build_system_context(db):
    """Build product database context for system prompt."""
    from app.models.category import Category, CategorySpecDefinition
    from app.models.product import Product

    cats = db.query(Category).filter_by(is_active=True).all()
    cat_info = []
    for c in cats:
        specs = db.query(CategorySpecDefinition).filter_by(category_id=c.id, is_filterable=True).all()
        spec_names = [f"{sd.spec_key}({sd.display_name})" for sd in specs]
        cat_info.append(f"  - {c.name} (slug:{c.slug}): {', '.join(spec_names) if spec_names else 'no filterable specs'}")

    products = db.query(Product).filter_by(status="active").all()
    prod_info = [f"  - {p.name} | {p.brand or ''} | {p.category.name if p.category else ''} | ¥{p.base_price or 0}" for p in products[:30]]

    return f"""你是产品数据库助手。帮助用户查询产品、设计方案、录入产品信息。

当前品类:
{chr(10).join(cat_info)}

当前产品(前30):
{chr(10).join(prod_info)}

通用维度可选值:
- 有线通讯: Ethernet, RS485, RS232, DryContact, KNX, M-BUS, USB
- 无线通讯: LoRaWAN, WiFi, 4G, 5G, NB-IoT, Zigbee, BLE, NFC, GNSS, D2D
- 协议: HTTP, HTTPS, MQTT, MQTTS, ModbusRTU, ModbusTCP, BACnet, TCP, UDP, SNMP, SSH, VPN
- 供电: DC, PoE, Battery, USB-C, AC, Solar

用户可能问: 查询产品、推荐方案、录入产品。用中文回答。"""


@router.post("/ai/chat")
async def ai_chat(request: Request, db=Depends(__import__('app.database', fromlist=['get_db']).get_db), user=Depends(get_current_user)):
    """SSE chat endpoint — proxies to Hermes Gateway or returns mock responses."""
    body = await request.json()
    user_input = body.get("input", "")
    history = body.get("history", [])

    # If Gateway URL configured, proxy to it
    if settings.AI_GATEWAY_URL and settings.AI_GATEWAY_KEY:
        return await _proxy_to_gateway(user_input, history, db)

    # Otherwise, return a helpful mock response (dev mode)
    return StreamingResponse(
        _mock_stream(user_input, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _proxy_to_gateway(user_input: str, history: list, db):
    """Stream responses from Hermes Gateway."""
    import httpx

    system_prompt = _build_system_context(db)
    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-10:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": user_input})

    async def generate():
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                f"{settings.AI_GATEWAY_URL}/v1/chat/completions",
                json={"model": "deepseek", "messages": messages, "stream": True},
                headers={"Authorization": f"Bearer {settings.AI_GATEWAY_KEY}"},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            yield f"data: [DONE]\n\n"
                            return
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield f"data: {json.dumps({'text': content})}\n\n"
                        except json.JSONDecodeError:
                            pass
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _mock_stream(user_input: str, db):
    """Dev mode: return simple text response based on keyword matching."""
    from app.models.product import Product
    from app.models.category import Category

    products = db.query(Product).filter_by(status="active").all()
    cats = db.query(Category).filter_by(is_active=True).all()

    response = f"收到你的问题: 「{user_input}」\n\n"
    response += f"当前数据库有 {len(products)} 个产品, {len(cats)} 个品类。\n\n"
    response += "（AI Gateway 未配置，当前为开发模式。请设置 AI_GATEWAY_URL 和 AI_GATEWAY_KEY 以启用完整 AI 功能。）"

    for char in response:
        yield f"data: {json.dumps({'text': char})}\n\n"
        time.sleep(0.02)
    yield "data: [DONE]\n\n"
