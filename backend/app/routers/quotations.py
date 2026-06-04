"""Quotation CRUD + export."""
from __future__ import annotations
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from app.database import get_db
from app.models.quotation import Quotation, QuotationItem
from app.models.product import Product
from app.models.solution import Solution, SolutionItem
from app.auth import get_current_user, filter_by_ownership, check_ownership
from app.models.user import User
from app.utils.escape import escape_like
from app.schemas.quotation import QuotationCreate, QuotationUpdate, QuotationItemCreate, QuotationItemUpdate
from app.schemas.solution import BatchDeleteRequest
from datetime import datetime, timedelta
from io import BytesIO

router = APIRouter()


def _generate_quote_number(db: Session) -> str:
    """Generate quote number: QT-YYYYMMDD-NNN."""
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"QT-{today}-"
    last = db.query(Quotation).filter(Quotation.quote_number.like(f"{prefix}%"))\
        .order_by(Quotation.id.desc()).with_for_update().first()
    seq = 1
    if last and last.quote_number:
        try:
            seq = int(last.quote_number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}{seq:03d}"


def _recalc_total(qt: Quotation, db: Session):
    items = db.query(QuotationItem).filter_by(quotation_id=qt.id).all()
    total = 0
    for item in items:
        qty = float(item.quantity or 0)
        price = float(item.unit_price or 0)
        rate = float(item.discount_rate or 100)
        amount = qty * price * (rate / 100)
        item.amount = amount
        total += amount
    qt.total_amount = total


