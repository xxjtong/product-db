"""AI tool definitions for product database queries."""
import json
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from app.utils.escape import escape_like
from app.services.product_helpers import product_eager_loads
from app.models.product import Product

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "搜索产品数据库中的产品，支持多关键词、品类、通讯方式、供电方式等条件",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string"}, "description": "搜索关键词列表，多个词OR搜索，匹配产品名称和型号"},
                    "category": {"type": "string", "description": "品类名称，如'网关'、'传感器'"},
                    "comm_method": {"type": "string", "description": "通讯方式，如'LoRaWAN'、'Ethernet'、'WiFi'"},
                    "protocol": {"type": "string", "description": "通讯协议，如'MQTT'、'HTTP'、'ModbusRTU'"},
                    "power": {"type": "string", "description": "供电方式，如'DC'、'PoE'、'Battery'"},
                    "brand": {"type": "string", "description": "厂商/品牌名称"},
                    "min_price": {"type": "number", "description": "最低价格"},
                    "max_price": {"type": "number", "description": "最高价格"},
                    "sort_by": {"type": "string", "description": "排序: price_asc, price_desc"},
                    "limit": {"type": "integer", "description": "返回数量限制，默认10，最大50"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_detail",
            "description": "获取指定产品的详细信息，包括规格参数、通讯方式、供电方式等",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "产品ID"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "列出所有产品品类",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_quotation",
            "description": "为当前方案创建报价单。需要方案ID，可选填入已知的产品ID和数量列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "solution_id": {"type": "integer", "description": "方案ID"},
                    "items": {"type": "array", "description": "可选，已知的产品列表", "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "quantity": {"type": "number"},
                        },
                    }},
                },
                "required": ["solution_id"],
            },
        },
    },
]


