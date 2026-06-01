from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.supplier import Supplier
from app.auth import get_current_user

router = APIRouter()


@router.get("/suppliers")
def list_suppliers(search: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(Supplier)
    if search:
        q = q.filter(Supplier.name.ilike(f"%{search}%"))
    suppliers = q.order_by(Supplier.name).all()
    return {"suppliers": [s.to_dict() for s in suppliers]}


@router.post("/suppliers")
def create_supplier(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = Supplier(
        name=data["name"],
        contact_person=data.get("contact_person"),
        phone=data.get("phone"),
        email=data.get("email"),
        website=data.get("website"),
        notes=data.get("notes"),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"supplier": s.to_dict()}


@router.put("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found")
    for f in ["name", "contact_person", "phone", "email", "website", "notes"]:
        if f in data:
            setattr(s, f, data[f])
    db.commit()
    return {"supplier": s.to_dict()}


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found")
    db.delete(s)
    db.commit()
    return {"ok": True}
