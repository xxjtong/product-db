"""AI Product Assistant — SSE chat with direct LLM + tool calling + conversation persistence."""
from __future__ import annotations
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user, check_ownership
from app.config import settings
from app.models.user import User
from app.models.solution import Solution
from app.models.ai_models import AIConversation, AIMessage
from app.models.ai_usage_log import AIUsageLog
from app.models.system_setting import SystemSetting
from app.services.ai_engine import engine, DEFAULT_MODEL
# 提示词默认值集中在 admin_routes._PROMPT_DEFAULTS（后台可编辑那份的唯一来源）。
# 以前这里各写一份兜底字符串，结果和默认值漂移（且都没有业务范围围栏）。
from app.routers.admin_routes import _PROMPT_DEFAULTS
from app.services.ai_tools import TOOL_DEFINITIONS, READ_ONLY_TOOL_DEFINITIONS, execute_tool
from app.services.product_helpers import product_eager_loads
from app.schemas.ai import AiChatRequest

router = APIRouter()

MAX_CONTEXT = 20  # max messages to include in context

# 本轮回答没能写完时补的占位回复（见 ai_chat 的 generate）：保证 user/assistant 成对，
# 占用极小但明确 —— 下次接着聊时不会出现两条连续 user 让模型答非所问。
_INTERRUPTED_REPLY = "[回复中断] 本轮回答未完成，请重新提问。"


def _get_ai_setting(db: Session, key: str, default: str) -> str:
    """Read AI setting from DB, fall back to default."""
    try:
        s = db.query(SystemSetting).filter_by(key=key).first()
        return s.value if s else default
    except Exception as e:
        logging.getLogger("uvicorn").warning(f"Failed to read AI setting {key}: {e}")
        return default

# Context cache (TTL 300s)
_ctx_cache: dict = {"ts": 0, "value": ""}


# --- Context Builder ---

