"""AI tool definitions for product database queries."""
import json
from sqlalchemy import or_

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "搜索产品数据库中的产品，支持关键词、品类、通讯方式、供电方式等条件",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词，匹配产品名称和型号"},
                    "category": {"type": "string", "description": "品类名称，如'LoRaWAN网关'、'LoRaWAN传感器'"},
                    "comm_method": {"type": "string", "description": "通讯方式，如'LoRaWAN'、'Ethernet'、'WiFi'"},
                    "protocol": {"type": "string", "description": "通讯协议，如'MQTT'、'HTTP'、'ModbusRTU'"},
                    "power": {"type": "string", "description": "供电方式，如'DC'、'PoE'、'Battery'"},
                    "manufacturer": {"type": "string", "description": "厂商名称"},
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
]


SYSTEM_PROMPT = """你是产品数据库AI助手。帮助用户查询产品、推荐方案、录入产品信息。

数据库包含 IoT 产品（网关、传感器、控制器、路由器等）和设施管理产品（会议屏、访客机、工位牌、门禁等）。

回答规则:
- 用中文简洁回答，尽量简短
- 查产品时调用 search_products 工具
- **不要在回答中展开产品详细规格表格**，系统会自动在下方显示产品卡片
- 列出产品时仅需简要说明名称和价格，1-2句话即可
- 如果没有找到匹配产品，如实告知并建议调整搜索条件
- 回答控制在3-5句话以内，不要生成冗长的markdown表格"""


def execute_tool(tool_name: str, arguments: dict, db) -> str:
    """Execute a tool function and return the result as JSON string."""
    from app.models.product import Product
    from app.models.category import Category
    from app.models.dictionary import Manufacturer, DictCommMethod, DictCommProtocol, DictPowerSupply
    from app.models.mapping import ProductCommMethod, ProductCommProtocol, ProductPowerSupply

    if tool_name == "search_products":
        keyword = (arguments.get("keyword") or "").strip()
        category = (arguments.get("category") or "").strip()
        comm_method = (arguments.get("comm_method") or "").strip()
        protocol = (arguments.get("protocol") or "").strip()
        power = (arguments.get("power") or "").strip()
        manufacturer = (arguments.get("manufacturer") or "").strip()
        limit = min(int(arguments.get("limit", 10) or 10), 50)

        q = db.query(Product).filter(Product.status == "active")

        if keyword:
            # Try exact keyword match first; fall back to bigram only if zero results
            kw_filters = [Product.name.ilike(f"%{keyword}%"), Product.model.ilike(f"%{keyword}%")]
            hit_count = db.query(Product).filter(Product.status == "active").filter(or_(*kw_filters)).count()
            if hit_count > 0:
                q = q.filter(or_(*kw_filters))
            elif len(keyword) >= 3:
                parts = [keyword[i:i+2] for i in range(0, len(keyword)-1)]
                bigram_filters = [Product.name.ilike(f"%{part}%") for part in parts[:5]]
                q = q.filter(or_(*bigram_filters))
            else:
                q = q.filter(or_(*kw_filters))

        if category:
            cat = db.query(Category).filter(Category.name.ilike(f"%{category}%")).first()
            if cat:
                q = q.filter(Product.category_id == cat.id)

        if manufacturer:
            mfg = db.query(Manufacturer).filter(Manufacturer.name.ilike(f"%{manufacturer}%")).first()
            if mfg:
                q = q.filter(Product.manufacturer_id == mfg.id)

        if comm_method:
            q = q.filter(Product.comm_methods.any(
                ProductCommMethod.method.has(DictCommMethod.name.ilike(f"%{comm_method}%"))
            ))

        if protocol:
            q = q.filter(Product.comm_protocols.any(
                ProductCommProtocol.protocol.has(DictCommProtocol.name.ilike(f"%{protocol}%"))
            ))

        if power:
            q = q.filter(Product.power_supplies.any(
                ProductPowerSupply.power.has(DictPowerSupply.name.ilike(f"%{power}%"))
            ))

        products = q.limit(limit).all()

        if not products:
            return json.dumps({"found": 0, "message": "未找到匹配产品"}, ensure_ascii=False)

        result = []
        for p in products:
            cat_name = p.category.name if p.category else ""
            mfg_name = p.manufacturer.name if p.manufacturer else ""
            comms = [cm.method.name for cm in p.comm_methods if cm.method]
            powers = [ps.power.name for ps in p.power_supplies if ps.power]
            result.append({
                "id": p.id,
                "name": p.name,
                "model": p.model or "",
                "category": cat_name,
                "manufacturer": mfg_name,
                "price": float(p.base_price) if p.base_price else 0,
                "comm_methods": comms,
                "power_supplies": powers,
                "description": (p.description or "")[:200],
            })

        return json.dumps({"found": len(result), "products": result}, ensure_ascii=False)

    elif tool_name == "get_product_detail":
        product_id = arguments.get("product_id")
        p = db.get(Product, product_id)
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
            "cost_price": float(p.cost_price) if p.cost_price else 0,
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

    return json.dumps({"error": f"Unknown tool: {tool_name}"})
