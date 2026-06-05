"""Product helper functions — eager loading, name resolution, mappings, pinyin."""
from __future__ import annotations
from sqlalchemy.orm import Session, selectinload
from app.models.product import Product
from app.models.category import Category, CategorySpecDefinition
from app.models.dictionary import Manufacturer
from app.models.supplier import Supplier
from app.models.dependency import ProductDependency
from app.models.mapping import (
    ProductCommMethod, ProductCommProtocol, ProductPowerSupply,
    ProductHardwareInterface, ProductSensorCapability, ProductImage,
)
from pypinyin import lazy_pinyin

# TTL cache for name resolution maps (30s)
_name_cache: dict = {"ts": 0, "cats": {}, "mfgs": {}, "sups": {}}


def build_pinyin(text: str) -> str:
    if not text:
        return ""
    return "".join(lazy_pinyin(text)).lower()


def get_name_maps(db: Session):
    """Return (category_map, mfg_map, supplier_map) with 30s TTL cache."""
    import time as _time
    now = _time.time()
    if now - _name_cache["ts"] < 30:
        return _name_cache["cats"], _name_cache["mfgs"], _name_cache["sups"]
    _name_cache["cats"] = {c.id: c.name for c in db.query(Category).all()}
    _name_cache["mfgs"] = {m.id: m.name for m in db.query(Manufacturer).all()}
    _name_cache["sups"] = {s.id: s.name for s in db.query(Supplier).all()}
    _name_cache["ts"] = now
    return _name_cache["cats"], _name_cache["mfgs"], _name_cache["sups"]


def product_eager_loads():
    """Return standard eager-load options for Product queries."""
    return [
        selectinload(Product.category),
        selectinload(Product.manufacturer),
        selectinload(Product.supplier),
        selectinload(Product.comm_methods).selectinload(ProductCommMethod.method),
        selectinload(Product.comm_protocols).selectinload(ProductCommProtocol.protocol),
        selectinload(Product.power_supplies).selectinload(ProductPowerSupply.power),
        selectinload(Product.hardware_interfaces),
        selectinload(Product.sensor_capabilities).selectinload(ProductSensorCapability.metric),
        selectinload(Product.images),
    ]


def build_product_detail(p: Product, db: Session) -> dict:
    """Build full product dict with mappings, images, spec_definitions, dependencies."""
    result = p.to_dict()

    # Add multi-category IDs from junction table
    from app.services.product_category_helper import get_product_category_ids
    rows = get_product_category_ids(db, p.id)
    result['category_ids'] = rows if rows else [p.category_id] if p.category_id else []

    spec_defs = db.query(CategorySpecDefinition).filter_by(category_id=p.category_id)\
        .order_by(CategorySpecDefinition.sort_order).all()
    result["spec_definitions"] = [sd.to_dict() for sd in spec_defs]

    if p.parent_id is None:
        variants = db.query(Product).filter(Product.parent_id == p.id).all()
        if variants:
            cats, mfgs, sups = get_name_maps(db)
            result["variants"] = [v.to_dict(cats, sups, mfgs) for v in variants]

    deps = db.query(ProductDependency).filter_by(product_id=p.id).all()
    result["dependencies"] = [d.to_dict() for d in deps]

    return result


def write_mappings(product_id: int, data: dict, db: Session):
    """Write mapping tables from a dict (used by create)."""
    # Comm methods
    for cm in (data.get("comm_methods") or []):
        mid = cm.get("method_id") if isinstance(cm, dict) else cm
        if not mid: continue
        db.add(ProductCommMethod(
            product_id=product_id,
            method_id=cm.get("method_id") if isinstance(cm, dict) else cm,
            details=cm.get("details", "") if isinstance(cm, dict) else "",
        ))
    # Comm protocols
    for cp in (data.get("comm_protocols") or []):
        pid = cp.get("protocol_id") if isinstance(cp, dict) else cp
        if not pid: continue
        db.add(ProductCommProtocol(
            product_id=product_id,
            protocol_id=pid,
            direction=cp.get("direction", "both") if isinstance(cp, dict) else "both",
        ))
    # Power supplies
    for ps in (data.get("power_supplies") or []):
        pid = ps.get("power_id") if isinstance(ps, dict) else ps
        if not pid: continue
        db.add(ProductPowerSupply(
            product_id=product_id,
            power_id=pid,
            voltage_range=ps.get("voltage_range", "") if isinstance(ps, dict) else "",
            battery_life=ps.get("battery_life", "") if isinstance(ps, dict) else "",
        ))
    # Hardware interfaces
    for hi in (data.get("hardware_interfaces") or []):
        if isinstance(hi, dict) and not hi.get("interface_name"): continue
        db.add(ProductHardwareInterface(
            product_id=product_id,
            interface_name=hi.get("interface_name", "") if isinstance(hi, dict) else hi,
            quantity=hi.get("quantity", 1) if isinstance(hi, dict) else 1,
            description=hi.get("description", "") if isinstance(hi, dict) else "",
        ))
    # Sensor capabilities
    for sc in (data.get("sensor_capabilities") or []):
        mid = sc.get("metric_id") if isinstance(sc, dict) else sc
        if not mid: continue
        db.add(ProductSensorCapability(
            product_id=product_id,
            metric_id=mid,
            measure_range=sc.get("measure_range") if isinstance(sc, dict) else None,
            accuracy=sc.get("accuracy") if isinstance(sc, dict) else None,
            resolution=sc.get("resolution") if isinstance(sc, dict) else None,
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


def rewrite_mappings(product_id: int, data: dict, db: Session):
    """Delete old mappings for fields present in data, then write new ones."""
    if "comm_methods" in data:
        db.query(ProductCommMethod).filter_by(product_id=product_id).delete()
    if "comm_protocols" in data:
        db.query(ProductCommProtocol).filter_by(product_id=product_id).delete()
    if "power_supplies" in data:
        db.query(ProductPowerSupply).filter_by(product_id=product_id).delete()
    if "hardware_interfaces" in data:
        db.query(ProductHardwareInterface).filter_by(product_id=product_id).delete()
    if "sensor_capabilities" in data:
        db.query(ProductSensorCapability).filter_by(product_id=product_id).delete()
    if "images" in data:
        db.query(ProductImage).filter_by(product_id=product_id).delete()
    write_mappings(product_id, data, db)
