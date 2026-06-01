"""Product API routes — v2 schema with dictionary + mapping tables."""
from __future__ import annotations
import json
import os
import re
import subprocess
import tempfile
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from app.database import get_db
from app.models.product import Product
from app.models.category import Category, CategorySpecDefinition
from app.models.dependency import ProductDependency
from app.models.supplier import Supplier
from app.models.dictionary import Manufacturer, DictCommMethod, DictCommProtocol, DictPowerSupply, DictSensorMetric
from app.models.mapping import (ProductCommMethod, ProductCommProtocol, ProductPowerSupply,
                                ProductHardwareInterface, ProductSensorCapability, ProductImage)
from app.services.spec_service import validate_specs, compare_products
from app.services.storage import save_upload, delete_file, upload_from_url
from app.auth import get_current_user
from app.config import settings
from app.models.user import User
import openpyxl
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from io import BytesIO
from pypinyin import lazy_pinyin
from datetime import datetime

router = APIRouter()


def _build_pinyin(text: str) -> str:
    if not text:
        return ""
    return "".join(lazy_pinyin(text)).lower()


# --- Helper: build product response with all mappings ---

def _product_detail(p: Product, db: Session) -> dict:
    """Build full product dict with mappings, images, spec_definitions, dependencies."""
    result = p.to_dict()

    # Spec definitions
    spec_defs = db.query(CategorySpecDefinition).filter_by(category_id=p.category_id)\
        .order_by(CategorySpecDefinition.sort_order).all()
    result["spec_definitions"] = [sd.to_dict() for sd in spec_defs]

    # Variants
    if p.parent_id is None:
        variants = db.query(Product).filter(Product.parent_id == p.id).all()
        if variants:
            cats = {c.id: c.name for c in db.query(Category).all()}
            mfgs = {m.id: m.name for m in db.query(Manufacturer).all()}
            sups = {s.id: s.name for s in db.query(Supplier).all()}
            result["variants"] = [v.to_dict(cats, sups, mfgs) for v in variants]

    # Dependencies
    deps = db.query(ProductDependency).filter_by(product_id=p.id).all()
    result["dependencies"] = [d.to_dict() for d in deps]

    return result


# --- Static routes (must be before {product_id}) ---

