"""Product spec sheet — HTML/PDF generation and AI content extraction."""
from __future__ import annotations
import json
import os
import re
import subprocess
import shutil
import tempfile
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.product import Product
from app.models.category import Category, CategorySpecDefinition
from app.models.dictionary import Manufacturer, DictCommMethod, DictCommProtocol, DictPowerSupply, DictSensorMetric
from app.auth import get_current_user
from app.config import settings
import httpx
from bs4 import BeautifulSoup

router = APIRouter()

# ─── Spec sheet generator ──────────────────────────────────────────


def _build_spec_html(p, db: Session) -> str:
    """Build complete HTML for product spec sheet."""
    spec_defs = db.query(CategorySpecDefinition).filter_by(category_id=p.category_id) \
        .order_by(CategorySpecDefinition.sort_order).all()

    groups: dict = {}
    for sd in spec_defs:
        g = sd.display_group or "基本参数"
        if g not in groups:
            groups[g] = []
        spec_val = (p.specs or {}).get(sd.spec_key)
        if spec_val is not None:
            groups[g].append((sd.display_name, spec_val, sd.unit or ""))

    cat = db.get(Category, p.category_id) if p.category_id else None
    mfg = db.get(Manufacturer, p.manufacturer_id) if p.manufacturer_id else None

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
body {{ font-family: 'Noto Sans SC', Inter, sans-serif; padding: 40px; max-width: 800px; margin: auto; }}
h1 {{ font-size: 20px; margin-bottom: 4px; }}
.spec-group {{ margin: 16px 0; }}
.spec-group h3 {{ font-size: 14px; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-bottom: 8px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
td {{ padding: 4px 8px; border: 1px solid #eee; }}
td:first-child {{ width: 180px; color: #666; }}
</style></head><body>
<h1>{p.name}</h1>
<p>{p.model or ""} | {cat.name if cat else ""} | {mfg.name if mfg else p.manufacturer.name if hasattr(p, 'manufacturer') and p.manufacturer else ""}</p>
"""
    for group_name, specs in groups.items():
        html += f'<div class="spec-group"><h3>{group_name}</h3><table>'
        for name, val, unit in specs:
            unit_str = f" {unit}" if unit else ""
            html += f"<tr><td>{name}</td><td>{val}{unit_str}</td></tr>"
        html += "</table></div>"

    html += "</body></html>"
    return html


@router.get("/products/{product_id}/spec-sheet")
def spec_sheet(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Generate product spec sheet (HTML or PDF)."""
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    html_content = _build_spec_html(p, db)
    return HTMLResponse(content=html_content)


# ─── AI product extraction ─────────────────────────────────────────


def _build_extraction_prompt(db: Session) -> str:
    """Build system prompt for product extraction AI."""
    cats = db.query(Category).filter_by(is_active=True).order_by(Category.sort_order).all()
    cat_info = "\n".join(f"  - {c.name} (slug: {c.slug or ''})" for c in cats)

    comm_methods = db.query(DictCommMethod).all()
    comm_method_names = [cm.name for cm in comm_methods]

    comm_protocols = db.query(DictCommProtocol).all()
    protocol_names = [cp.name for cp in comm_protocols]

    power_types = db.query(DictPowerSupply).all()
    power_names = [ps.name for ps in power_types]

    manufacturers = db.query(Manufacturer).order_by(Manufacturer.name).all()
    mfg_names = [m.name for m in manufacturers]

    sensor_metrics = db.query(DictSensorMetric).all()
    sensor_names = [sm.name for sm in sensor_metrics]

    return f"""你是一个物联网产品数据录入助手。从网页内容中提取产品信息，返回如下JSON格式。

重要规则:
- 只提取可以确定的信息，不确定的不要猜测
- 品类必须严格从可选的品类列表中选择一个，不能自创
- 通讯方式/协议/供电方式 中的名称字段必须从可选值中匹配
- 传感器检测指标中的 metric 字段必须从可选值中匹配
- 返回一个JSON对象，不要包含其他解释文字

品类列表:
{cat_info}

通讯方式可选值: {', '.join(comm_method_names)}
协议可选值: {', '.join(protocol_names)}
供电方式可选值: {', '.join(power_names)}
厂商可选值: {', '.join(mfg_names)}
传感器检测指标可选值: {', '.join(sensor_names)}

JSON格式:
{{
  "name": "产品名称",
  "model": "产品型号",
  "category_slug": "对应的品类slug",
  "manufacturer_name": "厂商名称（从列表匹配）",
  "description": "产品简要描述",
  "base_price": 价格数字或null,
  "comm_methods": [{{"name": "通讯方式名"}}],
  "comm_protocols": [{{"name": "协议名", "direction": "acquisition/forwarding/both"}}],
  "power_supplies": [{{"name": "供电方式名"}}],
  "hardware_interfaces": [{{"interface_name": "接口名", "quantity": 1, "description": "备注"}}],
  "sensor_capabilities": [{{"metric": "检测指标名", "measure_range": "测量范围", "accuracy": "精度", "resolution": "分辨率"}}],
  "specs": {{"spec_key": "值"}}
}}"""


def _call_ai_extract(url: str, title: str, text: str, db: Session) -> dict:
    """Call AI (DeepSeek) to extract product info from text."""
    from app.services.ai_engine import engine

    if not settings.AI_GATEWAY_KEY:
        return _regex_extract_from_text(title, text, db)

    system_prompt = _build_extraction_prompt(db)
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
        return _regex_extract_from_text(title, text, db)
    except Exception:
        return _regex_extract_from_text(title, text, db)


def _regex_extract_from_text(title: str, text: str, db: Session) -> dict:
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

    model_patterns = [
        r'\b([A-Z]{2,6}[-]?\d{2,4}(?:[-][A-Z]{1,4})?)\b',
        r'\b([A-Z]{1,2}\d{4}[A-Z]?(?:[-][A-Z]+)?)\b',
    ]
    for pat in model_patterns:
        m = re.search(pat, title + " " + text[:500])
        if m:
            result["model"] = m.group(1)
            break

    result["name"] = title or result["model"] or "Untitled"

    cats = db.query(Category).filter_by(is_active=True).order_by(Category.sort_order).all()
    cat_terms = [
        ("lorawan-gateway", ["gateway", "网关", "lora gateway", "lorawan gateway"]),
        ("lorawan-sensor", ["sensor", "传感器", "温度", "湿度", "co2"]),
        ("industrial-router", ["router", "路由器"]),
        ("conference-display", ["会议", "显示屏", "display"]),
        ("visitor-kiosk", ["访客机", "visitor"]),
    ]
    for slug, terms in cat_terms:
        if any(t in (title + text[:2000]).lower() for t in terms):
            result["category_slug"] = slug
            break

    mfgs = db.query(Manufacturer).order_by(Manufacturer.name).all()
    for mfg in mfgs:
        if mfg.name.lower() in (title + text[:1000]).lower():
            result["manufacturer_name"] = mfg.name
            break

    desc_match = re.search(r'((?:.{10,200}\.)\s)', text[:3000])
    if desc_match:
        result["description"] = desc_match.group(1).strip()

    # Comm methods
    comm_methods = db.query(DictCommMethod).all()
    for cm in comm_methods:
        if cm.name.lower() in text[:3000].lower():
            result["comm_methods"].append({"name": cm.name})

    # Protocols
    protocols = db.query(DictCommProtocol).all()
    for p in protocols:
        if p.name.lower() in text[:3000].lower():
            result["comm_protocols"].append({"name": p.name})

    # Power supplies
    powers = db.query(DictPowerSupply).all()
    for ps in powers:
        if ps.name.lower() in text[:3000].lower():
            result["power_supplies"].append({"name": ps.name})

    price_match = re.search(r'[¥￥]\s*(\d+(?:[.,]\d+)?)', text[:3000])
    if price_match:
        result["base_price"] = float(price_match.group(1).replace(",", ""))

    return result


@router.post("/products/ai-fetch")
def ai_fetch_product(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """AI-assisted product info extraction from URL or text."""
    url = (data.get("url") or "").strip()
    raw_text = (data.get("text") or "").strip()

    if raw_text:
        result = _call_ai_extract("", "", raw_text, db) if settings.AI_GATEWAY_KEY \
            else _regex_extract_from_text("", raw_text, db)
        return {"fetched": result}

    if not url:
        raise HTTPException(400, "URL or text is required")

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(400, "Invalid URL")

    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(400, f"Failed to fetch URL: {str(e)}")

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "path"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title else ""
    body = soup.body
    text = body.get_text(separator="\n", strip=True) if body else resp.text
    text = re.sub(r'\n{3,}', '\n\n', text)[:8000]

    if not text:
        raise HTTPException(400, "No text content extracted from URL")

    result = _call_ai_extract(url, title, text, db)
    return {"fetched": {"url": url, "title": title, **result}}