def build_context(db: Session) -> str:
    """Build dynamic system prompt with current product database stats (cached 300s)."""
    import time as _time
    now = _time.time()
    if now - _ctx_cache["ts"] < 300:
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

    sys_prompt = _get_ai_setting(db, "ai_system_prompt", _PROMPT_DEFAULTS["ai_system_prompt"])
    result = sys_prompt + f"""

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
    """Get recent messages as OpenAI-compatible format.

    History is replayed to the chat LLM, so the sequence must stay valid:
    a `tool` message is only legal when it answers a `tool_calls` entry of the
    immediately preceding assistant message, and an assistant `tool_calls`
    entry is only legal when every call is answered. Rows written by the
    keyword-extraction / mock paths are bare `tool` records with no matching
    call — replaying them verbatim makes the provider reject the whole request
    with 400, and the failure silently degrades to the mock agent.
    """
    msgs = db.query(AIMessage).filter_by(conversation_id=conv_id)\
        .order_by(AIMessage.created_at.desc(), AIMessage.id.desc()).limit(limit).all()
    msgs = list(reversed(msgs))

    result: list = []
    pending_ids: set = set()  # tool_call ids still awaiting a tool result
    pending_idx = -1          # index in result of the assistant owning them

    for m in msgs:
        if m.role == "tool":
            tcid = m.tool_call_id or ""
            if tcid and tcid in pending_ids:
                pending_ids.discard(tcid)
                result.append({"role": "tool", "tool_call_id": tcid, "content": m.content or ""})
            # Unmatched tool row (no preceding tool_calls) — drop it
            continue

        # Drop an assistant whose tool_calls were never answered
        if pending_ids:
            del result[pending_idx]
            pending_ids = set()
            pending_idx = -1

        if m.role not in ("user", "assistant", "system"):
            continue

        msg = {"role": m.role, "content": m.content or ""}
        if m.tool_calls:
            try:
                calls = json.loads(m.tool_calls)
            except (json.JSONDecodeError, TypeError):
                calls = None
            wait_ids = {c.get("id") for c in calls if c.get("id")} if calls else set()
            if wait_ids:
                msg["tool_calls"] = calls
                pending_ids = wait_ids
                pending_idx = len(result)
        result.append(msg)

    if pending_ids:
        del result[pending_idx]

    # Never start the window mid-turn — a leading assistant/tool message with
    # no user message before it is rejected too.
    while result and result[0]["role"] != "user":
        result.pop(0)

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

def _product_to_dict(p) -> dict:
    """Convert a Product model to a flat dict for AI response."""
    return {
        "id": p.id,
        "name": p.name,
        "model": p.model or "",
        "category": p.category.name if p.category else "",
        "manufacturer": p.manufacturer.name if p.manufacturer else "",
        "price": float(p.base_price) if p.base_price else 0,
        "comm_methods": [cm.method.name for cm in p.comm_methods if cm.method],
        "power_supplies": [ps.power.name for ps in p.power_supplies if ps.power],
        "description": (p.description or "")[:200],
    }


def _parse_tool_result(result_str: str) -> tuple:
    """Safely parse tool result JSON → (products, created_quote, quotation_preview)。"""
    try:
        tr = json.loads(result_str)
        return tr.get("products"), tr.get("created_quote"), tr.get("quotation_preview")
    except (json.JSONDecodeError, TypeError, KeyError):
        return None, None, None


# Raw tool-call markup that some models emit as plain text instead of returning
# structured `tool_calls`. Tags are wrapped in ASCII or full-width vertical bars.
_DSML_MARK = r'[\|\uff5c]{2}DSML[\|\uff5c]{2}'


def _parse_dsml_tool_calls(content: str) -> list:
    """Recover plain-text tool-call markup into OpenAI `tool_calls` shape."""
    if not content or "DSML" not in content:
        return []
    invoke_re = re.compile(
        _DSML_MARK + r'\s*invoke\s+name="([^"]+)"(.*?)</' + _DSML_MARK + r"\s*invoke>",
        re.DOTALL,
    )
    param_re = re.compile(
        _DSML_MARK + r'\s*parameter\s+name="([^"]+)"[^>]*>(.*?)</' + _DSML_MARK + r"\s*parameter>",
        re.DOTALL,
    )
    calls = []
    for name, body in invoke_re.findall(content):
        args: dict = {}
        for key, value in param_re.findall(body):
            value = value.strip()
            if value[:1] in ("[", "{"):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            args[key] = value
        calls.append({
            "id": f"dsml_{len(calls)}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
        })
    return calls


def _score_and_dedup_products(
    keywords: list[str], matches: dict, product_map: dict, filter_args: dict
) -> list[dict]:
    """Score LLM-matched products by keyword relevance, deduplicate, interleave, filter."""
    scored: dict[int, tuple] = {}  # product_id → (item_dict, score)
    kw_products: dict[str, list] = {}
    for kw in keywords:
        for i in matches.get(kw, [])[:10]:
            if not str(i).isdigit(): continue
            pid = int(i)
            p = product_map.get(pid)
            if not p: continue
            item = _product_to_dict(p)
            # SQL-level price filter
            if filter_args.get("min_price") is not None and item["price"] < filter_args["min_price"]: continue
            if filter_args.get("max_price") is not None and item["price"] > filter_args["max_price"]: continue
            # Score: name=3, model=2, description=1
            kw_lower = kw.lower()
            pts = 0
            if kw_lower in (p.name or '').lower(): pts += 3
            if kw_lower in (p.model or '').lower(): pts += 2
            if kw_lower in (p.description or '').lower(): pts += 1
            kw_products[kw] = kw_products.get(kw, []) + [item]
            if pid in scored:
                scored[pid] = (item, scored[pid][1] + pts)
            else:
                scored[pid] = (item, pts)
            if len(kw_products[kw]) >= 5:
                break

    # Deduplicate and sort by score descending
    seen_ids: set[int] = set()
    interleaved: list[dict] = []
    for item, _ in sorted(scored.values(), key=lambda x: x[1], reverse=True):
        if item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            interleaved.append(item)

    # Apply sort if specified
    if filter_args.get("sort_by") == "price_asc":
        interleaved.sort(key=lambda x: x["price"])
    elif filter_args.get("sort_by") == "price_desc":
        interleaved.sort(key=lambda x: x["price"], reverse=True)

    return interleaved


def _get_done_events(conv_id, db, total_tokens) -> list[dict]:
    """Return SSE event dicts signaling query completion with product results."""
    text = "查询完成。如需进一步筛选或对比，请告诉我。"
    save_message(conv_id, "assistant", content=text, db=db, commit=False)
    db.commit()
    events = [{"event": "text", "text": char} for char in text]
    events.append({"event": "done", "tokens": total_tokens})
    events.append({"event": "quick_replies", "items": ["对比产品", "全部加入方案"]})
    return events


def run_mock_agent(user_input: str, db: Session, conv_id: int, user_id: int = None):
    """Mock agent using keyword matching — no LLM API key needed."""
    yield {"event": "connect"}
    yield {"event": "first_token"}

    inp = user_input.lower()
    response = ""

    # Check for product search intent
    has_search_intent = any(k in inp for k in ["找", "搜索", "查", "推荐", "有没有", "列出", "哪些", "什么"])
    has_product_keyword = any(k in inp for k in ["网关", "传感器", "路由器", "温度", "湿度", "开关", "控制", "灯", "门禁", "空调", "表", "锁", "屏", "摄像", "控制器"])
    if has_search_intent or has_product_keyword:
        # Split compound queries (e.g. "lorawan网关" → ["lorawan", "网关"])
        # Remove leading +/- used for split syntax, then split on word boundaries
        clean = re.sub(r'^[+]+', '', user_input.strip())
        parts = re.split(r'[\s+，,、]+', clean)
        keywords = [p for p in parts if p] if len(parts) > 1 else [clean]
        args = {"keywords": keywords, "limit": 5}

        yield {"event": "tool", "text": "搜索产品..."}
        result_str = execute_tool("search_products", args, db, user_id=user_id)
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
        except Exception as e:
            logging.getLogger("uvicorn").warning(f"Mock agent: failed to parse tool result: {e}")
            response = "搜索完成，但结果解析出错。请重试。"

    elif "品类" in inp or "分类" in inp or "categories" in inp.lower():
        yield {"event": "tool", "text": "查询品类..."}
        result_str = execute_tool("list_categories", {}, db, user_id=user_id)
        result = json.loads(result_str)
        cats = result.get("categories", [])
        response = f"共有 {len(cats)} 个品类：\n" + "、".join(c["name"] for c in cats[:20])

    elif any(k in inp for k in ["你好", "hello", "hi", "帮助", "help"]):
        response = "你好！我是产品数据库AI助手。我可以帮你：\n- 搜索产品（如「找LoRaWAN传感器」）\n- 查询品类\n- 查看产品详情\n\n试试问我吧！"

    else:
        yield {"event": "tool", "text": "搜索产品..."}
        # Split compound queries into keywords, use multi-keyword search
        clean = re.sub(r'^[+]+', '', user_input.strip())
        parts = re.split(r'[\s+，,、]+', clean)
        keywords = [p for p in parts if p] if len(parts) > 1 else [clean]
        search_terms = [user_input] + keywords
        results = None
        result_str = ""
        for term in search_terms[:3]:
            args = {"keyword": term, "limit": 5}
            result_str = execute_tool("search_products", args, db, user_id=user_id)
            results = json.loads(result_str)
            if results.get("found", 0) > 0:
                break
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


# 关键词提取（Round 0）用的 DB 上下文缓存。**分两档**：full（首轮，含全部产品清单）
# 与 compact（后续轮，只有词表与统计）。分开缓存，否则首轮会把精简档也污染成全量。
_db_ctx_cache: dict = {"full": {"ts": 0.0, "value": ""}, "compact": {"ts": 0.0, "value": ""}}


def _build_db_context(db: Session, full: bool = True) -> str:
    """构造关键词提取用的 DB 上下文（300s TTL）。

    `full=True` 带上**全部产品**的 `[ID]` 名称/型号/描述/specs —— 会话**首轮**冷启动
    选型用：模型据此把用户需求直接对上具体产品 ID（代价是这份上下文很大，实测单轮
    input 一度到 51.7k tokens）。

    `full=False` 只给「统计 + 品类/厂商/通讯方式/协议/供电/传感指标」这些**词表**，
    够模型判断「该搜什么关键词」，不再塞产品正文 —— 后续轮的产品交给
    `search_products` 工具（SQL 检索），而不是每轮重发整库。

    「首轮全量、之后精简」由 ai_chat 按本会话是否首轮决定（R73）。
    """
    key = "full" if full else "compact"
    cache = _db_ctx_cache[key]
    now = time.time()
    if now - cache["ts"] <= 300:
        return cache["value"]

    from app.models.category import Category
    from app.models.product import Product
    from app.models.dictionary import Manufacturer, DictCommMethod, DictCommProtocol, DictPowerSupply, DictSensorMetric
    cats = db.query(Category).filter(Category.is_active == True).order_by(Category.name).all()
    mfgs = db.query(Manufacturer).order_by(Manufacturer.name).all()
    methods = db.query(DictCommMethod).order_by(DictCommMethod.name).all()
    protocols = db.query(DictCommProtocol).order_by(DictCommProtocol.name).all()
    powers = db.query(DictPowerSupply).order_by(DictPowerSupply.name).all()
    metrics = db.query(DictSensorMetric).order_by(DictSensorMetric.name).all()

    # 词表部分：两档共用。compact 档到这里就够了 —— 模型据此判断该搜什么
    vocab = f"""数据库现有数据：
