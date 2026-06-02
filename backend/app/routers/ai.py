"""AI Product Assistant — SSE chat with direct LLM + tool calling + conversation persistence."""
from __future__ import annotations
import json
import re
import time
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

_usage_pool = ThreadPoolExecutor(max_workers=1)

def _save_usage(user_id: int, tokens_in: int, tokens_out: int, duration_ms: int, success: bool):
    conn = sqlite3.connect('/Users/tong/product-db/backend/product_db.db', timeout=30)
    try:
        conn.execute(
            "INSERT INTO ai_usage_logs (user_id, operation, tokens_in, tokens_out, duration_ms, success) "
            "VALUES (?, 'chat', ?, ?, ?, ?)",
            (user_id, tokens_in, tokens_out, duration_ms, 1 if success else 0)
        )
        conn.commit()
    except Exception as e:
        import logging
        logging.getLogger("uvicorn").warning(f"AI usage log failed: {e}")
    finally:
        conn.close()
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.config import settings
from app.models.user import User
from app.models.ai_models import AIConversation, AIMessage
from app.services.ai_engine import engine, DEFAULT_MODEL
from app.services.ai_tools import TOOL_DEFINITIONS, SYSTEM_PROMPT, execute_tool

router = APIRouter()

MAX_CONTEXT = 20  # max messages to include in context

# Context cache (TTL 60s)
_ctx_cache: dict = {"ts": 0, "value": ""}


# --- Context Builder ---

def build_context(db: Session) -> str:
    """Build dynamic system prompt with current product database stats (cached 60s)."""
    import time as _time
    now = _time.time()
    if now - _ctx_cache["ts"] < 60:
        return _ctx_cache["value"]

    from app.models.product import Product
    from app.models.category import Category, CategorySpecDefinition
    from app.models.dictionary import Manufacturer

    prod_count = db.query(Product).filter_by(status="active").count()
    cat_count = db.query(Category).filter_by(is_active=True).count()
    mfg_count = db.query(Manufacturer).count()

    top_cats = db.query(Category).filter_by(is_active=True, level=2).order_by(Category.sort_order).limit(10).all()
    cat_info = ", ".join(c.name for c in top_cats)

    top_mfgs = db.query(Manufacturer).order_by(Manufacturer.id).limit(10).all()
    mfg_info = ", ".join(m.name for m in top_mfgs)

    # Collect filterable spec definitions per category for AI tool knowledge
    cat_specs = {}
    for c in top_cats:
        specs = db.query(CategorySpecDefinition).filter_by(
            category_id=c.id, is_filterable=True
        ).order_by(CategorySpecDefinition.sort_order).all()
        if specs:
            cat_specs[c.name] = [(s.spec_key, s.display_name) for s in specs]

    spec_lines = []
    for cat_name, specs in cat_specs.items():
        spec_lines.append(
            f"  {cat_name}: " + ", ".join(f"{k}({v})" for k, v in specs)
        )

    result = SYSTEM_PROMPT + f"""

当前数据库状态:
- {prod_count} 个产品
- {cat_count} 个品类 (主要: {cat_info})
- {mfg_count} 个厂商 (主要: {mfg_info})
- 品类可筛选参数:
{chr(10).join(spec_lines) if spec_lines else '  (无)'}"""
    _ctx_cache["value"] = result
    _ctx_cache["ts"] = now
    return result


# --- Conversation Management ---

def get_or_create_conversation(user_id: int, conv_id: int | None, db: Session) -> AIConversation:
    if conv_id:
        conv = db.get(AIConversation, conv_id)
        if conv and conv.user_id == user_id:
            return conv
    conv = AIConversation(user_id=user_id, title="新对话")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_messages_for_context(conv_id: int, db: Session, limit: int = MAX_CONTEXT) -> list:
    """Get recent messages as OpenAI-compatible format."""
    msgs = db.query(AIMessage).filter_by(conversation_id=conv_id)\
        .order_by(AIMessage.created_at.desc()).limit(limit).all()
    msgs = list(reversed(msgs))

    result = []
    for m in msgs:
        if m.role in ("user", "assistant", "system"):
            msg = {"role": m.role, "content": m.content or ""}
            if m.tool_calls:
                try:
                    msg["tool_calls"] = json.loads(m.tool_calls)
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(msg)
        elif m.role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": m.tool_call_id or "",
                "content": m.content or "",
            })
    return result


def save_message(conv_id: int, role: str, content: str = "", tool_calls: str = None,
                 tool_call_id: str = None, db: Session = None, commit: bool = True):
    msg = AIMessage(
        conversation_id=conv_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
    )
    db.add(msg)
    if commit:
        db.commit()
    else:
        db.flush()


# --- Agent Loop ---

