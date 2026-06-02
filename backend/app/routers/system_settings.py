"""System settings API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.system_setting import SystemSetting
from app.schemas.dictionary import SystemSettingUpdate

router = APIRouter()


def get_setting(db: Session, key: str, default: str = "") -> str:
    s = db.query(SystemSetting).filter_by(key=key).first()
    return s.value if s else default


@router.get("/settings")
def list_settings(db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = db.query(SystemSetting).order_by(SystemSetting.key).all()
    return {"settings": [s.to_dict() for s in items]}


@router.put("/settings/{key}")
def update_setting(key: str, data: SystemSettingUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    s = db.query(SystemSetting).filter_by(key=key).first()
    if not s:
        s = SystemSetting(key=key)
        db.add(s)
    s.value = data.value
    s.description = data.description
    db.commit()
    return {"setting": s.to_dict()}


@router.get("/settings/{key}")
def get_one_setting(key: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {"value": get_setting(db, key)}
