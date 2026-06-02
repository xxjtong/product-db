"""Dictionary management API routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.dictionary import (Manufacturer, DictCommMethod, DictCommProtocol,
                                   DictPowerSupply, DictSensorMetric)
from app.auth import get_current_user
from app.schemas.dictionary import ManufacturerCreate, ManufacturerUpdate

router = APIRouter()


# --- Manufacturers ---

@router.get("/dicts/manufacturers")
def list_manufacturers(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(Manufacturer)
    total = q.count()
    items = q.order_by(Manufacturer.name).offset((page-1)*per_page).limit(per_page).all()
    return {"manufacturers": [m.to_dict() for m in items], "total": total, "page": page, "per_page": per_page}


@router.get("/dicts/manufacturers/{mfg_id}")
def get_manufacturer(mfg_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    m = db.get(Manufacturer, mfg_id)
    if not m:
        raise HTTPException(404, "Manufacturer not found")
    return {"manufacturer": m.to_dict()}


@router.post("/dicts/manufacturers")
def create_manufacturer(data: ManufacturerCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    m = Manufacturer(name=data.name, website=data.website, description=data.description)
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"manufacturer": m.to_dict()}


@router.put("/dicts/manufacturers/{mfg_id}")
def update_manufacturer(mfg_id: int, data: ManufacturerUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    m = db.get(Manufacturer, mfg_id)
    if not m:
        raise HTTPException(404)
    for f in ["name", "website", "description"]:
        val = getattr(data, f, None)
        if val is not None:
            setattr(m, f, val)
    db.commit()
    return {"manufacturer": m.to_dict()}


@router.delete("/dicts/manufacturers/{mfg_id}")
def delete_manufacturer(mfg_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    m = db.get(Manufacturer, mfg_id)
    if not m:
        raise HTTPException(404)
    db.delete(m)
    db.commit()
    return {"ok": True}


# --- Dict tables (read-only for now, can add CRUD later) ---

# TTL cache for dict tables (30s)
_dict_cache: dict = {"ts": 0}

def _cached_dict_query(key: str, query_fn, db: Session):
    import time as _time
    now = _time.time()
    if now - _dict_cache.get(f"{key}_ts", 0) < 30:
        return _dict_cache.get(key, [])
    items = query_fn(db)
    _dict_cache[key] = items
    _dict_cache[f"{key}_ts"] = now
    return items


@router.get("/dicts/comm-methods")
def list_comm_methods(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = _cached_dict_query("comm_methods", lambda d: d.query(DictCommMethod).order_by(DictCommMethod.id).all(), db)
    total = len(items)
    start = (page-1)*per_page; items = items[start:start+per_page]
    return {"comm_methods": [i.to_dict() for i in items], "total": total}


@router.get("/dicts/comm-protocols")
def list_comm_protocols(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = _cached_dict_query("comm_protocols", lambda d: d.query(DictCommProtocol).order_by(DictCommProtocol.id).all(), db)
    total = len(items)
    start = (page-1)*per_page; items = items[start:start+per_page]
    return {"comm_protocols": [i.to_dict() for i in items], "total": total}


@router.get("/dicts/power-supplies")
def list_power_supplies(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = _cached_dict_query("power_supplies", lambda d: d.query(DictPowerSupply).order_by(DictPowerSupply.id).all(), db)
    total = len(items)
    start = (page-1)*per_page; items = items[start:start+per_page]
    return {"power_supplies": [i.to_dict() for i in items], "total": total}


@router.get("/dicts/sensor-metrics")
def list_sensor_metrics(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = _cached_dict_query("sensor_metrics", lambda d: d.query(DictSensorMetric).order_by(DictSensorMetric.id).all(), db)
    total = len(items)
    start = (page-1)*per_page; items = items[start:start+per_page]
    return {"sensor_metrics": [i.to_dict() for i in items], "total": total}
