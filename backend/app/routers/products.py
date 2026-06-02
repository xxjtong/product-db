"""Product API routes — v2 schema with dictionary + mapping tables."""
from __future__ import annotations
import json
import os
import re
import subprocess
import tempfile
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import or_
from app.database import get_db
from app.models.product import Product
from app.models.category import Category, CategorySpecDefinition
from app.models.dependency import ProductDependency
from app.models.supplier import Supplier
from app.models.dictionary import Manufacturer
from app.models.mapping import (ProductCommMethod, ProductCommProtocol, ProductPowerSupply,
                                ProductHardwareInterface, ProductSensorCapability, ProductImage)
from app.services.spec_service import validate_specs, compare_products
from app.services.storage import save_upload, delete_file, upload_from_url
from app.services.spec_generator import build_spec_html
from app.services.ai_extract import call_ai_extract, regex_extract_from_text
from app.auth import get_current_user
from app.config import settings
from app.models.user import User
from app.utils.escape import escape_like
from app.schemas.product import (
    ProductCreate, ProductUpdate, AIFetchRequest,
    DownloadImageRequest,
    ProductDependencyCreate, ProductDependencyUpdate,
)
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


# --- URL validation (SSRF prevention) ---

ALLOWED_URL_SCHEMES = {"http", "https"}
BLOCKED_HOSTS = {"169.254.169.254", "localhost", "0.0.0.0", "127.0.0.1", "metadata.google.internal"}


