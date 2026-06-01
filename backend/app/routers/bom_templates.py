"""BOM Template CRUD + Solution BOM Snapshot management + xlsx export."""
from __future__ import annotations
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.bom_template import BOMTemplate, SolutionBOMSnapshot
from app.models.solution import Solution, SolutionItem
from app.models.product import Product
from app.auth import get_current_user
from app.models.user import User
from datetime import datetime
from io import BytesIO

router = APIRouter()


# --- BOM Templates ---

@router.get("/bom-templates")
def list_templates(db: Session = Depends(get_db), user=Depends(get_current_user)):
    templates = db.query(BOMTemplate).order_by(BOMTemplate.name).all()
    return {"templates": [t.to_dict() for t in templates]}


@router.post("/bom-templates")
def create_template(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = BOMTemplate(
        name=data["name"],
        description=data.get("description"),
        sheet_name=data.get("sheet_name", "Sheet1"),
        snapshot=data.get("snapshot", {}),
        is_default=data.get("is_default", False),
        created_by=user.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"template": t.to_dict()}


@router.get("/bom-templates/{template_id}")
def get_template(template_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = db.get(BOMTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    return {"template": t.to_dict()}


@router.put("/bom-templates/{template_id}")
def update_template(template_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = db.get(BOMTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    for f in ["name", "description", "sheet_name", "snapshot", "is_default"]:
        if f in data:
            setattr(t, f, data[f])
    t.updated_at = datetime.now()
    db.commit()
    return {"template": t.to_dict()}


@router.delete("/bom-templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = db.get(BOMTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.post("/bom-templates/{template_id}/duplicate")
def duplicate_template(template_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = db.get(BOMTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    new_t = BOMTemplate(
        name=f"{t.name} (副本)",
        description=t.description,
        sheet_name=t.sheet_name,
        snapshot=t.snapshot,
        is_default=False,
        created_by=user.id,
    )
    db.add(new_t)
    db.commit()
    db.refresh(new_t)
    return {"template": new_t.to_dict()}


# --- Solution BOM Snapshot ---

@router.get("/solutions/{solution_id}/bom-snapshot")
def get_bom_snapshot(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")

    existing = db.query(SolutionBOMSnapshot).filter_by(solution_id=solution_id).first()
    if existing:
        return {"bom_snapshot": existing.to_dict()}

    # Generate from template + solution items
    template_id = None
    default_template = db.query(BOMTemplate).filter_by(is_default=True).first()
    if not default_template:
        default_template = db.query(BOMTemplate).first()
    template_id = default_template.id if default_template else None

    snapshot_data = _generate_snapshot(sol, default_template, db)
    new_snapshot = SolutionBOMSnapshot(
        solution_id=solution_id,
        template_id=template_id,
        snapshot=snapshot_data,
    )
    db.add(new_snapshot)
    db.commit()
    db.refresh(new_snapshot)
    return {"bom_snapshot": new_snapshot.to_dict()}


@router.put("/solutions/{solution_id}/bom-snapshot")
def save_bom_snapshot(solution_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")

    existing = db.query(SolutionBOMSnapshot).filter_by(solution_id=solution_id).first()
    if existing:
        existing.snapshot = data.get("snapshot", existing.snapshot)
        existing.updated_at = datetime.now()
    else:
        existing = SolutionBOMSnapshot(
            solution_id=solution_id,
            template_id=data.get("template_id"),
            snapshot=data.get("snapshot", {}),
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return {"bom_snapshot": existing.to_dict()}


@router.post("/solutions/{solution_id}/bom-snapshot/save-as-template")
def save_as_template(solution_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    snap = db.query(SolutionBOMSnapshot).filter_by(solution_id=solution_id).first()
    if not snap:
        raise HTTPException(404, "No BOM snapshot found for this solution")

    t = BOMTemplate(
        name=data.get("name", f"Template from Solution #{solution_id}"),
        description=data.get("description"),
        sheet_name=data.get("sheet_name", "Sheet1"),
        snapshot=snap.snapshot,
        is_default=False,
        created_by=user.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"template": t.to_dict()}


@router.get("/solutions/{solution_id}/bom-snapshot/export-xlsx")
def export_bom_xlsx(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    import openpyxl
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM"

    ws.append([f"BOM - {sol.name}"])
    ws.append([f"客户: {sol.client_name or ''}", f"项目: {sol.project_name or ''}"])
    ws.append([])
    ws.append(["序号", "产品", "SKU", "数量", "单价", "金额", "折扣(%)", "备注"])

    items = db.query(SolutionItem).filter_by(solution_id=solution_id)\
        .order_by(SolutionItem.sort_order).all()
    product_map = {p.id: p for p in db.query(Product).all()}
    for idx, item in enumerate(items, 1):
        p = product_map.get(item.product_id)
        ws.append([
            idx,
            p.name if p else "",
            p.sku if p else "",
            float(item.quantity or 0),
            float(item.unit_price or 0),
            float(item.quantity or 0) * float(item.unit_price or 0) * (float(item.discount_rate or 100) / 100),
            float(item.discount_rate or 100),
            item.remark or "",
        ])

    ws.append([])
    ws.append(["合计", "", "", "", "", float(sol.total_price or 0)])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"bom_solution_{solution_id}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


def _generate_snapshot(sol: Solution, template, db: Session) -> dict:
    """Generate a BOM snapshot by merging template structure with solution items."""
    if template and template.snapshot:
        snapshot = dict(template.snapshot)
    else:
        snapshot = {"cells": {}, "colWidths": {}, "rowHeights": {}}

    items = db.query(SolutionItem).filter_by(solution_id=sol.id)\
        .order_by(SolutionItem.sort_order).all()
    product_map = {p.id: p for p in db.query(Product).all()}

    cells = snapshot.get("cells", {})
    start_row = 3
    for idx, item in enumerate(items):
        row = start_row + idx
        p = product_map.get(item.product_id)
        cells[f"A{row}"] = {"v": idx + 1}
        cells[f"B{row}"] = {"v": p.name if p else ""}
        cells[f"C{row}"] = {"v": p.sku if p else ""}
        cells[f"D{row}"] = {"v": float(item.quantity or 0)}
        cells[f"E{row}"] = {"v": float(item.unit_price or 0)}
        cells[f"F{row}"] = {"v": float(item.quantity or 0) * float(item.unit_price or 0) * (float(item.discount_rate or 100) / 100)}
        cells[f"G{row}"] = {"v": float(item.discount_rate or 100)}
        cells[f"H{row}"] = {"v": item.remark or ""}

    snapshot["cells"] = cells
    return snapshot
