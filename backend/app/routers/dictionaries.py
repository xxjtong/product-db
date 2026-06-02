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
def list_manufacturers(db: Session = Depends(get_db)):
    items = db.query(Manufacturer).order_by(Manufacturer.name).all()
    return {"manufacturers": [m.to_dict() for m in items]}


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

@router.get("/dicts/comm-methods")
def list_comm_methods(db: Session = Depends(get_db)):
    items = db.query(DictCommMethod).order_by(DictCommMethod.id).all()
    return {"comm_methods": [i.to_dict() for i in items]}


@router.get("/dicts/comm-protocols")
def list_comm_protocols(db: Session = Depends(get_db)):
    items = db.query(DictCommProtocol).order_by(DictCommProtocol.id).all()
    return {"comm_protocols": [i.to_dict() for i in items]}


@router.get("/dicts/power-supplies")
def list_power_supplies(db: Session = Depends(get_db)):
    items = db.query(DictPowerSupply).order_by(DictPowerSupply.id).all()
    return {"power_supplies": [i.to_dict() for i in items]}


@router.get("/dicts/sensor-metrics")
def list_sensor_metrics(db: Session = Depends(get_db)):
    items = db.query(DictSensorMetric).order_by(DictSensorMetric.id).all()
    return {"sensor_metrics": [i.to_dict() for i in items]}
