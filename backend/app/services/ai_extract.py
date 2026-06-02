"""AI-assisted product info extraction — shared by routers.

Provides AI extraction (via DeepSeek) and regex fallback for
extracting structured product data from web pages or raw text.
"""
from __future__ import annotations
import json
import re
from sqlalchemy.orm import Session
from app.config import settings
from app.models.category import Category
from app.models.dictionary import (
    Manufacturer, DictCommMethod, DictCommProtocol, DictPowerSupply, DictSensorMetric,
)


def build_extraction_prompt(db: Session) -> str:
    """Build system prompt for product extraction AI."""
    cats = db.query(Category).filter_by(is_active=True).order_by(Category.sort_order).all()
    cat_info = [f"  - slug:{c.slug} name:{c.name}" for c in cats if c.slug]

    methods = db.query(DictCommMethod).all()
    method_names = [m.name for m in methods]

    protocols = db.query(DictCommProtocol).all()
    protocol_names = [p.name for p in protocols]

    powers = db.query(DictPowerSupply).all()
    power_names = [p.name for p in powers]

    manufacturers = db.query(Manufacturer).all()
    manufacturer_names = [m.name for m in manufacturers]

    metrics = db.query(DictSensorMetric).all()
    metric_names = [f"{m.name}({m.unit})" for m in metrics]

    return f"""你是一个物联网产品信息提取助手。根据网页内容提取产品结构化信息，输出必须是有效 JSON，不要包含任何其他文本。

品类列表 (选择最匹配的 slug):
{chr(10).join(cat_info)}

通讯方式可选值: {json.dumps(method_names, ensure_ascii=False)}
通讯协议可选值: {json.dumps(protocol_names, ensure_ascii=False)}
供电方式可选值: {json.dumps(power_names, ensure_ascii=False)}
厂商可选值: {json.dumps(manufacturer_names, ensure_ascii=False)}
传感器指标可选值: {json.dumps(metric_names, ensure_ascii=False)}

提取以下信息（未知字段设为 null 或空):
{{
  "name": "产品名称",
  "model": "产品型号",
  "category_slug": "匹配的品类slug",
  "manufacturer_name": "厂商名(必须从可选值匹配,否则null)",
  "description": "产品描述(1-2句)",
  "base_price": "价格数字或null",
  "comm_methods": [{{"name": "Ethernet", "details": "1× 10/100Mbps"}}],
  "comm_protocols": [{{"name": "MQTT", "direction": "both"}}],
  "power_supplies": [{{"name": "DC", "voltage_range": "9-24V", "battery_life": null}}],
  "hardware_interfaces": [{{"interface_name": "RS485", "quantity": 1, "description": "Modbus"}}],
  "sensor_capabilities": [{{"metric_name": "温度", "measure_range": "-20~60", "accuracy": "±0.2"}}],
  "specs": {{"ip_rating": "IP67", "dimensions_mm": "240×164×90.9"}}
}}

注意: comm_methods/comm_protocols/power_supplies 中的 name 字段必须从可选值中匹配，无法匹配的不要添加。"""