@router.get("/products")
def list_products(
    category_id: Optional[int] = None,
    search: str = "",
    parent_id: Optional[int] = Query(None),
    comm_method: Optional[int] = Query(None, description="Filter by comm method dict ID"),
    comm_protocol: Optional[int] = Query(None, description="Filter by protocol dict ID"),
    power_supply: Optional[int] = Query(None, description="Filter by power supply dict ID"),
    manufacturer_id: Optional[int] = None,
    status: str = "active",
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    q = db.query(Product)

    if category_id:
        # Include child categories
        child_cats = db.query(Category).filter_by(parent_id=category_id).all()
        cat_ids = [category_id] + [c.id for c in child_cats]
        q = q.filter(Product.category_id.in_(cat_ids))

    if search:
        search_lower = search.lower()
        q = q.filter(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.model.ilike(f"%{search}%"),
                Product.sku.ilike(f"%{search}%"),
                Product.pinyin_search.ilike(f"%{search_lower}%"),
            )
        )

    if parent_id is not None:
        if parent_id == 0:
            q = q.filter(Product.parent_id.is_(None))
        else:
            q = q.filter(Product.parent_id == parent_id)

    if status:
        q = q.filter(Product.status == status)

    if manufacturer_id:
        q = q.filter(Product.manufacturer_id == manufacturer_id)

    # Mapping table filters
    if comm_method:
        q = q.filter(Product.comm_methods.any(ProductCommMethod.method_id == comm_method))
    if comm_protocol:
        q = q.filter(Product.comm_protocols.any(ProductCommProtocol.protocol_id == comm_protocol))
    if power_supply:
        q = q.filter(Product.power_supplies.any(ProductPowerSupply.power_id == power_supply))

    total = q.count()
    products = q.order_by(Product.name).offset((page - 1) * per_page).limit(per_page).all()

    cats = {c.id: c.name for c in db.query(Category).all()}
    mfgs = {m.id: m.name for m in db.query(Manufacturer).all()}
    sups = {s.id: s.name for s in db.query(Supplier).all()}

    return {
        "products": [p.to_dict(cats, sups, mfgs) for p in products],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/products/compare")
def compare(product_ids: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ids = [int(x) for x in product_ids.split(",") if x.strip().isdigit()]
    if len(ids) < 2:
        raise HTTPException(400, "At least 2 product IDs required")
    products = db.query(Product).filter(Product.id.in_(ids)).all()
    if len(products) < 2:
        raise HTTPException(404, "Products not found")

    matrix = compare_products(products)
    product_data = {
        p.id: {
            "id": p.id,
            "name": p.name,
            "model": p.model or "",
            "sku": p.sku or "",
            "manufacturer_name": p.manufacturer.name if p.manufacturer else "",
            "category_name": p.category.name if p.category else "",
        }
        for p in products
    }

    categories = set(p.category_id for p in products)
    spec_defs = db.query(CategorySpecDefinition).filter(
        CategorySpecDefinition.category_id.in_(categories)
    ).all()
    display_map = {sd.spec_key: sd.display_name for sd in spec_defs}

    return {
        "products": product_data,
        "matrix": matrix,
        "display_names": display_map,
    }


@router.get("/products/export")
def export_products(
    category_id: Optional[int] = None, search: str = "",
    db: Session = Depends(get_db), user=Depends(get_current_user),
):
    q = db.query(Product)
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if search:
        q = q.filter(Product.name.ilike(f"%{search}%"))
    products = q.order_by(Product.name).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "产品列表"
    headers = ["ID", "型号", "名称", "品类", "厂商", "通讯方式", "协议", "供电", "规格(JSON)"]
    ws.append(headers)

    for p in products:
        comm = ", ".join(cm.method.name for cm in p.comm_methods if cm.method)
        proto = ", ".join(cp.protocol.name for cp in p.comm_protocols if cp.protocol)
        power = ", ".join(ps.power.name for ps in p.power_supplies if ps.power)
        ws.append([
            p.id, p.model or "", p.name,
            p.category.name if p.category else "",
            p.manufacturer.name if p.manufacturer else "",
            comm, proto, power,
            json.dumps(p.specs or {}, ensure_ascii=False),
        ])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''products.xlsx"},
    )


@router.post("/products/upload-image")
def upload_image(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload an image file, return URL."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    content = file.file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image must be under 5MB")
    url = save_upload(content, file.filename or "upload.jpg")
    return {"url": url}


@router.post("/products/download-image")
def download_image(data: dict, user=Depends(get_current_user)):
    """Download image from URL, save locally, return URL."""
    url = data.get("url", "").strip()
    if not url:
        raise HTTPException(400, "URL is required")
    try:
        local_url = upload_from_url(url)
        return {"url": local_url}
    except Exception as e:
        raise HTTPException(400, f"Failed to download image: {e}")


# --- Parameterized routes ---

@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    return {"product": _product_detail(p, db)}


@router.post("/products")
def create_product(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Validate specs if category has definitions
    if "specs" in data and "category_id" in data:
        spec_defs = db.query(CategorySpecDefinition).filter_by(category_id=data["category_id"]).all()
        specs = data["specs"] if isinstance(data["specs"], dict) else json.loads(data["specs"])
        errors = validate_specs(specs, spec_defs)
        if errors:
            raise HTTPException(400, detail={"errors": errors})

    p = Product(
        model=data.get("model", ""),
        name=data["name"],
        sku=data.get("sku", ""),
        category_id=data["category_id"],
        manufacturer_id=data.get("manufacturer_id"),
        supplier_id=data.get("supplier_id"),
        unit=data.get("unit", "台"),
        base_price=data.get("base_price"),
        cost_price=data.get("cost_price"),
        description=data.get("description", ""),
        image_url=data.get("image_url", ""),
        product_url=data.get("product_url", ""),
        status=data.get("status", "active"),
        parent_id=data.get("parent_id"),
        specs=data.get("specs", {}),
        urls=data.get("urls", {}),
        custom_fields=data.get("custom_fields", {}),
    )
    p.pinyin_search = _build_pinyin(f"{p.name} {p.model or ''}")
    p.created_at = datetime.now()
    p.updated_at = datetime.now()

    db.add(p)
    db.flush()  # get p.id

    # Write mapping tables
    _write_mappings(p.id, data, db)

    db.commit()
    db.refresh(p)
    cats = {c.id: c.name for c in db.query(Category).all()}
    mfgs = {m.id: m.name for m in db.query(Manufacturer).all()}
    sups = {s.id: s.name for s in db.query(Supplier).all()}
    return {"product": p.to_dict(cats, sups, mfgs)}


@router.put("/products/{product_id}")
def update_product(product_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")

    # Core fields
    for f in ["model", "name", "sku", "category_id", "manufacturer_id", "supplier_id",
              "unit", "base_price", "cost_price", "description", "image_url", "product_url",
              "status", "parent_id"]:
        if f in data:
            setattr(p, f, data[f])

    if "specs" in data:
        p.specs = data["specs"] if isinstance(data["specs"], dict) else json.loads(data["specs"])
    if "urls" in data:
        p.urls = data["urls"]
    if "custom_fields" in data:
        p.custom_fields = data["custom_fields"]

    p.pinyin_search = _build_pinyin(f"{p.name} {p.model or ''}")
    p.updated_at = datetime.now()

    # Rewrite mapping tables (delete old, insert new)
    _rewrite_mappings(product_id, data, db)

    db.commit()
    cats = {c.id: c.name for c in db.query(Category).all()}
    mfgs = {m.id: m.name for m in db.query(Manufacturer).all()}
    sups = {s.id: s.name for s in db.query(Supplier).all()}
    return {"product": p.to_dict(cats, sups, mfgs)}


@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    db.delete(p)
    db.commit()
    return {"ok": True}


# --- AI-assisted URL fetch ---

def _build_extraction_prompt(db: Session) -> str:
    """Build AI system prompt for product info extraction from web pages."""
    from app.models.category import Category as Cat, CategorySpecDefinition as SpecDef

    cats = db.query(Cat).filter_by(is_active=True).order_by(Cat.sort_order).all()
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

提取以下信息（未知字段设为 null 或空）:
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


def _call_ai_extract(url: str, title: str, text: str, db: Session) -> dict:
    """Call AI (DeepSeek via Gateway or direct) to extract product info from text."""
    system_prompt = _build_extraction_prompt(db)
    user_msg = f"""网页标题: {title}
网页URL: {url}

网页内容:
{text[:6000]}

请提取该产品的结构化信息。"""

    # Use direct DeepSeek API if no gateway configured
    if not settings.AI_GATEWAY_URL or not settings.AI_GATEWAY_KEY:
        return _regex_extract_from_text(title, text, db)

    payload = {
        "model": "deepseek",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }

    try:
        if "/v1" in settings.AI_GATEWAY_URL:
            resp = httpx.post(
                f"{settings.AI_GATEWAY_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.AI_GATEWAY_KEY}"},
                timeout=60,
            )
        else:
            resp = httpx.post(
                settings.AI_GATEWAY_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.AI_GATEWAY_KEY}"},
                timeout=60,
            )

        if resp.status_code != 200:
            return _regex_extract_from_text(title, text, db)

        content = resp.json()["choices"][0]["message"]["content"]
        # Extract JSON from response (in case AI wraps it in markdown)
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


@router.post("/products/ai-fetch")
def ai_fetch_product(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """AI-assisted product info extraction from URL or text."""
    url = (data.get("url") or "").strip()
    raw_text = (data.get("text") or "").strip()

    if raw_text:
        # Direct text extraction mode
        result = _call_ai_extract("", "", raw_text, db) if (settings.AI_GATEWAY_URL and settings.AI_GATEWAY_KEY) \
            else _regex_extract_from_text("", raw_text, db)
        return {"fetched": result}

    if not url:
        raise HTTPException(400, "URL or text is required")

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(400, "Invalid URL")

    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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

def _build_spec_html(p, db: Session) -> str:
    """Build complete HTML for product spec sheet."""
    spec_defs = db.query(CategorySpecDefinition).filter_by(category_id=p.category_id)\
        .order_by(CategorySpecDefinition.sort_order).all()

    groups: dict = {}
    for sd in spec_defs:
        g = sd.display_group or "基本参数"
        if g not in groups:
            groups[g] = []
        groups[g].append(sd)

    defined_keys = {sd.spec_key for sd in spec_defs}
    unmatched = {k: v for k, v in (p.specs or {}).items() if k not in defined_keys}

    # Product image HTML
    img_html = ""
    primary_img = next((img for img in p.images if img.is_primary), None)
    if primary_img:
        img_url = primary_img.url
        if not img_url.startswith("http"):
            img_url = f"file://{os.path.dirname(__file__)}/../../{img_url.lstrip('/')}"
        img_html = f'<img src="{img_url}" class="product-img" />'

    # Comm methods
    comm_rows = ""
    for cm in p.comm_methods:
        if cm.method:
            mtype = "有线" if cm.method.method_type == "wired" else "无线"
            comm_rows += f"<tr><td>{mtype}</td><td>{cm.method.name}</td><td>{cm.details or '—'}</td></tr>"

    # Protocols
    proto_rows = ""
    for cp in p.comm_protocols:
        if cp.protocol:
            proto_rows += f"<tr><td>{cp.protocol.name}</td><td>{'双向' if cp.direction == 'both' else '采集' if cp.direction == 'acquisition' else '转发'}</td></tr>"

    # Power
    power_rows = ""
    for ps in p.power_supplies:
        if ps.power:
            power_rows += f"<tr><td>{ps.power.name}</td><td>{ps.voltage_range or '—'}</td><td>{ps.battery_life or '—'}</td></tr>"

    # Hardware interfaces
    iface_rows = ""
    for hi in p.hardware_interfaces:
        iface_rows += f"<tr><td>{hi.interface_name}</td><td>×{hi.quantity}</td><td>{hi.description or '—'}</td></tr>"

    # Sensor capabilities
    sensor_rows = ""
    for sc in p.sensor_capabilities:
        if sc.metric:
            sensor_rows += f"<tr><td>{sc.metric.name} ({sc.metric.unit or ''})</td><td>{sc.measure_range or '—'}</td><td>{sc.accuracy or '—'}</td><td>{sc.resolution or '—'}</td></tr>"

    # Spec groups
    spec_group_html = ""
    for group_name, items in groups.items():
        rows = ""
        for sd in items:
            val = (p.specs or {}).get(sd.spec_key)
            if val is None:
                val_str = "—"
            elif sd.spec_type == "boolean":
                val_str = "✓" if val else "—"
            else:
                val_str = str(val)
                if sd.unit:
                    val_str += f" {sd.unit}"
            rows += f"<tr><td>{sd.display_name}</td><td>{val_str}</td></tr>"
        spec_group_html += f"""<h2>{group_name}</h2>
<table>{rows}</table>"""

    unmatched_rows = ""
    if unmatched:
        for k, v in unmatched.items():
            unmatched_rows += f"<tr><td>{k}</td><td>{v}</td></tr>"

    desc_html = f"<h2>描述</h2><p>{p.description}</p>" if p.description else ""
    base_info = f"<p>{p.manufacturer.name if p.manufacturer else ''} | {p.category.name if p.category else ''} | 型号: {p.model or '—'}</p>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>{p.name} - 规格书</title>
<style>
@page {{ size: A4; margin: 20mm 18mm; @bottom-center {{ content: "第 " counter(page) " 页"; font-size: 9px; color: #94a3b8; }} }}
body {{ font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei", sans-serif; font-size: 12px; color: #1e293b; line-height: 1.6; }}
.header {{ border-bottom: 3px solid #0f3460; padding-bottom: 12px; margin-bottom: 20px; }}
.header h1 {{ font-size: 22px; margin: 0 0 4px; color: #0f3460; }}
.header p {{ font-size: 12px; color: #64748b; margin: 2px 0; }}
h2 {{ font-size: 14px; color: #0f3460; margin: 20px 0 8px; padding: 4px 0 4px 10px; border-left: 4px solid #0f3460; background: #f8fafc; page-break-after: avoid; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 11px; page-break-inside: avoid; }}
th {{ background: #f1f5f9; padding: 6px 10px; text-align: left; font-weight: 600; border-bottom: 2px solid #cbd5e1; }}
td {{ padding: 5px 10px; border-bottom: 1px solid #e2e8f0; }}
td:first-child {{ color: #475569; width: 160px; }}
.badge {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; margin: 1px 2px; background: #f1f5f9; border: 1px solid #e2e8f0; }}
.product-img {{ max-width: 120px; max-height: 120px; float: right; border-radius: 6px; border: 1px solid #e2e8f0; margin-left: 16px; }}
.footer {{ margin-top: 24px; padding-top: 12px; border-top: 1px solid #e2e8f0; font-size: 10px; color: #94a3b8; text-align: center; }}
</style></head>
<body>
<div class="header">
  {img_html}
  <h1>{p.name}</h1>
  {base_info}
</div>
<h2>通讯方式</h2>
<table><tr><th>类型</th><th>方式</th><th>详情</th></tr>{comm_rows or '<tr><td colspan="3">—</td></tr>'}</table>

<h2>通讯协议</h2>
<table><tr><th>协议</th><th>方向</th></tr>{proto_rows or '<tr><td colspan="2">—</td></tr>'}</table>

<h2>供电方式</h2>
<table><tr><th>方式</th><th>电压/规格</th><th>续航</th></tr>{power_rows or '<tr><td colspan="3">—</td></tr>'}</table>

{"<h2>硬件接口</h2><table><tr><th>接口</th><th>数量</th><th>描述</th></tr>" + iface_rows + "</table>" if iface_rows else ""}

{"<h2>传感能力</h2><table><tr><th>指标</th><th>量程</th><th>精度</th><th>分辨率</th></tr>" + sensor_rows + "</table>" if sensor_rows else ""}

{spec_group_html}

{"<h2>其他参数</h2><table>" + unmatched_rows + "</table>" if unmatched_rows else ""}

{desc_html}

<div class="footer">© 产品数据库 — 生成于 {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
</body></html>"""


@router.get("/products/{product_id}/spec-sheet")
def spec_sheet(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Generate product spec sheet as PDF download or HTML view."""
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")

    html = _build_spec_html(p, db)
    filename = re.sub(r'[^\w\-_.]', '_', p.name or 'product')

    # Try CLI weasyprint for PDF (brew-installed at /opt/homebrew/bin/weasyprint)
    html_path = f"/tmp/_spec_{product_id}.html"
    pdf_path = f"/tmp/_spec_{product_id}.pdf"
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        import shutil
        wp = "/opt/homebrew/bin/weasyprint" if os.path.exists("/opt/homebrew/bin/weasyprint") else shutil.which("weasyprint")
        if wp:
            rc = os.system(f'DYLD_LIBRARY_PATH=/opt/homebrew/lib {wp} "{html_path}" "{pdf_path}" -e utf-8 2>/dev/null')
            if rc == 0 and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 100:
                with open(pdf_path, "rb") as f2:
                    pdf_bytes = f2.read()
                os.unlink(pdf_path)
                return StreamingResponse(
                    BytesIO(pdf_bytes),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}-spec-sheet.pdf"},
                )
    except Exception:
        pass

    return HTMLResponse(content=html)


# --- Dependencies ---

@router.get("/products/{product_id}/dependencies")
def get_dependencies(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    deps = db.query(ProductDependency).filter_by(product_id=product_id).all()
    return {"dependencies": [d.to_dict() for d in deps]}


@router.post("/products/{product_id}/dependencies")
def create_dependency(product_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    dep = ProductDependency(
        product_id=product_id,
        depends_on_product_id=data.get("depends_on_product_id"),
        depends_on_category_id=data.get("depends_on_category_id"),
        dependency_type=data.get("dependency_type", "required"),
        description=data.get("description"),
        sort_order=data.get("sort_order", 0),
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return {"dependency": dep.to_dict()}


@router.put("/products/{product_id}/dependencies/{dep_id}")
def update_dependency(product_id: int, dep_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    dep = db.get(ProductDependency, dep_id)
    if not dep or dep.product_id != product_id:
        raise HTTPException(404)
    for f in ["depends_on_product_id", "depends_on_category_id", "dependency_type", "description", "sort_order"]:
        if f in data:
            setattr(dep, f, data[f])
    db.commit()
    return {"dependency": dep.to_dict()}


@router.delete("/products/{product_id}/dependencies/{dep_id}")
def delete_dependency(product_id: int, dep_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    dep = db.get(ProductDependency, dep_id)
    if not dep or dep.product_id != product_id:
        raise HTTPException(404)
    db.delete(dep)
    db.commit()
    return {"ok": True}


# --- Mapping helpers ---

def _write_mappings(product_id: int, data: dict, db: Session):
    """Write mapping tables for a product (create only)."""
    # Comm methods
    for cm in data.get("comm_methods", []):
        db.add(ProductCommMethod(
            product_id=product_id,
            method_id=cm.get("method_id") if isinstance(cm, dict) else cm,
            details=cm.get("details", "") if isinstance(cm, dict) else "",
        ))

    # Comm protocols
    for cp in data.get("comm_protocols", []):
        db.add(ProductCommProtocol(
            product_id=product_id,
            protocol_id=cp.get("protocol_id") if isinstance(cp, dict) else cp,
            direction=cp.get("direction", "both") if isinstance(cp, dict) else "both",
        ))

    # Power supplies
    for ps in data.get("power_supplies", []):
        db.add(ProductPowerSupply(
            product_id=product_id,
            power_id=ps.get("power_id") if isinstance(ps, dict) else ps,
            voltage_range=ps.get("voltage_range", "") if isinstance(ps, dict) else "",
            battery_life=ps.get("battery_life", "") if isinstance(ps, dict) else "",
        ))

    # Hardware interfaces
    for hi in data.get("hardware_interfaces", []):
        db.add(ProductHardwareInterface(
            product_id=product_id,
            interface_name=hi["interface_name"],
            quantity=hi.get("quantity", 1),
            description=hi.get("description", ""),
        ))

    # Sensor capabilities
    for sc in data.get("sensor_capabilities", []):
        db.add(ProductSensorCapability(
            product_id=product_id,
            metric_id=sc.get("metric_id") if isinstance(sc, dict) else sc,
            measure_range=sc.get("measure_range", "") if isinstance(sc, dict) else "",
            accuracy=sc.get("accuracy", "") if isinstance(sc, dict) else "",
            resolution=sc.get("resolution", "") if isinstance(sc, dict) else "",
        ))

    # Images
    for idx, img in enumerate(data.get("images", [])):
        db.add(ProductImage(
            product_id=product_id,
            url=img.get("url", "") if isinstance(img, dict) else img,
            is_primary=img.get("is_primary", idx == 0) if isinstance(img, dict) else (idx == 0),
            sort_order=img.get("sort_order", idx) if isinstance(img, dict) else idx,
            alt_text=img.get("alt_text", "") if isinstance(img, dict) else "",
        ))


def _rewrite_mappings(product_id: int, data: dict, db: Session):
    """Delete old mappings and write new ones."""
    db.query(ProductCommMethod).filter_by(product_id=product_id).delete()
    db.query(ProductCommProtocol).filter_by(product_id=product_id).delete()
    db.query(ProductPowerSupply).filter_by(product_id=product_id).delete()
    db.query(ProductHardwareInterface).filter_by(product_id=product_id).delete()
    db.query(ProductSensorCapability).filter_by(product_id=product_id).delete()
    db.query(ProductImage).filter_by(product_id=product_id).delete()
    _write_mappings(product_id, data, db)