def run_mock_agent(user_input: str, db: Session, conv_id: int):
    """Mock agent using keyword matching — no LLM API key needed."""
    yield {"event": "connect"}
    yield {"event": "first_token"}

    inp = user_input.lower()
    response = ""

    # Check for product search intent
    has_search_intent = any(k in inp for k in ["找", "搜索", "查", "推荐", "有没有", "列出", "哪些", "什么"])
    has_product_keyword = any(k in inp for k in ["网关", "传感器", "路由器", "温度", "湿度", "开关", "控制", "灯", "门禁", "空调", "表", "锁", "屏", "摄像", "控制器"])
    if has_search_intent or has_product_keyword:
        # Try to search products
        keyword = user_input  # use full query as keyword for relevance
        args = {"keyword": keyword, "limit": 10}
        if "网关" in inp: args["category"] = "网关"
        elif "传感器" in inp: args["category"] = "传感器"
        elif "路由器" in inp: args["category"] = "路由器"
        if "lora" in inp.lower(): args["comm_method"] = "LoRaWAN"
        if "wifi" in inp.lower(): args["comm_method"] = "WiFi"

        yield {"event": "tool", "text": "搜索产品..."}
        result_str = execute_tool("search_products", args, db)
        save_message(conv_id, "tool", content=result_str, db=db, commit=False)
        try:
            result = json.loads(result_str)
            if result.get("products"):
                yield {"event": "products", "data": result["products"]}
                yield {"event": "component", "component": "SolutionProductCard", "props": {"products": result["products"]}}
            if result.get("found", 0) > 0:
                products = result["products"]
                response = f"找到 {len(products)} 个相关产品：\n\n"
                for p in products:
                    response += f"**{p['name']}**"
                    if p.get('model'): response += f" ({p['model']})"
                    response += f"\n  品类: {p.get('category', '')} | 厂商: {p.get('manufacturer', '')}"
                    comms = p.get('comm_methods', [])
                    powers = p.get('power_supplies', [])
                    if comms or powers:
                        response += f" | {' '.join(comms)} {' '.join(powers)}"
                    if p.get('price') is not None: response += f" | ¥{p['price']}"
                    response += f"\n  {p.get('description', '')[:100]}\n\n"
                response += "需要查看哪个产品的详情？"
            else:
                response = "没有找到匹配的产品。试试调整搜索条件？"
        except Exception:
            import logging
            logging.getLogger("uvicorn").warning("Mock agent: failed to parse tool result")
            response = "搜索完成，但结果解析出错。请重试。"

    elif "品类" in inp or "分类" in inp or "categories" in inp.lower():
        yield {"event": "tool", "text": "查询品类..."}
        result_str = execute_tool("list_categories", {}, db)
        result = json.loads(result_str)
        cats = result.get("categories", [])
        response = f"共有 {len(cats)} 个品类：\n" + "、".join(c["name"] for c in cats[:20])

    elif any(k in inp for k in ["你好", "hello", "hi", "帮助", "help"]):
        response = "你好！我是产品数据库AI助手。我可以帮你：\n- 搜索产品（如「找LoRaWAN传感器」）\n- 查询品类\n- 查看产品详情\n\n试试问我吧！"

    else:
        yield {"event": "tool", "text": "搜索产品..."}
        search_terms = [user_input]
        if len(user_input) > 2:
            words = re.split(r'[，,、\s]+', user_input)
            search_terms = [user_input] + [w for w in words if len(w) >= 1]
        results = None
        result_str = ""
        for term in search_terms[:3]:
            args = {"keyword": term, "limit": 5}
            result_str = execute_tool("search_products", args, db)
            results = json.loads(result_str)
            if results.get("found", 0) > 0:
                break
        save_message(conv_id, "tool", content=result_str, db=db, commit=False)
        if results and results.get("found", 0) > 0:
            products = results["products"]
            yield {"event": "products", "data": products}
            yield {"event": "component", "component": "SolutionProductCard", "props": {"products": products}}
            response = f"找到 {len(products)} 个产品：\n\n"
            for p in products:
                response += f"**{p['name']}** ({p.get('model','')}) — ¥{p.get('price',0)}\n"
        else:
            response = "没有找到匹配的产品。提示：试试搜索品类名、通讯方式、或产品型号。"

    # Stream response
    for char in response:
        yield {"event": "text", "text": char}
    save_message(conv_id, "assistant", content=response, db=db, commit=False)
    db.commit()
    yield {"event": "done"}
    yield {"event": "quick_replies", "items": ["对比产品", "全部加入方案"]}