def execute_tool(tool_name: str, arguments: dict, db) -> str:
    """Execute a tool function and return the result as JSON string."""
    from app.models.product import Product
    from app.models.category import Category
    from app.models.dictionary import Manufacturer, DictCommMethod, DictCommProtocol, DictPowerSupply
    from app.models.mapping import ProductCommMethod, ProductCommProtocol, ProductPowerSupply

    if tool_name == "search_products":
        # Support both "keywords" (array) and "keyword" (string)
        kw_raw = arguments.get("keywords") or arguments.get("keyword")
        if isinstance(kw_raw, list):
            keywords = [k.strip() for k in kw_raw if k and str(k).strip()]
        elif kw_raw and str(kw_raw).strip():
            keywords = [str(kw_raw).strip()]
        else:
            keywords = []
        category = (arguments.get("category") or "").strip()
        comm_method = (arguments.get("comm_method") or "").strip()
        protocol = (arguments.get("protocol") or "").strip()
        power = (arguments.get("power") or "").strip()
        # Support both "brand" and "manufacturer"
        manufacturer = (arguments.get("brand") or arguments.get("manufacturer") or "").strip()
        min_price = arguments.get("min_price")
        max_price = arguments.get("max_price")
        sort_by = (arguments.get("sort_by") or "").strip()
        limit = min(int(arguments.get("limit", 10) or 10), 50)

        # Build base query with non-keyword filters
        def _apply_filters(q):
            if category:
                cat = db.query(Category).filter(Category.name.ilike(f"%{escape_like(category)}%")).first()
                if cat:
                    q = q.filter(Product.category_id == cat.id)
            if manufacturer:
                mfg = db.query(Manufacturer).filter(Manufacturer.name.ilike(f"%{escape_like(manufacturer)}%")).first()
                if mfg:
                    q = q.filter(Product.manufacturer_id == mfg.id)
            if comm_method:
                q = q.filter(Product.comm_methods.any(
                    ProductCommMethod.method.has(DictCommMethod.name.ilike(f"%{escape_like(comm_method)}%"))
                ))
            if protocol:
                q = q.filter(Product.comm_protocols.any(
                    ProductCommProtocol.protocol.has(DictCommProtocol.name.ilike(f"%{escape_like(protocol)}%"))
                ))
            if power:
                q = q.filter(Product.power_supplies.any(
                    ProductPowerSupply.power.has(DictPowerSupply.name.ilike(f"%{escape_like(power)}%"))
                ))
            if min_price is not None:
                q = q.filter(Product.base_price >= min_price)
            if max_price is not None:
                q = q.filter(Product.base_price <= max_price)
            if sort_by == "price_asc":
                q = q.order_by(Product.base_price.asc())
            elif sort_by == "price_desc":
                q = q.order_by(Product.base_price.desc())
            return q

        def _search_kw(kw: str, base_q, max_results: int):
            """Search for a single keyword, return up to max_results products."""
            kw_clean = escape_like(kw)
            return base_q.filter(or_(
                Product.name.ilike(f"%{kw_clean}%"),
                Product.model.ilike(f"%{kw_clean}%"),
                Product.description.ilike(f"%{kw_clean}%"),
            )).options(
                selectinload(Product.category),
                selectinload(Product.manufacturer),
                selectinload(Product.comm_methods).selectinload(ProductCommMethod.method),
                selectinload(Product.power_supplies).selectinload(ProductPowerSupply.power),
            ).limit(max_results).all()

        base_q = db.query(Product).filter(Product.status == "active")
        base_q = _apply_filters(base_q)

        has_filters = bool(category or manufacturer or comm_method or protocol or power or min_price is not None or max_price is not None)

        if len(keywords) <= 1:
            # Single keyword — simple search with relevance scoring
            kw = keywords[0] if keywords else ""
            products = _search_kw(kw, base_q, limit + 10) if kw else []
            # Sort by match quality: name > model > description
            if kw and products:
                kw_lower = kw.lower()
                def _score(p):
                    pts = 0
                    if kw_lower in (p.name or '').lower(): pts += 3
                    if kw_lower in (p.model or '').lower(): pts += 2
                    if kw_lower in (p.description or '').lower(): pts += 1
                    return pts
                products.sort(key=_score, reverse=True)
                products = products[:limit]
            # Fallback: no results but filters active → return filtered results
            if not products and has_filters:
                products = base_q.options(
                    selectinload(Product.category), selectinload(Product.manufacturer),
                    selectinload(Product.comm_methods).selectinload(ProductCommMethod.method),
                    selectinload(Product.power_supplies).selectinload(ProductPowerSupply.power),
                ).limit(limit).all()
        else:
            # Multi-keyword — search each independently, score by match quality
            # Fetch more candidates than needed so scoring can pick the best ones
            candidates_per_kw = max(limit * 3, 20)
            scored: dict[int, tuple] = {}  # product_id → (product, score)
            for kw in keywords:
                found = _search_kw(kw, base_q, candidates_per_kw)
                kw_lower = kw.lower()
                for p in found:
                    # Score: name=3, model=2, description=1
                    pts = 0
                    if kw_lower in (p.name or '').lower(): pts += 3
                    if kw_lower in (p.model or '').lower(): pts += 2
                    if kw_lower in (p.description or '').lower(): pts += 1
                    if p.id in scored:
                        scored[p.id] = (p, scored[p.id][1] + pts)
                    else:
                        scored[p.id] = (p, pts)

            # Sort by score descending, take top results
            products = [p for p, _ in sorted(scored.values(), key=lambda x: x[1], reverse=True)][:limit]

            # All keywords failed but filters active → return filtered
            if not products and has_filters:
                products = base_q.options(
                    selectinload(Product.category), selectinload(Product.manufacturer),
                    selectinload(Product.comm_methods).selectinload(ProductCommMethod.method),
                    selectinload(Product.power_supplies).selectinload(ProductPowerSupply.power),
                ).limit(limit).all()

        if not products:
            return json.dumps({"found": 0, "message": "未找到匹配产品"}, ensure_ascii=False)

        # Build result items; per-category cap only for single-keyword
        per_cat = 3 if len(keywords) <= 1 else 20  # no practical cap for multi-kw
        by_cat: dict[str, list] = {}
        for p in products:
            cat_name = p.category.name if p.category else ""
            mfg_name = p.manufacturer.name if p.manufacturer else ""
            comms = [cm.method.name for cm in p.comm_methods if cm.method]
            powers = [ps.power.name for ps in p.power_supplies if ps.power]
            item = {
                "id": p.id,
                "name": p.name,
                "model": p.model or "",
                "category": cat_name,
                "manufacturer": mfg_name,
                "price": float(p.base_price) if p.base_price else 0,
                "comm_methods": comms,
                "power_supplies": powers,
                "description": (p.description or "")[:200],
            }
            by_cat.setdefault(cat_name or "其他", []).append(item)

        result = []
        for items in by_cat.values():
            result.extend(items[:per_cat])

        # Multi-kw: no global cap (each keyword already limited to 5)
        if len(keywords) <= 1:
            result = result[:5]

        return json.dumps({"found": len(result), "products": result}, ensure_ascii=False)

    elif tool_name == "get_product_detail":
        product_id = arguments.get("product_id")
        p = db.scalar(select(Product).options(*product_eager_loads()).where(Product.id == product_id))
        if not p:
            return json.dumps({"error": "产品不存在"}, ensure_ascii=False)

        comms = [{"type": cm.method.method_type, "name": cm.method.name, "details": cm.details or ""}
                 for cm in p.comm_methods if cm.method]
        protocols = [{"name": cp.protocol.name, "direction": cp.direction}
                     for cp in p.comm_protocols if cp.protocol]
        powers = [{"name": ps.power.name, "voltage": ps.voltage_range or "", "battery_life": ps.battery_life or ""}
                  for ps in p.power_supplies if ps.power]
        interfaces = [{"name": hi.interface_name, "qty": hi.quantity, "desc": hi.description or ""}
                      for hi in p.hardware_interfaces]
        sensors = [{"metric": sc.metric.name, "range": sc.measure_range or "", "accuracy": sc.accuracy or ""}
                   for sc in p.sensor_capabilities if sc.metric]

        return json.dumps({
            "id": p.id,
            "name": p.name,
            "model": p.model or "",
            "category": p.category.name if p.category else "",
            "manufacturer": p.manufacturer.name if p.manufacturer else "",
            "supplier": p.supplier.name if p.supplier else "",
            "price": float(p.base_price) if p.base_price else 0,
            "description": p.description or "",
            "comm_methods": comms,
            "comm_protocols": protocols,
            "power_supplies": powers,
            "hardware_interfaces": interfaces,
            "sensor_capabilities": sensors,
            "specs": p.specs or {},
            "product_url": p.product_url or "",
            "view_count": p.view_count or 0,
        }, ensure_ascii=False)

    elif tool_name == "list_categories":
        cats = db.query(Category).filter_by(is_active=True).order_by(Category.sort_order).all()
        result = [{"id": c.id, "name": c.name, "slug": c.slug or "", "level": c.level or 1} for c in cats]
        return json.dumps({"count": len(result), "categories": result}, ensure_ascii=False)

    elif tool_name == "create_quotation":
        from app.models.solution import Solution, SolutionItem
        from app.models.quotation import Quotation, QuotationItem
        from app.models.product import Product as Prod

        solution_id = arguments.get("solution_id")
        sol = db.get(Solution, solution_id)
        if not sol:
            return json.dumps({"error": "方案不存在"}, ensure_ascii=False)

        # Auto-add suggested items if provided
        items_data = arguments.get("items") or []
        for item in items_data:
            pid = item.get("product_id")
            qty = item.get("quantity", 1)
            if pid and not db.query(SolutionItem).filter_by(solution_id=solution_id, product_id=pid).first():
                p = db.get(Prod, pid)
                if p:
                    db.add(SolutionItem(solution_id=solution_id, product_id=pid, quantity=qty,
                                        unit_price=float(p.base_price or 0)))
        db.commit()

        # Create quotation
        items = db.query(SolutionItem).filter_by(solution_id=solution_id).all()
        if not items:
            return json.dumps({"error": "方案中没有产品"}, ensure_ascii=False)

        total = sum(float(it.quantity or 0) * float(it.unit_price or 0) * (float(it.discount_rate or 100) / 100)
                    for it in items)
        qt = Quotation(solution_id=solution_id, title=sol.name,
                       client_name=sol.client_name or "",
                       status="draft", total_amount=total)
        db.add(qt)
        db.commit()
        db.refresh(qt)

        # Add items with product snapshot
        for it in items:
            p = db.get(Prod, it.product_id)
            snapshot = {"name": p.name, "model": p.model, "sku": p.sku} if p else {}
            db.add(QuotationItem(quotation_id=qt.id, product_id=it.product_id, product_snapshot=snapshot,
                                 quantity=it.quantity, unit_price=it.unit_price,
                                 discount_rate=it.discount_rate or 100,
                                 amount=float(it.quantity or 0) * float(it.unit_price or 0)))
        db.commit()

        item_list = []
        for it in db.query(QuotationItem).filter_by(quotation_id=qt.id).all():
            item_list.append({"product_name": it.product_snapshot.get("name", "") if it.product_snapshot else "",
                              "quantity": float(it.quantity or 0),
                              "unit_price": float(it.unit_price or 0)})

        return json.dumps({
            "created_quote": {"id": qt.id, "title": qt.title, "total": float(qt.total_amount or 0), "items": item_list},
            "message": f"已创建报价单 #{qt.id}「{qt.title}」，共 {len(item_list)} 项，合计 ¥{float(qt.total_amount or 0):.0f}",
        }, ensure_ascii=False)

    return json.dumps({"error": f"Unknown tool: {tool_name}"})
