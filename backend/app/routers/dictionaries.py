"""Dictionary management API routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.utils.helpers import get_or_404, apply_partial_update
from app.models.dictionary import (Manufacturer, DictCommMethod, DictCommProtocol,
                                   DictPowerSupply, DictSensorMetric)
from app.auth import get_current_user, filter_by_ownership, check_ownership
from app.schemas.dictionary import (ManufacturerCreate, ManufacturerUpdate,
    CommMethodCreate, CommMethodUpdate, CommProtocolCreate, CommProtocolUpdate,
    PowerSupplyCreate, PowerSupplyUpdate, SensorMetricCreate, SensorMetricUpdate)

router = APIRouter()


# --- Manufacturers ---

@router.get("/dicts/manufacturers")
def list_manufacturers(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = filter_by_ownership(db.query(Manufacturer), Manufacturer, user)
    total = q.count()
    items = q.order_by(Manufacturer.sort_order, Manufacturer.name).offset((page-1)*per_page).limit(per_page).all()
    return {"manufacturers": [m.to_dict() for m in items], "total": total, "page": page, "per_page": per_page}


@router.get("/dicts/manufacturers/{mfg_id}")
def get_manufacturer(mfg_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    m = get_or_404(db, Manufacturer, mfg_id)
    return {"manufacturer": m.to_dict()}


@router.post("/dicts/manufacturers", status_code=201)
def create_manufacturer(data: ManufacturerCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    m = Manufacturer(name=data.name, website=data.website, description=data.description, created_by=user.id)
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"manufacturer": m.to_dict()}


@router.put("/dicts/manufacturers/{mfg_id}")
def update_manufacturer(mfg_id: int, data: ManufacturerUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    m = get_or_404(db, Manufacturer, mfg_id)
    check_ownership(m, user)
    apply_partial_update(m, data, ["name", "website", "description", "sort_order"])
    db.commit()
    return {"manufacturer": m.to_dict()}


@router.delete("/dicts/manufacturers/{mfg_id}")
def delete_manufacturer(mfg_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    m = get_or_404(db, Manufacturer, mfg_id)
    check_ownership(m, user)
    db.delete(m)
    db.commit()
    return {"ok": True}


# --- Dict table caching ---

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


def _dict_list_filtered(model, db: Session, user, order_by=None):
    """List dict items with ownership filter (no cache, for per-user filtering)."""
    q = filter_by_ownership(db.query(model), model, user)
    if order_by is not None:
        q = q.order_by(order_by)
    return q.all()


@router.get("/dicts/comm-methods")
def list_comm_methods(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = _dict_list_filtered(DictCommMethod, db, user, DictCommMethod.id)
    total = len(items)
    start = (page-1)*per_page; items = items[start:start+per_page]
    return {"comm_methods": [i.to_dict() for i in items], "total": total}


@router.get("/dicts/comm-protocols")
def list_comm_protocols(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = _dict_list_filtered(DictCommProtocol, db, user, DictCommProtocol.id)
    total = len(items)
    start = (page-1)*per_page; items = items[start:start+per_page]
    return {"comm_protocols": [i.to_dict() for i in items], "total": total}


@router.get("/dicts/power-supplies")
def list_power_supplies(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = _dict_list_filtered(DictPowerSupply, db, user, DictPowerSupply.id)
    total = len(items)
    start = (page-1)*per_page; items = items[start:start+per_page]
    return {"power_supplies": [i.to_dict() for i in items], "total": total}


@router.get("/dicts/sensor-metrics")
def list_sensor_metrics(page: int = 1, per_page: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = _dict_list_filtered(DictSensorMetric, db, user, DictSensorMetric.id)
    total = len(items)
    start = (page-1)*per_page; items = items[start:start+per_page]
    return {"sensor_metrics": [i.to_dict() for i in items], "total": total}


# --- Generic dict CRUD helpers ---

def _dict_create(model, data: dict, db: Session, user=None):
    valid_cols = {c.name for c in model.__table__.columns if c.name != 'id'}
    kwargs = {k: v for k, v in data.items() if v is not None and k in valid_cols}
    if user and 'created_by' in valid_cols:
        kwargs['created_by'] = user.id
    item = model(**kwargs)
    db.add(item); db.commit(); db.refresh(item)
    return item.to_dict()

def _dict_update(item, data: dict, db: Session):
    valid_cols = {c.name for c in item.__table__.columns if c.name != 'id'}
    for k, v in data.items():
        if v is not None and k in valid_cols: setattr(item, k, v)
    db.commit()
    return item.to_dict()


# --- Comm Methods CRUD ---

@router.post("/dicts/comm-methods", status_code=201)
def create_comm_method(data: CommMethodCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {"comm_method": _dict_create(DictCommMethod, data.model_dump(), db, user)}

@router.put("/dicts/comm-methods/{item_id}")
def update_comm_method(item_id: int, data: CommMethodUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = get_or_404(db, DictCommMethod, item_id, "Not found")
    check_ownership(item, user)
    return {"comm_method": _dict_update(item, data.model_dump(exclude_unset=True), db)}

@router.delete("/dicts/comm-methods/{item_id}")
def delete_comm_method(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = get_or_404(db, DictCommMethod, item_id, "Not found")
    check_ownership(item, user)
    db.delete(item); db.commit()
    return {"ok": True}


# --- Comm Protocols CRUD ---

@router.post("/dicts/comm-protocols", status_code=201)
def create_comm_protocol(data: CommProtocolCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {"comm_protocol": _dict_create(DictCommProtocol, data.model_dump(), db, user)}

@router.put("/dicts/comm-protocols/{item_id}")
def update_comm_protocol(item_id: int, data: CommProtocolUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = get_or_404(db, DictCommProtocol, item_id, "Not found")
    check_ownership(item, user)
    return {"comm_protocol": _dict_update(item, data.model_dump(exclude_unset=True), db)}

@router.delete("/dicts/comm-protocols/{item_id}")
def delete_comm_protocol(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = get_or_404(db, DictCommProtocol, item_id, "Not found")
    check_ownership(item, user)
    db.delete(item); db.commit()
    return {"ok": True}


# --- Power Supplies CRUD ---

@router.post("/dicts/power-supplies", status_code=201)
def create_power_supply(data: PowerSupplyCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {"power_supply": _dict_create(DictPowerSupply, data.model_dump(), db, user)}

@router.put("/dicts/power-supplies/{item_id}")
def update_power_supply(item_id: int, data: PowerSupplyUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = get_or_404(db, DictPowerSupply, item_id, "Not found")
    check_ownership(item, user)
    return {"power_supply": _dict_update(item, data.model_dump(exclude_unset=True), db)}

@router.delete("/dicts/power-supplies/{item_id}")
def delete_power_supply(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = get_or_404(db, DictPowerSupply, item_id, "Not found")
    check_ownership(item, user)
    db.delete(item); db.commit()
    return {"ok": True}


# --- Sensor Metrics CRUD ---

@router.post("/dicts/sensor-metrics", status_code=201)
def create_sensor_metric(data: SensorMetricCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {"sensor_metric": _dict_create(DictSensorMetric, data.model_dump(), db, user)}

@router.put("/dicts/sensor-metrics/{item_id}")
def update_sensor_metric(item_id: int, data: SensorMetricUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = get_or_404(db, DictSensorMetric, item_id, "Not found")
    check_ownership(item, user)
    return {"sensor_metric": _dict_update(item, data.model_dump(exclude_unset=True), db)}

@router.delete("/dicts/sensor-metrics/{item_id}")
def delete_sensor_metric(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = get_or_404(db, DictSensorMetric, item_id, "Not found")
    check_ownership(item, user)
    db.delete(item); db.commit()
    return {"ok": True}