async def run_agent(messages: list, db: Session, conv_id: int):
    """Run agent loop with tool calling. Yields SSE event dicts."""
    yield {"event": "connect"}

    # If no API key, use mock mode
    if not settings.AI_GATEWAY_KEY:
        user_msg = messages[-1]["content"] if messages else ""
        for event in run_mock_agent(user_msg, db, conv_id):
            yield event
        return

    products_found = False
    current_messages = messages[:]
    max_turns = 2
    total_tokens = {"in": 0, "out": 0}

    # Round 0: keyword extraction via cheap model
    user_query = messages[-1]["content"] if messages else ""
    try:
        extract_prompt = [
            {"role": "system", "content": "从用户查询提取搜索参数，返回JSON: {\"keyword\":\"关键词\",\"category\":\"品类\",\"comm_method\":\"通讯方式\"}。品类从:网关/传感器/节点终端/安防/工具/执行器/蜂窝设备 中选择。只返回JSON。"},
            {"role": "user", "content": user_query},
        ]
        extract_resp = await engine.chat(extract_prompt, model="deepseek-chat", temperature=0, max_tokens=100)
        usage_ext = extract_resp.get("usage", {})
        total_tokens["in"] += usage_ext.get("prompt_tokens", 0)
        total_tokens["out"] += usage_ext.get("completion_tokens", 0)
        content = extract_resp["choices"][0]["message"].get("content", "")
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            extracted = json.loads(json_match.group())
            keyword = (extracted.get("keyword") or "").strip()
            if keyword:
                yield {"event": "tool", "text": f"搜索 {keyword}..."}
                args = {"keyword": keyword, "limit": 10}
                if extracted.get("category"): args["category"] = extracted["category"]
                if extracted.get("comm_method"): args["comm_method"] = extracted["comm_method"]
                result_str = execute_tool("search_products", args, db)
                save_message(conv_id, "tool", content=result_str, db=db, commit=False)
                # Feed tool result into agent context
                current_messages.append({"role": "assistant", "content": None, "tool_calls": [{
                    "id": "extract_0", "type": "function",
                    "function": {"name": "search_products", "arguments": json.dumps(args)}
                }]})
                current_messages.append({"role": "tool", "tool_call_id": "extract_0", "content": result_str})
                try:
                    tr = json.loads(result_str)
                    if tr.get("products"):
                        products_found = True
                        yield {"event": "products", "data": tr["products"]}
                        yield {"event": "component", "component": "SolutionProductCard", "props": {"products": tr["products"]}}
                except Exception:
                    pass
                max_turns = 1  # Only need 1 more turn for text response
    except Exception:
        pass  # Fall through to normal agent

    for turn in range(max_turns):
        try:
            response = await engine.chat(current_messages, tools=TOOL_DEFINITIONS if turn == 0 and not products_found else None, temperature=0.3)
            # Accumulate token usage
            usage = response.get("usage", {})
            total_tokens["in"] += usage.get("prompt_tokens", 0)
            total_tokens["out"] += usage.get("completion_tokens", 0)
        except Exception as e:
            # Fall back to mock mode on API error
            user_msg = messages[-1]["content"] if messages else ""
            for event in run_mock_agent(user_msg, db, conv_id):
                yield event
            return

        choice = response["choices"][0]
        msg = choice["message"]

        # If the model wants to call a tool
        if msg.get("tool_calls"):
            tool_calls = msg["tool_calls"]
            current_messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})

            # Save assistant message with tool calls
            save_message(conv_id, "assistant", tool_calls=json.dumps(tool_calls, ensure_ascii=False), db=db, commit=False)

            for tc in tool_calls:
                fn = tc["function"]
                tool_name = fn["name"]
                try:
                    args = json.loads(fn["arguments"])
                except (json.JSONDecodeError, TypeError):
                    args = {}

                yield {"event": "tool", "text": f"调用 {tool_name}..."}

                # Execute tool
                try:
                    result_str = execute_tool(tool_name, args, db)
                except Exception as e:
                    result_str = json.dumps({"error": str(e)})

                # Save tool result
                save_message(conv_id, "tool", content=result_str, tool_call_id=tc.get("id", ""), db=db, commit=False)
                try:
                    tr = json.loads(result_str)
                    if tr.get("products"):
                        products_found = True
                        yield {"event": "products", "data": tr["products"]}
                        yield {"event": "component", "component": "SolutionProductCard", "props": {"products": tr["products"]}}
                    if tr.get("created_quote"):
                        products_found = True
                        yield {"event": "component", "component": "QuoteDraftCard", "props": tr["created_quote"]}
                except Exception:
                    import logging
                    logging.getLogger("uvicorn").warning("run_agent: failed to parse tool result JSON")

                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result_str,
                })

            yield {"event": "first_token"}
            continue

        # Model returned a text response — stream it
        content = msg.get("content", "")
        # Save the full response
        save_message(conv_id, "assistant", content=content, db=db, commit=False)
        db.commit()

        # Stream the content character by character for SSE effect
        for char in content:
            yield {"event": "text", "text": char}

        yield {"event": "done", "tokens": total_tokens}
        if products_found:
            yield {"event": "quick_replies", "items": ["对比产品", "全部加入方案"]}
        return

    # Max turns exceeded — ask LLM for final response without tools
    try:
        response = await engine.chat(current_messages, temperature=0.3)
        text = response["choices"][0]["message"].get("content", "抱歉，查询超时，请重新提问。")
    except Exception as e:
        import logging
        logging.getLogger("uvicorn").warning(f"run_agent: max-turns LLM call failed: {e}")
        text = "抱歉，查询超时，请重新提问。"
    save_message(conv_id, "assistant", content=text, db=db, commit=False)
    db.commit()
    for char in text:
        yield {"event": "text", "text": char}
    yield {"event": "done", "tokens": total_tokens}
    if products_found:
        yield {"event": "quick_replies", "items": ["对比产品", "全部加入方案"]}