品类({len(cats)}): {', '.join(c.name for c in cats)}
厂商({len(mfgs)}): {', '.join(m.name for m in mfgs)}
通讯方式({len(methods)}): {', '.join(m.name for m in methods)}
协议({len(protocols)}): {', '.join(p.name for p in protocols)}
供电({len(powers)}): {', '.join(m.name for m in powers)}
传感器指标({len(metrics)}): {', '.join(m.name for m in metrics)}"""

    if not full:
        value = vocab + (
            "\n（本会话已过首轮，为省 token 不再重复发送产品清单；需要具体产品时"
            "请调用 search_products 工具，按关键词/品类/厂商/通讯方式检索）"
        )
        cache["value"] = value
        cache["ts"] = now
        return value

    products = db.query(Product.id, Product.name, Product.model, Product.description, Product.specs)\
        .filter(Product.status == 'active').order_by(Product.name).all()

    from app.services.product_category_helper import get_product_category_map
    cat_id_to_name = {c.id: c.name for c in cats}
    pc_id_map = get_product_category_map(db)
    prod_cats: dict[int, list[str]] = {}
    for pid, cids in pc_id_map.items():
        prod_cats[pid] = [cat_id_to_name[cid] for cid in cids if cid in cat_id_to_name]

    prod_parts = []
    for p in products:
        pid = p.id
        part = f"[ID:{pid}] {p.name}"
        if p.model: part += f"({p.model})"
        cats_list = prod_cats.get(pid, [])
        if cats_list:
            part += f" [{', '.join(cats_list)}]"
        if p.description:
            desc = re.sub(r'https?://\S+', '', p.description).strip()
            if desc:
                part += f": {desc}"
        if p.specs and isinstance(p.specs, dict):
            spec_kv = [f"{k}={v}" for k, v in p.specs.items() if v]
            if spec_kv:
                part += f" | specs: {', '.join(spec_kv)}"
        prod_parts.append(part)
    products_text = '\n'.join(prod_parts)

    value = f"""{vocab}