@router.get("/quotations")
def list_quotations(
    status: Optional[str] = None,
    search: str = "",
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    q = db.query(Quotation).options(
        selectinload(Quotation.items),
    )
    q = filter_by_ownership(q, Quotation, user)
    if status:
        q = q.filter(Quotation.status == status)
    if search:
        q = q.filter(
            Quotation.quote_number.ilike(f"%{escape_like(search)}%")
            | Quotation.title.ilike(f"%{escape_like(search)}%")
            | Quotation.client_name.ilike(f"%{escape_like(search)}%")
        )
    total = q.count()
    quotations = q.order_by(Quotation.updated_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "quotations": [qt.to_dict() for qt in quotations],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/quotations")
def create_quotation(data: QuotationCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = Quotation(
        solution_id=data.solution_id,
        quote_number=_generate_quote_number(db),
        title=data.title,
        client_name=data.client_name,
        client_contact=data.client_contact,
        valid_days=data.valid_days,
        tax_rate=data.tax_rate,
        status=data.status,
        notes=data.notes,
        created_by=user.id,
    )

    # Populate from solution if provided
    solution_id = data.solution_id
    if solution_id:
        sol = db.get(Solution, solution_id)
        if sol:
            if not qt.title:
                qt.title = sol.name
            if not qt.client_name:
                qt.client_name = sol.client_name
            sol_items = db.query(SolutionItem).options(
                selectinload(SolutionItem.product),
            ).filter_by(solution_id=solution_id).all()
            # Preload products with all relationships for full snapshots
            product_ids = [si.product_id for si in sol_items]
            products_map = {}
            if product_ids:
                prods = db.query(Product).options(
                    selectinload(Product.category),
                    selectinload(Product.manufacturer),
                    selectinload(Product.supplier),
                    selectinload(Product.comm_methods),
                    selectinload(Product.comm_protocols),
                    selectinload(Product.power_supplies),
                    selectinload(Product.hardware_interfaces),
                    selectinload(Product.sensor_capabilities),
                    selectinload(Product.images),
                ).filter(Product.id.in_(product_ids)).all()
                products_map = {p.id: p for p in prods}
            for si in sol_items:
                prod = products_map.get(si.product_id)
                snapshot = prod.to_dict() if prod else {}
                qi = QuotationItem(
                    quotation=qt,
                    solution_item_id=si.id,
                    product_id=si.product_id,
                    product_snapshot=snapshot,
                    quantity=si.quantity,
                    unit_price=si.unit_price or (float(prod.base_price) if prod and prod.base_price else 0),
                    amount=float(si.quantity or 0) * float(si.unit_price or 0),
                    discount_rate=si.discount_rate,
                    remark=si.remark,
                    sort_order=si.sort_order,
                )
                db.add(qi)

    db.add(qt)
    db.commit()
    db.refresh(qt)
    _recalc_total(qt, db)
    db.commit()
    db.refresh(qt)
    return {"quotation": qt.to_dict()}


@router.post("/quotations/batch-delete")
def batch_delete_quotations(data: BatchDeleteRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not data.ids:
        raise HTTPException(400, "ids is required")
    deleted = db.query(Quotation).filter(Quotation.id.in_(data.ids)).delete(synchronize_session="fetch")
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.get("/quotations/{quotation_id}")
def get_quotation(quotation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = db.scalar(select(Quotation).options(
        selectinload(Quotation.items),
    ).where(Quotation.id == quotation_id))
    if not qt:
        raise HTTPException(404, "Quotation not found")
    return {"quotation": qt.to_dict()}


@router.put("/quotations/{quotation_id}")
def update_quotation(quotation_id: int, data: QuotationUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = db.get(Quotation, quotation_id)
    if not qt:
        raise HTTPException(404, "Quotation not found")
    check_ownership(qt, user)
    for f in ["title", "client_name", "client_contact", "valid_days", "tax_rate", "status", "notes"]:
        val = getattr(data, f, None)
        if val is not None:
            setattr(qt, f, val)
    qt.updated_at = datetime.now()
    db.commit()
    qt = db.scalar(select(Quotation).options(
        selectinload(Quotation.items),
    ).where(Quotation.id == quotation_id))
    return {"quotation": qt.to_dict()}


@router.delete("/quotations/{quotation_id}")
def delete_quotation(quotation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = db.get(Quotation, quotation_id)
    if not qt:
        raise HTTPException(404, "Quotation not found")
    check_ownership(qt, user)
    db.delete(qt)
    db.commit()
    return {"ok": True}


# --- Quotation Items ---

@router.get("/quotations/{quotation_id}/items")
def list_quotation_items(quotation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = db.get(Quotation, quotation_id)
    if not qt:
        raise HTTPException(404, "Quotation not found")
    items = db.query(QuotationItem).filter_by(quotation_id=quotation_id)\
        .order_by(QuotationItem.sort_order).all()
    return {"items": [i.to_dict() for i in items]}


@router.post("/quotations/{quotation_id}/items")
def add_quotation_item(quotation_id: int, data: QuotationItemCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = db.get(Quotation, quotation_id)
    if not qt:
        raise HTTPException(404, "Quotation not found")
    prod = db.get(Product, data.product_id)
    snapshot = prod.to_dict() if prod else {}

    qi = QuotationItem(
        quotation_id=quotation_id,
        product_id=data.product_id,
        product_snapshot=snapshot,
        quantity=data.quantity,
        unit_price=data.unit_price if data.unit_price is not None else (float(prod.base_price or 0) if prod else 0),
        amount=data.amount,
        discount_rate=data.discount_rate,
        remark=data.remark,
        sort_order=data.sort_order,
    )
    db.add(qi)
    db.commit()
    _recalc_total(qt, db)
    db.commit()
    db.refresh(qi)
    return {"item": qi.to_dict()}


@router.put("/quotations/{quotation_id}/items/{item_id}")
def update_quotation_item(quotation_id: int, item_id: int, data: QuotationItemUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qi = db.get(QuotationItem, item_id)
    if not qi or qi.quotation_id != quotation_id:
        raise HTTPException(404, "Item not found")
    for f in ["product_id", "quantity", "unit_price", "amount", "discount_rate", "remark", "sort_order"]:
        val = getattr(data, f, None)
        if val is not None:
            setattr(qi, f, val)
    db.commit()
    qt = db.get(Quotation, quotation_id)
    _recalc_total(qt, db)
    db.commit()
    db.refresh(qi)
    return {"item": qi.to_dict()}


@router.delete("/quotations/{quotation_id}/items/{item_id}")
def delete_quotation_item(quotation_id: int, item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qi = db.get(QuotationItem, item_id)
    if not qi or qi.quotation_id != quotation_id:
        raise HTTPException(404, "Item not found")
    db.delete(qi)
    db.commit()
    qt = db.get(Quotation, quotation_id)
    _recalc_total(qt, db)
    db.commit()
    return {"ok": True}


# --- Export ---

@router.get("/quotations/{quotation_id}/export-xlsx")
def export_quotation_xlsx(quotation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = db.get(Quotation, quotation_id)
    if not qt:
        raise HTTPException(404, "Quotation not found")

    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "报价单"

    ws.append(["报价单"])
    ws.append([f"编号: {qt.quote_number or ''}", f"客户: {qt.client_name or ''}"])
    ws.append([f"有效期: {qt.valid_days}天", f"税率: {float(qt.tax_rate or 0)}%"])
    ws.append([])
    ws.append(["#", "产品名称", "型号/SKU", "功能描述", "数量", "单价", "折扣%", "小计", "备注"])

    items = db.query(QuotationItem).filter_by(quotation_id=quotation_id)\
        .order_by(QuotationItem.sort_order).all()
    for idx, item in enumerate(items, 1):
        snap = item.product_snapshot or {}
        model_sku = (snap.get("model", "") or "") + (" / " + snap.get("sku", "") if snap.get("sku") else "")
        ws.append([
            idx,
            snap.get("name", ""),
            model_sku,
            (snap.get("description", "") or "")[:200],
            float(item.quantity or 0),
            float(item.unit_price or 0),
            float(item.discount_rate or 100),
            float(item.amount or 0),
            item.remark or "",
        ])

    ws.append([])
    ws.append(["", "", "", "", "", "", "合计", float(qt.total_amount or 0), ""])

    # Log download
    from app.models.download_log import DownloadLog
    import logging
    log = DownloadLog(user_id=user.id, file_type="quotation", entity_id=quotation_id, ip_address="")
    db.add(log)
    qt.download_count = (qt.download_count or 0) + 1
    db.commit()

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"quotation_{qt.quote_number or quotation_id}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


# --- Quotation BOM Editor ---

@router.get("/quotations/{quotation_id}/bom")
def get_quotation_bom(quotation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = db.get(Quotation, quotation_id)
    if not qt:
        raise HTTPException(404, "Quotation not found")
    items = db.query(QuotationItem).filter_by(quotation_id=quotation_id)\
        .order_by(QuotationItem.sort_order).all()
    rows = []
    for idx, item in enumerate(items):
        snap = item.product_snapshot or {}
        rows.append({
            "name": snap.get("name", ""),
            "sku": snap.get("sku", ""),
            "model": snap.get("model", ""),
            "description": (snap.get("description", "") or "")[:200],
            "qty": float(item.quantity or 0),
            "price": float(item.unit_price or 0),
            "discount": float(item.discount_rate or 100),
            "remark": item.remark or "",
        })
    return {"rows": rows, "total": float(qt.total_amount or 0)}


@router.put("/quotations/{quotation_id}/bom")
def save_quotation_bom(quotation_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = db.get(Quotation, quotation_id)
    if not qt:
        raise HTTPException(404, "Quotation not found")
    rows = data.get("rows", [])
    # Remove all existing items, then recreate from BOM rows
    db.query(QuotationItem).filter_by(quotation_id=quotation_id).delete()
    for idx, row in enumerate(rows):
        snap = {"name": row.get("name", ""), "sku": row.get("sku", ""),
                "model": row.get("model", ""), "description": row.get("description", "")}
        qi = QuotationItem(
            quotation_id=quotation_id,
            product_id=0,
            product_snapshot=snap,
            quantity=float(row.get("qty", 1) or 1),
            unit_price=float(row.get("price", 0) or 0),
            amount=float(row.get("qty", 1) or 1) * float(row.get("price", 0) or 0) * (float(row.get("discount", 100) or 100) / 100),
            discount_rate=float(row.get("discount", 100) or 100),
            remark=str(row.get("remark", "") or ""),
            sort_order=idx + 1,
        )
        db.add(qi)
    db.flush()
    _recalc_total(qt, db)
    db.commit()
    return {"ok": True, "total": float(qt.total_amount or 0)}