# --- Routes ---

@router.post("/ai/chat")
async def ai_chat(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """SSE chat endpoint with tool calling and conversation persistence."""
    body = await request.json()
    user_input = body.get("input", "").strip()
    conv_id = body.get("conversation_id")

    if not user_input:
        raise HTTPException(400, "Input is required")

    # Get or create conversation
    conv = get_or_create_conversation(user.id, conv_id, db)

    # Auto-title from first message
    if not conv.title or conv.title == "新对话":
        conv.title = user_input[:30] + ("..." if len(user_input) > 30 else "")
        db.commit()

    # Build context
    system_msg = build_context(db)
    history = get_messages_for_context(conv.id, db)

    messages = [
        {"role": "system", "content": system_msg},
        *history,
        {"role": "user", "content": user_input},
    ]

    # Save user message and capture ID before session closes
    cid = conv.id
    save_message(cid, "user", content=user_input, db=db)

    # Log AI usage via thread pool (WAL-safe)
    _usage_pool.submit(_save_usage, user.id, 0, 0, 0, True)

    async def generate():
        # Use a fresh DB session for the generator
        sse_db = next(get_db())
        start_time = time.time()
        tokens = {"in": 0, "out": 0}
        success = True
        try:
            async for event in run_agent(messages, sse_db, cid):
                event["conversation_id"] = cid
                if event.get("event") == "done" and event.get("tokens"):
                    tokens = event["tokens"]
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            # Update conversation timestamp
            sse_conv = sse_db.get(AIConversation, cid)
            if sse_conv:
                sse_conv.updated_at = datetime.now()
                sse_db.commit()
        except Exception as e:
            success = False
            yield f"data: {json.dumps({'event': 'error', 'text': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            # Update token counts via thread pool (WAL-safe)
            duration = int((time.time() - start_time) * 1000)
            _usage_pool.submit(_save_usage, user.id, tokens["in"], tokens["out"], duration, success)
            sse_db.close()

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/ai/conversations")
def list_conversations(db: Session = Depends(get_db), user=Depends(get_current_user)):
    convs = db.query(AIConversation).filter_by(user_id=user.id)\
        .order_by(AIConversation.updated_at.desc()).limit(20).all()
    return {"conversations": [c.to_dict() for c in convs]}


@router.get("/ai/conversations/{conv_id}")
def get_conversation(conv_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    conv = db.get(AIConversation, conv_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    messages = db.query(AIMessage).filter_by(conversation_id=conv_id)\
        .order_by(AIMessage.created_at).all()
    return {"conversation": conv.to_dict(), "messages": [m.to_dict() for m in messages]}


@router.delete("/ai/conversations/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    conv = db.get(AIConversation, conv_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    db.delete(conv)
    db.commit()
    return {"ok": True}


@router.get("/ai/stats")
def get_ai_stats(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Return total and current-user AI usage counts with token stats."""
    from app.models.ai_usage_log import AIUsageLog
    from sqlalchemy import func
    total = db.query(AIUsageLog).count()
    user_count = db.query(AIUsageLog).filter_by(user_id=user.id).count()
    total_tokens_in = db.query(func.sum(AIUsageLog.tokens_in)).scalar() or 0
    total_tokens_out = db.query(func.sum(AIUsageLog.tokens_out)).scalar() or 0
    user_tokens_in = db.query(func.sum(AIUsageLog.tokens_in)).filter_by(user_id=user.id).scalar() or 0
    user_tokens_out = db.query(func.sum(AIUsageLog.tokens_out)).filter_by(user_id=user.id).scalar() or 0
    return {
        "total": total, "user_count": user_count,
        "total_tokens_in": total_tokens_in, "total_tokens_out": total_tokens_out,
        "user_tokens_in": user_tokens_in, "user_tokens_out": user_tokens_out,
    }