def call_ai_extract(url: str, title: str, text: str, db: Session) -> dict:
    """Call AI (DeepSeek) to extract product info from text.

    Falls back to regex extraction if no API key or on error.
    """
    from app.services.ai_engine import engine

    if not settings.AI_GATEWAY_KEY:
        return regex_extract_from_text(title, text, db)

    system_prompt = build_extraction_prompt(db)
    user_msg = f"""网页标题: {title}
网页URL: {url}

网页内容:
{text[:6000]}

请提取该产品的结构化信息。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    try:
        result = engine.chat(messages, temperature=0.1, max_tokens=2000)
        content = result["choices"][0]["message"]["content"]
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return regex_extract_from_text(title, text, db)
    except Exception:
        return regex_extract_from_text(title, text, db)


def regex_extract_from_text(title: str, text: str, db: Session) -> dict:
    """Regex-based product info extraction as fallback when AI is unavailable."""
    result: dict = {
        "name": title or "",
        "model": "",
        "category_slug": None,
        "manufacturer_name": None,
        "description": "",
        "base_price": None,
        "comm_methods": [],
        "comm_protocols": [],
        "power_supplies": [],
        "hardware_interfaces": [],
        "sensor_capabilities": [],
        "specs": {},
    }

    # Try to extract model number from title/text
    model_patterns = [
        r'\b([A-Z]{2,6}[-]?\d{2,4}(?:[-][A-Z]{1,4})?)\b',  # EG71, AM307, UG65
        r'\b([A-Z]{1,2}\d{4}[A-Z]?(?:[-][A-Z]+)?)\b',        # VS121, EM300
    ]
    for pattern in model_patterns:
        m = re.search(pattern, title + " " + text[:2000])
        if m:
            result["model"] = m.group(1)
            break

    # Try to match manufacturer
    manufacturers = db.query(Manufacturer).all()
    for mfg in manufacturers:
        if mfg.name.lower() in (title + text[:3000]).lower():
            result["manufacturer_name"] = mfg.name
            break

    # Try to match category by keywords
    cat_keywords = {
        "lorawan-gateway": ["gateway", "网关", "lora gateway", "lorawan gateway", "基站"],
        "lorawan-sensor": ["sensor", "传感器", "检测", "监测", "探头"],
        "4g-5g-router": ["router", "路由器", "5g", "4g", "cpe"],
        "lorawan-controller": ["controller", "控制器", "采集器"],
        "ip-camera-nvr": ["camera", "摄像机", "nvr", "camera"],
        "lorawan-node": ["node", "节点", "执行器"],
    }
    combined = (title + " " + text[:3000]).lower()
    for slug, keywords in cat_keywords.items():
        if any(k in combined for k in keywords):
            result["category_slug"] = slug
            break

    # Match comm methods, protocols, power from dict tables
    methods = db.query(DictCommMethod).all()
    for m in methods:
        if m.name.lower() in combined:
            detail = ""
            # Try to extract detail for this method
            detail_patterns = {
                "Ethernet": [r'(\d+×?\s*(?:10[/]100|1000|Gigabit)[Mm][Bb][Pp][Ss])', r'(\d+个.*?网口)'],
                "4G": [r'(LTE\s*CAT\s*\d+)', r'(CAT\d+)'],
                "5G": [r'(5G\s*(?:NR|SA|NSA))'],
                "LoRaWAN": [r'(\d+通道)', r'(CN\d{3})', r'(Class\s*[ABC])'],
            }
            if m.name in detail_patterns:
                for dp in detail_patterns[m.name]:
                    dm = re.search(dp, combined, re.IGNORECASE)
                    if dm:
                        detail = dm.group(1)
                        break
            result["comm_methods"].append({"name": m.name, "details": detail})

    for p in db.query(DictCommProtocol).all():
        if p.name.lower().replace("/", "").replace(" ", "") in combined.replace(" ", "").replace("/", "").lower():
            result["comm_protocols"].append({"name": p.name, "direction": "both"})

    for ps in db.query(DictPowerSupply).all():
        if ps.name.lower() in combined:
            voltage = ""
            volt_match = re.search(r'(\d+(?:[.-]\d+)?\s*[Vv](?:DC)?)', text[:3000])
            if volt_match:
                voltage = volt_match.group(1)
            result["power_supplies"].append({"name": ps.name, "voltage_range": voltage, "battery_life": None})

    # Extract description (first meaningful paragraph)
    paragraphs = [p.strip() for p in text[:3000].split("\n") if len(p.strip()) > 30]
    if paragraphs:
        result["description"] = paragraphs[0][:300]

    # Extract IP rating (case-insensitive since text was lowered)
    ip_match = re.search(r'\b(ip\d{2})\b', combined)
    if ip_match:
        result["specs"]["ip_rating"] = ip_match.group(1).upper()

    # Extract dimensions
    dim_match = re.search(r'(\d{2,4}\s*[×xX]\s*\d{2,4}\s*[×xX]\s*\d{2,4}\s*(?:mm)?)', combined)
    if dim_match:
        result["specs"]["dimensions_mm"] = dim_match.group(1).replace(" ", "")

    # Extract weight
    weight_match = re.search(r'(\d{3,5})\s*g', combined)
    if weight_match:
        result["specs"]["weight_g"] = int(weight_match.group(1))

    return result
