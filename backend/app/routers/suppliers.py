from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.utils.helpers import get_or_404
from app.models.supplier import Supplier
from app.auth import get_current_user, filter_by_ownership, check_ownership
from app.utils.escape import escape_like, LIKE_ESCAPE
from app.utils.helpers import apply_partial_update
from app.schemas.supplier import SupplierCreate, SupplierUpdate

router = APIRouter()


@router.get("/suppliers")
def list_suppliers(
    search: str = "",
    page: int = 1,
    per_page: int = 25,
    all: bool = False,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    q = filter_by_ownership(db.query(Supplier), Supplier, user)
    if search:
        q = q.filter(Supplier.name.ilike(f"%{escape_like(search)}%", escape=LIKE_ESCAPE))
    q = q.order_by(Supplier.name)
    total = q.count()
    if all:
        suppliers = q.all()
        return {"suppliers": [s.to_dict() for s in suppliers], "total": total}
    suppliers = q.offset((page - 1) * per_page).limit(per_page).all()
    return {"suppliers": [s.to_dict() for s in suppliers], "total": total, "page": page, "per_page": per_page}


@router.get("/suppliers/{supplier_id}")
def get_supplier(supplier_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = get_or_404(db, Supplier, supplier_id, "Supplier not found")
    return {"supplier": s.to_dict()}


@router.post("/suppliers", status_code=201)
def create_supplier(data: SupplierCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = Supplier(
        name=data.name,
        contact_person=data.contact_person,
        phone=data.phone,
        email=data.email,
        website=data.website,
        notes=data.notes,
        created_by=user.id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"supplier": s.to_dict()}


@router.put("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, data: SupplierUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = get_or_404(db, Supplier, supplier_id, "Supplier not found")
    check_ownership(s, user)
    apply_partial_update(s, data, ["name", "contact_person", "phone", "email", "website", "notes"])
    db.commit()
    return {"supplier": s.to_dict()}


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = get_or_404(db, Supplier, supplier_id, "Supplier not found")
    check_ownership(s, user)
    db.delete(s)
    db.commit()
    return {"ok": True}
