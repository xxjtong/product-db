"""AI Product Assistant — SSE chat with direct LLM + tool calling + conversation persistence."""
from __future__ import annotations
import json
import re
from datetime import datetime
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


# --- Context Builder ---

def build_context(db: Session) -> str:
    """Build dynamic system prompt with current product database stats."""
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

    return SYSTEM_PROMPT + f"""

当前数据库状态:
- {prod_count} 个产品
- {cat_count} 个品类 (主要: {cat_info})
- {mfg_count} 个厂商 (主要: {mfg_info})
- 品类可筛选参数:
{chr(10).join(spec_lines) if spec_lines else '  (无)'}"""


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
    search_keywords = ["找", "搜索", "查", "推荐", "有没有", "列出", "哪些", "什么"]
    if any(k in inp for k in search_keywords) or any(k in inp for k in ["网关", "传感器", "路由器", "温度", "湿度"]):
        # Try to search products
        args = {"limit": 5}
        if "网关" in inp: args["category"] = "网关"
        elif "传感器" in inp: args["category"] = "传感器"
        elif "路由器" in inp: args["category"] = "路由器"
        if "lora" in inp.lower(): args["comm_method"] = "LoRaWAN"
        if "wifi" in inp.lower(): args["comm_method"] = "WiFi"
        if "温度" in inp: args["keyword"] = "温度"
        if "湿度" in inp: args["keyword"] = "湿度"
        if "5g" in inp.lower(): args["keyword"] = "5G"

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


def run_agent(messages: list, db: Session, conv_id: int):
    """Run agent loop with tool calling. Yields SSE event dicts."""
    yield {"event": "connect"}

    # If no API key, use mock mode
    if not settings.AI_GATEWAY_KEY:
        user_msg = messages[-1]["content"] if messages else ""
        yield from run_mock_agent(user_msg, db, conv_id)
        return

    current_messages = messages[:]
    max_turns = 2

    for turn in range(max_turns):
        try:
            response = engine.chat(current_messages, tools=TOOL_DEFINITIONS, temperature=0.3)
        except Exception as e:
            # Fall back to mock mode on API error
            user_msg = messages[-1]["content"] if messages else ""
            yield from run_mock_agent(user_msg, db, conv_id)
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
                        yield {"event": "products", "data": tr["products"]}
                        yield {"event": "component", "component": "SolutionProductCard", "props": {"products": tr["products"]}}
                except Exception:
                    pass

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

        yield {"event": "done"}
        return

    # Max turns exceeded — ask LLM for final response without tools
    try:
        response = engine.chat(current_messages, temperature=0.3)
        text = response["choices"][0]["message"].get("content", "抱歉，查询超时，请重新提问。")
    except Exception:
        text = "抱歉，查询超时，请重新提问。"
    save_message(conv_id, "assistant", content=text, db=db, commit=False)
    db.commit()
    for char in text:
        yield {"event": "text", "text": char}
    yield {"event": "done"}


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

    async def generate():
        # Use a fresh DB session for the generator
        sse_db = next(get_db())
        try:
            for event in run_agent(messages, sse_db, cid):
                event["conversation_id"] = cid
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            # Update conversation timestamp
            sse_conv = sse_db.get(AIConversation, cid)
            if sse_conv:
                sse_conv.updated_at = datetime.now()
                sse_db.commit()
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'text': str(e)}, ensure_ascii=False)}\n\n"
        finally:
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
