"""AI-assisted product info extraction — shared by routers.

Provides AI extraction (via DeepSeek) and regex fallback for
extracting structured product data from web pages or raw text.
"""
from __future__ import annotations
import json
import re
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.dictionary import (
    Manufacturer, DictCommMethod, DictCommProtocol, DictPowerSupply, DictSensorMetric,
)

# TTL cache for extraction prompt (30s to match field_visibility pattern)
_prompt_cache: dict = {"ts": 0, "value": ""}


def build_extraction_prompt(db: Session) -> str:
    """Build system prompt for product extraction AI (cached 300s)."""
    import time as _time
    now = _time.time()
    if now - _prompt_cache["ts"] < 300:
        return _prompt_cache["value"]

    cats = db.query(Category).filter_by(is_active=True).order_by(Category.sort_order).all()
    cat_info = [f"{c.slug}({c.name})" for c in cats if c.slug]

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

    # Read custom instruction from DB, fall back to default
    from app.models.system_setting import SystemSetting
    instruction = "你是物联网产品信息提取助手。根据网页内容提取产品结构化信息或者下方的产品规格文本，提取所有可用信息，输出为严格 JSON 格式。"
    try:
        s = db.query(SystemSetting).filter_by(key="ai_extract_prompt").first()
        if s and s.value: instruction = s.value
    except Exception: pass

    result = f"""{instruction}

数据库已有数据供参考（提取的值必须来自数据库已有词汇，找不到则用 null）：
品类: {', '.join(cat_info)}
通讯方式: {', '.join(method_names)}
通讯协议: {', '.join(protocol_names)}
供电方式: {', '.join(power_names)}
厂商: {', '.join(manufacturer_names)}
传感器指标: {', '.join(metric_names)}

返回此 JSON 结构（只返回 JSON，无 Markdown 包裹）:
{{
  "name": "产品名称",
  "model": "产品型号",
  "category_slug": "品类slug(从上述列表选)",
  "manufacturer_name": "厂商(从列表选, 否则null)",
  "description": "产品描述(保留关键技术参数, 1-3句)",
  "base_price": "价格数字或null",
  "comm_methods": [{{"name": "Ethernet", "details": "端口数和速率"}}],
  "comm_protocols": [{{"name": "MQTT", "direction": "both"}}],
  "power_supplies": [{{"name": "DC", "voltage_range": "9-24V", "battery_life": null}}],
  "hardware_interfaces": [{{"interface_name": "RS485", "quantity": 1, "description": ""}}],
  "sensor_capabilities": [{{"metric_name": "温度", "measure_range": "-30~70", "accuracy": "±0.2", "resolution": "0.1"}}],
  "specs": {{"防护等级": "IP67", "尺寸": "240×164×90.9mm", "重量": "500g"}}
}}

规则:
- name/model/description/specs 从文本中提取实际值
- comm_methods/protocols/power_supplies/sensor_capabilities 的 name 必须来自上述数据库列表
- 文本没提到的字段设 null 或空数组
- specs 内的 key 必须使用中文命名（防护等级/尺寸/重量/材质/工作温度/安装方式等），禁止使用英文 key
- specs 值带单位(如 "240×164×90.9mm", "500g")"""

    _prompt_cache["value"] = result
    _prompt_cache["ts"] = now
    return result


def call_ai_extract(url: str, title: str, text: str, db: Session, _usage: list = None) -> dict:
    """Call AI (DeepSeek) to extract product info from text.

    Falls back to regex extraction if no API key or on error.
    If _usage list is provided, [tokens_in, tokens_out] is appended on success.
    """
    import asyncio, time as _time
    from app.services.ai_engine import engine

    if not engine.api_key:
        return regex_extract_from_text(title, text, db)

    system_prompt = build_extraction_prompt(db)
    user_msg = f"""来源: {title or url or '文件'}

规格文本:
{text[:12000]}

请提取产品的结构化信息。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    try:
        t0 = _time.time()
        result = asyncio.run(engine.chat(messages, temperature=0.1, max_tokens=3000))
        elapsed_ms = int((_time.time() - t0) * 1000)
        usage = result.get("usage", {})
        if _usage is not None:
            _usage.append(usage.get("prompt_tokens", 0))
            _usage.append(usage.get("completion_tokens", 0))
            _usage.append(elapsed_ms)
        content = result["choices"][0]["message"]["content"]
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return regex_extract_from_text(title, text, db)
    except Exception as e:
        import logging; logging.getLogger("uvicorn").warning(f"AI extraction failed, using regex fallback: {e}")
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
        result["specs"]["防护等级"] = ip_match.group(1).upper()

    # Extract dimensions
    dim_match = re.search(r'(\d{2,4}\s*[×xX]\s*\d{2,4}\s*[×xX]\s*\d{2,4}\s*(?:mm)?)', combined)
    if dim_match:
        result["specs"]["尺寸"] = dim_match.group(1).replace(" ", "")

    # Extract weight
    weight_match = re.search(r'(\d{3,5})\s*g', combined)
    if weight_match:
        result["specs"]["重量"] = f"{int(weight_match.group(1))}g"

    return result