def validate_url(url: str) -> bool:
    """Validate URL scheme and block private/metadata hosts (SSRF prevention)."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        return False
    hostname = (parsed.hostname or "").lower()
    for blocked in BLOCKED_HOSTS:
        if hostname == blocked or hostname.endswith("." + blocked):
            return False
    return True


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
    q = db.query(Product).options(
        selectinload(Product.category),
        selectinload(Product.manufacturer),
        selectinload(Product.supplier),
        selectinload(Product.comm_methods).selectinload(ProductCommMethod.method),
        selectinload(Product.comm_protocols).selectinload(ProductCommProtocol.protocol),
        selectinload(Product.power_supplies).selectinload(ProductPowerSupply.power),
        selectinload(Product.hardware_interfaces),
        selectinload(Product.sensor_capabilities),
        selectinload(Product.images),
    )

    if category_id:
        # Include child categories
        child_cats = db.query(Category).filter_by(parent_id=category_id).all()
        cat_ids = [category_id] + [c.id for c in child_cats]
        q = q.filter(Product.category_id.in_(cat_ids))

    if search:
        search_lower = search.lower()
        q = q.filter(
            or_(
                Product.name.ilike(f"%{escape_like(search)}%"),
                Product.model.ilike(f"%{escape_like(search)}%"),
                Product.sku.ilike(f"%{escape_like(search)}%"),
                Product.pinyin_search.ilike(f"%{escape_like(search_lower)}%"),
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

    product_list = [p.to_dict(cats, sups, mfgs) for p in products]
    # Apply field visibility for non-admin users
    from app.services.field_visibility import filter_fields_for_user
    is_admin = getattr(user, 'role', '') == 'admin'
    for p in product_list:
        filter_fields_for_user(p, is_admin, db)
    return {
        "products": product_list,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/products/compare")
def compare(product_ids: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ids = [int(x) for x in product_ids.split(",") if x.strip().isdigit()]
    if len(ids) < 2:
        raise HTTPException(400, "At least 2 product IDs required")
    products = db.query(Product).options(
        selectinload(Product.category),
        selectinload(Product.manufacturer),
        selectinload(Product.supplier),
        selectinload(Product.comm_methods).selectinload(ProductCommMethod.method),
        selectinload(Product.comm_protocols).selectinload(ProductCommProtocol.protocol),
        selectinload(Product.power_supplies).selectinload(ProductPowerSupply.power),
        selectinload(Product.hardware_interfaces),
        selectinload(Product.sensor_capabilities).selectinload(ProductSensorCapability.metric),
        selectinload(Product.images),
    ).filter(Product.id.in_(ids)).all()
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
    q = db.query(Product).options(
        selectinload(Product.category),
        selectinload(Product.manufacturer),
        selectinload(Product.supplier),
        selectinload(Product.comm_methods).selectinload(ProductCommMethod.method),
        selectinload(Product.comm_protocols).selectinload(ProductCommProtocol.protocol),
        selectinload(Product.power_supplies).selectinload(ProductPowerSupply.power),
    )
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if search:
        q = q.filter(Product.name.ilike(f"%{escape_like(search)}%"))
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

    # Validate file extension
    original_name = file.filename or "upload.jpg"
    ext = os.path.splitext(original_name)[1].lower()
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File extension '{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    # Magic bytes validation
    if len(content) >= 8:
        header = content[:8]
        valid_signatures = [
            b'\xff\xd8\xff',       # JPEG
            b'\x89PNG\r\n\x1a\n',  # PNG
            b'GIF8',               # GIF
            b'RIFF',               # WebP (RIFF container)
            b'BM',                 # BMP
        ]
        if not any(header.startswith(sig) for sig in valid_signatures):
            raise HTTPException(400, "File content does not match a valid image format")
    else:
        raise HTTPException(400, "File too small to be a valid image")

    # Use UUID filename to avoid path traversal
    safe_name = f"{uuid.uuid4().hex[:16]}{ext}"
    url = save_upload(content, safe_name)
    return {"url": url}


@router.post("/products/download-image")
def download_image(data: DownloadImageRequest, user=Depends(get_current_user)):
    """Download image from URL, save locally, return URL."""
    url = data.url.strip()
    if not url:
        raise HTTPException(400, "URL is required")
    if not validate_url(url):
        raise HTTPException(400, "URL not allowed")
    try:
        local_url = upload_from_url(url)
        return {"url": local_url}
    except Exception as e:
        raise HTTPException(400, f"Failed to download image: {e}")


# --- Parameterized routes ---

@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = db.query(Product).options(
        selectinload(Product.category),
        selectinload(Product.manufacturer),
        selectinload(Product.supplier),
        selectinload(Product.comm_methods).selectinload(ProductCommMethod.method),
        selectinload(Product.comm_protocols).selectinload(ProductCommProtocol.protocol),
        selectinload(Product.power_supplies).selectinload(ProductPowerSupply.power),
        selectinload(Product.hardware_interfaces),
        selectinload(Product.sensor_capabilities).selectinload(ProductSensorCapability.metric),
        selectinload(Product.images),
    ).get(product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    p.view_count = (p.view_count or 0) + 1
    db.commit()
    return {"product": _product_detail(p, db)}


@router.post("/products")
def create_product(data: ProductCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Validate specs if category has definitions
    if data.specs and data.category_id:
        spec_defs = db.query(CategorySpecDefinition).filter_by(category_id=data.category_id).all()
        specs = data.specs
        errors = validate_specs(specs, spec_defs)
        if errors:
            raise HTTPException(400, detail={"errors": errors})

    p = Product(
        model=data.model,
        name=data.name,
        sku=data.sku,
        category_id=data.category_id,
        manufacturer_id=data.manufacturer_id,
        supplier_id=data.supplier_id,
        unit=data.unit,
        base_price=data.base_price,
        cost_price=data.cost_price,
        description=data.description,
        image_url=data.image_url,
        product_url=data.product_url,
        status=data.status,
        parent_id=data.parent_id,
        specs=data.specs,
        urls=data.urls,
        custom_fields=data.custom_fields,
    )
    p.pinyin_search = _build_pinyin(f"{p.name} {p.model or ''}")
    p.created_at = datetime.now()
    p.updated_at = datetime.now()

    db.add(p)
    db.flush()  # get p.id

    # Write mapping tables
    _write_mappings(p.id, data.model_dump(exclude_none=True), db)

    db.commit()
    db.refresh(p)
    cats = {c.id: c.name for c in db.query(Category).all()}
    mfgs = {m.id: m.name for m in db.query(Manufacturer).all()}
    sups = {s.id: s.name for s in db.query(Supplier).all()}
    return {"product": p.to_dict(cats, sups, mfgs)}


@router.put("/products/{product_id}")
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")

    # Core fields
    for f in ["model", "name", "sku", "category_id", "manufacturer_id", "supplier_id",
              "unit", "base_price", "cost_price", "description", "image_url", "product_url",
              "status", "parent_id"]:
        val = getattr(data, f, None)
        if val is not None:
            setattr(p, f, val)

    if data.specs:
        p.specs = data.specs
    if data.urls:
        p.urls = data.urls
    if data.custom_fields:
        p.custom_fields = data.custom_fields

    p.pinyin_search = _build_pinyin(f"{p.name} {p.model or ''}")
    p.updated_at = datetime.now()

    # Rewrite mapping tables (delete old, insert new)
    _rewrite_mappings(product_id, data.model_dump(), db)

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


@router.post("/products/ai-fetch")
def ai_fetch_product(data: AIFetchRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """AI-assisted product info extraction from URL or text."""
    url = data.url.strip()
    raw_text = data.text.strip()

    if raw_text:
        # Direct text extraction mode
        result = call_ai_extract("", "", raw_text, db) if settings.AI_GATEWAY_KEY \
            else regex_extract_from_text("", raw_text, db)
        return {"fetched": result}

    if not url:
        raise HTTPException(400, "URL or text is required")

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(400, "Invalid URL")

    if not validate_url(url):
        raise HTTPException(400, "URL not allowed")

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

    result = call_ai_extract(url, title, text, db)

    return {"fetched": {"url": url, "title": title, **result}}


@router.get("/products/{product_id}/spec-sheet")
def spec_sheet(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Generate product spec sheet as PDF download or HTML view."""
    p = db.query(Product).options(
        selectinload(Product.category),
        selectinload(Product.manufacturer),
        selectinload(Product.supplier),
        selectinload(Product.comm_methods).selectinload(ProductCommMethod.method),
        selectinload(Product.comm_protocols).selectinload(ProductCommProtocol.protocol),
        selectinload(Product.power_supplies).selectinload(ProductPowerSupply.power),
        selectinload(Product.hardware_interfaces),
        selectinload(Product.sensor_capabilities).selectinload(ProductSensorCapability.metric),
        selectinload(Product.images),
    ).get(product_id)
    if not p:
        raise HTTPException(404, "Product not found")

    html = build_spec_html(p, db)
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
            env = os.environ.copy()
            env["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib"
            result = subprocess.run(
                [wp, html_path, pdf_path, "-e", "utf-8"],
                env=env, capture_output=True,
            )
            if result.returncode == 0 and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 100:
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
def create_dependency(product_id: int, data: ProductDependencyCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    dep = ProductDependency(
        product_id=product_id,
        depends_on_product_id=data.depends_on_product_id,
        depends_on_category_id=data.depends_on_category_id,
        dependency_type=data.dependency_type,
        description=data.description,
        sort_order=data.sort_order,
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return {"dependency": dep.to_dict()}


@router.put("/products/{product_id}/dependencies/{dep_id}")
def update_dependency(product_id: int, dep_id: int, data: ProductDependencyUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    dep = db.get(ProductDependency, dep_id)
    if not dep or dep.product_id != product_id:
        raise HTTPException(404)
    for f in ["depends_on_product_id", "depends_on_category_id", "dependency_type", "description", "sort_order"]:
        val = getattr(data, f, None)
        if val is not None:
            setattr(dep, f, val)
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
    for cm in (data.get("comm_methods") or []):
        db.add(ProductCommMethod(
            product_id=product_id,
            method_id=cm.get("method_id") if isinstance(cm, dict) else cm,
            details=cm.get("details", "") if isinstance(cm, dict) else "",
        ))

    # Comm protocols
    for cp in (data.get("comm_protocols") or []):
        db.add(ProductCommProtocol(
            product_id=product_id,
            protocol_id=cp.get("protocol_id") if isinstance(cp, dict) else cp,
            direction=cp.get("direction", "both") if isinstance(cp, dict) else "both",
        ))

    # Power supplies
    for ps in (data.get("power_supplies") or []):
        db.add(ProductPowerSupply(
            product_id=product_id,
            power_id=ps.get("power_id") if isinstance(ps, dict) else ps,
            voltage_range=ps.get("voltage_range", "") if isinstance(ps, dict) else "",
            battery_life=ps.get("battery_life", "") if isinstance(ps, dict) else "",
        ))

    # Hardware interfaces
    for hi in (data.get("hardware_interfaces") or []):
        db.add(ProductHardwareInterface(
            product_id=product_id,
            interface_name=hi["interface_name"],
            quantity=hi.get("quantity", 1),
            description=hi.get("description", ""),
        ))

    # Sensor capabilities
    for sc in (data.get("sensor_capabilities") or []):
        db.add(ProductSensorCapability(
            product_id=product_id,
            metric_id=sc.get("metric_id") if isinstance(sc, dict) else sc,
            measure_range=sc.get("measure_range", "") if isinstance(sc, dict) else "",
            accuracy=sc.get("accuracy", "") if isinstance(sc, dict) else "",
            resolution=sc.get("resolution", "") if isinstance(sc, dict) else "",
        ))

    # Images
    for idx, img in enumerate((data.get("images") or [])):
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