产品列表(名称/型号/描述/specs):
{products_text}"""
    cache["value"] = value
    cache["ts"] = now
    return value


async def run_agent(messages: list, db: Session, conv_id: int, user_id: int = None,
                    tool_definitions: list = None, full_db_context: bool = True):
    """Run agent loop with tool calling. Yields SSE event dicts.

    `full_db_context`：Round 0 是否把**全部产品清单**塞进关键词提取的 system prompt。
    ai_chat 只在会话**首轮**传 True（冷启动选型），之后传 False 走精简词表（R73）。
    """
    # 不给就用全量工具集；带方案上下文时由调用方传入（否则只读，见 READ_ONLY_TOOL_DEFINITIONS）
    tools = TOOL_DEFINITIONS if tool_definitions is None else tool_definitions
    yield {"event": "connect"}

    # If no API key, use mock mode
    if not settings.AI_GATEWAY_KEY:
        user_msg = messages[-1]["content"] if messages else ""
        for event in run_mock_agent(user_msg, db, conv_id, user_id=user_id):
            yield event
        return

    products_found = False
    current_messages = messages[:]
    max_turns = 2
    total_tokens = {"in": 0, "out": 0}

    # Round 0: keyword extraction with full DB context
    auth_failed = False
    user_query = messages[-1]["content"] if messages else ""
    try:
        db_ctx = _build_db_context(db, full=full_db_context)

        kw_model = _get_ai_setting(db, "ai_keyword_model", "deepseek-chat")
        # 兜底用共享默认值：此前这里藏了**第三份**独立文案，与 _PROMPT_DEFAULTS 那份不一致，
        # 一旦库里没这行就会用上过时版本（R67 统一）
        kw_prompt = _get_ai_setting(db, "ai_keyword_prompt", _PROMPT_DEFAULTS["ai_keyword_prompt"])
        kw_system = f"{kw_prompt}\n\n{db_ctx}"
        extract_prompt = [
            {"role": "system", "content": kw_system},
            {"role": "user", "content": user_query},
        ]
        extract_resp = await engine.chat(extract_prompt, model=kw_model, temperature=0, max_tokens=2000)
        usage_ext = extract_resp.get("usage", {})
        total_tokens["in"] += usage_ext.get("prompt_tokens", 0)
        total_tokens["out"] += usage_ext.get("completion_tokens", 0)
        content = extract_resp["choices"][0]["message"].get("content") or extract_resp["choices"][0]["message"].get("reasoning_content", "")
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        # DSML fallback: deepseek-v4-flash sometimes returns native tool-call format
        has_dsml = not json_match and ('DSML' in content or 'dsml' in content)
        if has_dsml:
            dsml_kws = re.findall(r'name="keyword"[^>]*>([^<]+)<', content)
            keywords = [k.strip() for k in dsml_kws if k.strip()]
            if keywords:
                yield {"event": "tool", "text": f"搜索 {' + '.join(keywords)}..."}
                args = {"keywords": keywords, "limit": 5}
                result_str = execute_tool("search_products", args, db, user_id=user_id)
                # Not persisted: this is an internal retrieval artifact, not a
                # real tool call — storing it would leave an unmatched `tool`
                # row that makes the next round's history invalid.
                current_messages.append({"role": "assistant", "content": None, "tool_calls": [{
                    "id": "extract_0", "type": "function",
                    "function": {"name": "search_products", "arguments": json.dumps(args)}
                }]})
                current_messages.append({"role": "tool", "tool_call_id": "extract_0", "content": result_str})
                products_data, _, _ = _parse_tool_result(result_str)
                if products_data:
                    products_found = True
                    yield {"event": "products", "data": products_data}
                    yield {"event": "component", "component": "SolutionProductCard", "props": {"products": products_data}}
                max_turns = 1
        elif json_match:
            extracted = json.loads(json_match.group())
            # Support both "keywords" (array, new) and "keyword" (string, legacy)
            kw_raw = extracted.get("keywords") or extracted.get("keyword")
            if isinstance(kw_raw, list):
                keywords = [k for k in kw_raw if k and str(k).strip()]
            elif kw_raw and str(kw_raw).strip():
                keywords = [str(kw_raw).strip()]
            else:
                keywords = []
            brand = extracted.get("brand") or extracted.get("manufacturer")
            has_filter = bool(extracted.get("category") or extracted.get("comm_method") or extracted.get("protocol") or extracted.get("power") or brand)
            matches = extracted.get("matches", {})  # LLM-matched: {keyword: [id1, id2, ...]}
            solutions = extracted.get("solutions")  # multi-solution grouping

            # Multi-solution mode: yield grouped results
            if solutions and isinstance(solutions, list) and len(solutions) > 0:
                from app.models.product import Product as ProductModel
                all_pids = set()
                for sol in solutions:
                    for pid in sol.get("product_ids", [])[:10]:
                        if str(pid).isdigit():
                            all_pids.add(int(pid))
                product_map = {}
                if all_pids:
                    prods = db.query(ProductModel).options(*product_eager_loads()).filter(
                        ProductModel.id.in_(all_pids), ProductModel.status == 'active'
                    ).all()
                    product_map = {p.id: p for p in prods}

                for sol in solutions:
                    sol_name = sol.get("name", "")
                    sol_desc = sol.get("desc", "")
                    sol_pids = [int(i) for i in sol.get("product_ids", [])[:10] if str(i).isdigit()]
                    sol_products = []
                    for pid in sol_pids:
                        p = product_map.get(pid)
                        if p:
                            sol_products.append(_product_to_dict(p))
                    if sol_products:
                        products_found = True
                        yield {"event": "products", "data": sol_products,
                               "solution_name": sol_name, "solution_desc": sol_desc}
                        yield {"event": "component", "component": "SolutionProductCard",
                               "props": {"products": sol_products,
                                         "solution_name": sol_name, "solution_desc": sol_desc}}
                if products_found:
                    max_turns = 1

            elif keywords or has_filter:
                if keywords:
                    yield {"event": "tool", "text": f"搜索 {' + '.join(keywords)}..."}
                elif brand:
                    yield {"event": "tool", "text": f"搜索品牌 {brand}..."}
                else:
                    yield {"event": "tool", "text": f"筛选产品..."}

                # Build SQL-level filter args (price/sorting not in db_ctx, applied post-match)
                filter_args = {}
                for f in ("category", "comm_method", "protocol", "power"):
                    if extracted.get(f): filter_args[f] = extracted[f]
                if brand: filter_args["manufacturer"] = brand
                if extracted.get("min_price") is not None: filter_args["min_price"] = extracted["min_price"]
                if extracted.get("max_price") is not None: filter_args["max_price"] = extracted["max_price"]
                if extracted.get("sort_by"): filter_args["sort_by"] = extracted["sort_by"]

                if matches and any(matches.get(kw) for kw in keywords):
                    # Hybrid: LLM matched product IDs from db_ctx → validate + dedup + filter
                    # Per-keyword: top 10 from LLM → cross-keyword dedup → cap 5 per keyword → interleave
                    from app.models.product import Product as ProductModel

                    # Batch-load all product IDs across all keywords
                    all_pids: set[int] = set()
                    for kw in keywords:
                        for i in matches.get(kw, [])[:10]:
                            if str(i).isdigit():
                                all_pids.add(int(i))
                    product_map = {}
                    if all_pids:
                        prods = db.query(ProductModel).options(*product_eager_loads()).filter(
                            ProductModel.id.in_(all_pids), ProductModel.status == 'active'
                        ).all()
                        product_map = {p.id: p for p in prods}

                    interleaved = _score_and_dedup_products(keywords, matches, product_map, filter_args)

                    if interleaved:
                        products_found = True
                        result_str = json.dumps({"found": len(interleaved), "products": interleaved}, ensure_ascii=False)
                        current_messages.append({"role": "assistant", "content": None, "tool_calls": [{
                            "id": "extract_0", "type": "function",
                            "function": {"name": "search_products", "arguments": json.dumps({"keywords": keywords, **filter_args})}
                        }]})
                        current_messages.append({"role": "tool", "tool_call_id": "extract_0", "content": result_str})
                        yield {"event": "products", "data": interleaved}
                        yield {"event": "component", "component": "SolutionProductCard", "props": {"products": interleaved}}
                        max_turns = 1

                        # Supplement LLM matches with SQL search when coverage is thin (≤3 results)
                        if len(interleaved) <= 3:
                            args = {"keywords": keywords or [], "limit": 10, **filter_args}
                            result_str = execute_tool("search_products", args, db, user_id=user_id)
                            sql_data, _, _ = _parse_tool_result(result_str)
                            if sql_data:
                                shown_ids = {p["id"] for p in interleaved}
                                extra = [p for p in sql_data if p["id"] not in shown_ids]
                                if extra:
                                    merged = interleaved + extra[:8]
                                    yield {"event": "products", "data": merged}
                                    yield {"event": "component", "component": "SolutionProductCard", "props": {"products": merged}}

                if not products_found:
                    # Fallback: LLM returned no matches → use SQL LIKE search
                    args = {"keywords": keywords or [], "limit": 5, **filter_args}
                    result_str = execute_tool("search_products", args, db, user_id=user_id)
                    current_messages.append({"role": "assistant", "content": None, "tool_calls": [{
                        "id": "extract_0", "type": "function",
                        "function": {"name": "search_products", "arguments": json.dumps(args)}
                    }]})
                    current_messages.append({"role": "tool", "tool_call_id": "extract_0", "content": result_str})
                    products_data, _, _ = _parse_tool_result(result_str)
                    if products_data:
                        products_found = True
                        yield {"event": "products", "data": products_data}
                        yield {"event": "component", "component": "SolutionProductCard", "props": {"products": products_data}}
                    max_turns = 1
    except Exception as e:
        logging.getLogger("uvicorn").warning(f"Keyword extraction failed: {e}")
        # Check for API key auth failure (401) — only warn once
        auth_failed = '401' in str(e) or '401' in str(getattr(e, 'response', ''))
        if auth_failed:
            yield {"event": "warning", "text": "⚠️ AI API key 已过期或无效，使用本地搜索降级。请在管理后台更新 API key。"}

    # If keyword extraction already found products, skip chat LLM
    if products_found:
        for event in _get_done_events(conv_id, db, total_tokens):
            yield event
        return

    chat_model = _get_ai_setting(db, "ai_chat_model", "deepseek-v4-flash")
    for turn in range(max_turns):
        try:
            response = await engine.chat(current_messages, model=chat_model, temperature=0.3,
                                         tools=tools)
            # Accumulate token usage
            usage = response.get("usage", {})
            total_tokens["in"] += usage.get("prompt_tokens", 0)
            total_tokens["out"] += usage.get("completion_tokens", 0)
        except Exception as e:
            logging.getLogger("uvicorn").warning(f"Chat LLM failed: {e}")
            # Check for API key auth failure (401) — only warn if not already warned
            if not auth_failed:
                if '401' in str(e) or '401' in str(getattr(e, 'response', '')):
                    yield {"event": "warning", "text": "⚠️ AI API key 已过期或无效，使用本地搜索降级。请在管理后台更新 API key。"}
            # If keyword extraction already found products, don't mock-re-search
            if products_found:
                for event in _get_done_events(conv_id, db, total_tokens):
                    yield event
                return
            # Fall back to mock mode on API error
            user_msg = messages[-1]["content"] if messages else ""
            for event in run_mock_agent(user_msg, db, conv_id, user_id=user_id):
                yield event
            return

        choice = response["choices"][0]
        msg = choice["message"]
        content = msg.get("content") or msg.get("reasoning_content", "") or ""

        # If the model wants to call a tool. Some models ignore the `tools`
        # declaration and emit the call as plain text instead — recover it so
        # the tool actually runs instead of leaking the markup to the user.
        tool_calls = msg.get("tool_calls") or _parse_dsml_tool_calls(content)
        if tool_calls:
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
                    result_str = execute_tool(tool_name, args, db, user_id=user_id)
                except Exception as e:
                    result_str = json.dumps({"error": str(e)})

                # Save tool result
                save_message(conv_id, "tool", content=result_str, tool_call_id=tc.get("id", ""), db=db, commit=False)
                products_data, _, preview = _parse_tool_result(result_str)
                if products_data:
                    products_found = True
                    yield {"event": "products", "data": products_data}
                    yield {"event": "component", "component": "SolutionProductCard", "props": {"products": products_data}}
                if preview:
                    # 报价单**预览**卡：点「确认生成」才真正落库（R71）
                    products_found = True
                    yield {"event": "component", "component": "QuoteDraftCard", "props": preview}

                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result_str,
                })

            yield {"event": "first_token"}
            continue

        # Model returned a text response — stream it.
        # Residual tool-call markup is not a real answer (the parse above
        # already failed), so never show it to the user.
        if "DSML" in content:
            content = "抱歉，我没能理解这个请求，请换个说法再试一次。"
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
        text = response["choices"][0]["message"].get("content") or response["choices"][0]["message"].get("reasoning_content") or ""
        if "DSML" in text or not text:
            text = "查询完成，如需进一步了解请告诉我。" if products_found else "抱歉，查询超时，请重新提问。"
    except Exception as e:
        logging.getLogger("uvicorn").warning(f"run_agent: max-turns LLM call failed: {e}")
        if products_found:
            for char in "查询完成，如需进一步了解请告诉我。":
                yield {"event": "text", "text": char}
            yield {"event": "done", "tokens": total_tokens}
            yield {"event": "quick_replies", "items": ["对比产品", "全部加入方案"]}
            return
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
async def ai_chat(data: AiChatRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """SSE chat endpoint with tool calling and conversation persistence."""
    user_input = data.input.strip()
    conv_id = data.conversation_id

    if not user_input:
        raise HTTPException(400, "Input is required")

    # 方案上下文：只有带着**有权限的**方案时，才把写工具（create_quotation）交给模型。
    # 拿不到上下文时它只能凭空猜一个 solution_id 去建单 —— 浮窗里说一句话就生成一张
    # 报价单，正是从这里进去的。无权/已删的方案按「没有上下文」处理，静默降级为只读。
    solution = None
    if data.solution_id:
        candidate = db.get(Solution, data.solution_id)
        if candidate is not None:
            try:
                check_ownership(candidate, user, strict=True)
                solution = candidate
            except HTTPException:
                logging.getLogger("uvicorn").warning(
                    "ai_chat: 用户 %s 请求了无权访问的方案 %s，本次降级为只读",
                    user.id, data.solution_id)
    tool_definitions = TOOL_DEFINITIONS if solution else READ_ONLY_TOOL_DEFINITIONS

    # Get or create conversation
    conv = get_or_create_conversation(user.id, conv_id, db)

    # Auto-title from first message
    if not conv.title or conv.title == "新对话":
        conv.title = user_input[:30] + ("..." if len(user_input) > 30 else "")
        db.commit()

    # Build context
    system_msg = build_context(db)
    history = get_messages_for_context(conv.id, db)
    # 只有本会话**首轮**把整库产品清单交给模型（冷启动选型）；之后各轮只给词表，
    # 具体产品交给 search_products 工具检索。原先每轮都重发全量，实测单轮 input 51.7k（R73）
    is_first_turn = not history

    messages = [
        {"role": "system", "content": system_msg},
        *history,
        {"role": "user", "content": user_input},
    ]

    # Save user message and capture values before session closes
    cid = conv.id
    uid = user.id  # capture before async context
    source = (data.source or "").strip()[:20]   # 入口来源（floating / solution），只用于用量统计
    save_message(cid, "user", content=user_input, db=db)


    async def generate():
        # Use a fresh DB session for the generator
        sse_db = next(get_db())
        start_time = time.time()
        tokens = {"in": 0, "out": 0}
        success = True
        replied = False  # run_agent 是否已把 assistant 回复写进库
        try:
            async for event in run_agent(messages, sse_db, cid, user_id=uid,
                                         tool_definitions=tool_definitions,
                                         full_db_context=is_first_turn):
                event["conversation_id"] = cid
                if event.get("event") == "done" and event.get("tokens"):
                    tokens = event["tokens"]
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            replied = True
            # Update conversation timestamp
            sse_conv = sse_db.get(AIConversation, cid)
            if sse_conv:
                sse_conv.updated_at = datetime.now(timezone.utc)
                sse_db.commit()
        except asyncio.CancelledError:
            # 客户端断开（关页面/切走）会取消生成器，run_agent 写不到 assistant。
            # 交给 finally 补占位并记失败，然后原样抛出（生命周期由 ASGI 处理）。
            success = False
            raise
        except Exception as e:
            success = False
            logging.getLogger("uvicorn").error(f"AI chat error: {e}", exc_info=True)
            yield f"data: {json.dumps({'event': 'error', 'text': 'AI 服务暂时不可用，请稍后重试'}, ensure_ascii=False)}\n\n"
        finally:
            # user 消息在生成器启动前就已落库，若 assistant 最终没写成，历史里会留下
            # 一条没有回复的孤立 user 消息：下次接话时上下文变成两条连续 user
            # （模型容易答非所问），界面上看也像「回复凭空丢了」。这里补占位保证成对。
            if not replied:
                try:
                    save_message(cid, "assistant", content=_INTERRUPTED_REPLY,
                                 db=sse_db, commit=False)
                    sse_db.commit()
                except Exception as e:
                    sse_db.rollback()
                    logging.getLogger("uvicorn").warning(
                        "写入中断占位回复失败 conv=%s: %s", cid, e)
            # Persist usage log via SQLAlchemy session (before close)
            duration = int((time.time() - start_time) * 1000)
            try:
                usage = AIUsageLog(
                    user_id=uid, operation='chat',
                    tokens_in=tokens.get("in", 0), tokens_out=tokens.get("out", 0),
                    duration_ms=duration, success=success, source=source,
                )
                sse_db.add(usage)
                sse_db.commit()
            except Exception as e:
                logging.getLogger("uvicorn").warning("Failed to log AI usage for user %d: %s", uid, e)
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
        .order_by(AIMessage.created_at, AIMessage.id).all()
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
    """Return current-user AI usage; global totals only for admin.

    全局口径（total / total_tokens_*）此前对所有登录用户返回，属口径溢出 —— 侧边栏
    只展示 user_* 字段，所以对非 admin 去掉全局项不影响界面。
    """
    from app.models.ai_usage_log import AIUsageLog
    from sqlalchemy import func
    user_count = db.query(AIUsageLog).filter_by(user_id=user.id).count()
    user_tokens_in = db.query(func.sum(AIUsageLog.tokens_in)).filter_by(user_id=user.id).scalar() or 0
    user_tokens_out = db.query(func.sum(AIUsageLog.tokens_out)).filter_by(user_id=user.id).scalar() or 0
    payload = {
        "user_count": user_count,
        "user_tokens_in": user_tokens_in,
        "user_tokens_out": user_tokens_out,
    }
    if getattr(user, "role", "") == "admin":
        payload.update({
            "total": db.query(AIUsageLog).count(),
            "total_tokens_in": db.query(func.sum(AIUsageLog.tokens_in)).scalar() or 0,
            "total_tokens_out": db.query(func.sum(AIUsageLog.tokens_out)).scalar() or 0,
        })
    return payload
