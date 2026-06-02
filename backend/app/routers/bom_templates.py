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
from app.schemas.bom_template import BOMTemplateCreate, BOMTemplateUpdate, SaveAsTemplateRequest
from app.schemas.solution import BOMSnapshotSave
from datetime import datetime
from io import BytesIO

router = APIRouter()


# --- BOM Templates ---

@router.get("/bom-templates")
def list_templates(db: Session = Depends(get_db), user=Depends(get_current_user)):
    templates = db.query(BOMTemplate).order_by(BOMTemplate.name).all()
    return {"templates": [t.to_dict() for t in templates]}


@router.post("/bom-templates")
def create_template(data: BOMTemplateCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = BOMTemplate(
        name=data.name,
        description=data.description,
        sheet_name=data.sheet_name,
        snapshot=data.snapshot,
        is_default=data.is_default,
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
def update_template(template_id: int, data: BOMTemplateUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    t = db.get(BOMTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    for f in ["name", "description", "sheet_name", "snapshot", "is_default"]:
        val = getattr(data, f, None)
        if val is not None:
            setattr(t, f, val)
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
def save_bom_snapshot(solution_id: int, data: BOMSnapshotSave, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")

    existing = db.query(SolutionBOMSnapshot).filter_by(solution_id=solution_id).first()
    if existing:
        existing.snapshot = data.snapshot if data.snapshot else existing.snapshot
        existing.updated_at = datetime.now()
    else:
        existing = SolutionBOMSnapshot(
            solution_id=solution_id,
            template_id=None,
            snapshot=data.snapshot,
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return {"bom_snapshot": existing.to_dict()}


@router.post("/solutions/{solution_id}/bom-snapshot/save-as-template")
def save_as_template(solution_id: int, data: SaveAsTemplateRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    snap = db.query(SolutionBOMSnapshot).filter_by(solution_id=solution_id).first()
    if not snap:
        raise HTTPException(404, "No BOM snapshot found for this solution")

    t = BOMTemplate(
        name=data.name or f"Template from Solution #{solution_id}",
        description=data.description,
        sheet_name=data.sheet_name,
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
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    import re

    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")

    snap = db.query(SolutionBOMSnapshot).filter_by(solution_id=solution_id).first()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM"

    if snap and snap.snapshot and snap.snapshot.get("cells"):
        _write_snapshot_to_xlsx(ws, snap.snapshot)
    else:
        _write_basic_bom(ws, sol, solution_id, db)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"bom_solution_{solution_id}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


def _cell_ref_to_rc(ref: str):
    """Convert 'A1' to (row, col) tuple (1-indexed)."""
    m = re.match(r'^([A-Z]+)(\d+)$', ref)
    if not m:
        return 1, 1
    col = 0
    for ch in m.group(1):
        col = col * 26 + (ord(ch) - 64)
    return int(m.group(2)), col


def _inline_style_to_openpyxl(s: dict) -> dict:
    """Convert snapshot inline style to openpyxl kwargs."""
    result = {}
    font_kwargs = {}

    if s.get("fs"):
        font_kwargs["size"] = s["fs"]
    if s.get("bl"):
        font_kwargs["bold"] = True
    if s.get("it"):
        font_kwargs["italic"] = True
    if s.get("ul"):
        font_kwargs["underline"] = "single"
    if s.get("ff"):
        font_kwargs["name"] = s["ff"]
    if s.get("cl"):
        font_kwargs["color"] = s["cl"].lstrip("#")

    if font_kwargs:
        result["font"] = Font(**font_kwargs)

    if s.get("bg"):
        result["fill"] = PatternFill(start_color=s["bg"].lstrip("#"),
                                      end_color=s["bg"].lstrip("#"),
                                      fill_type="solid")

    align_kwargs = {}
    if s.get("ht"):
        align_map = {"left": "left", "center": "center", "right": "right"}
        align_kwargs["horizontal"] = align_map.get(s["ht"], s["ht"])
    if s.get("vt"):
        v_map = {"top": "top", "middle": "center", "bottom": "bottom"}
        align_kwargs["vertical"] = v_map.get(s["vt"], s["vt"])
    if s.get("tb"):
        align_kwargs["wrap_text"] = True
    if align_kwargs:
        result["alignment"] = Alignment(**align_kwargs)

    return result


def _write_snapshot_to_xlsx(ws, snapshot: dict):
    """Write snapshot data (cells, styles, merges, colWidths, rowHeights) to openpyxl worksheet."""
    cells = snapshot.get("cells", {})

    # Write cell values, formulas, and styles
    for ref, cell in cells.items():
        row, col = _cell_ref_to_rc(ref)
        openpyxl_cell = ws.cell(row=row, column=col)

        v = cell.get("v")
        if v is not None and v != "":
            openpyxl_cell.value = v

        if cell.get("f"):
            openpyxl_cell.value = "=" + cell["f"]

        if cell.get("s"):
            style_kwargs = _inline_style_to_openpyxl(cell["s"])
            for attr, value in style_kwargs.items():
                setattr(openpyxl_cell, attr, value)

    # Apply column widths
    col_widths = snapshot.get("colWidths", {})
    for col_key, width in col_widths.items():
        _, col = _cell_ref_to_rc(col_key + "1")
        ws.column_dimensions[col_key].width = max(float(width) * 0.14, 3)

    # Apply row heights
    row_heights = snapshot.get("rowHeights", {})
    for row_key, height in row_heights.items():
        ws.row_dimensions[int(row_key)].height = float(height) * 0.75

    # Apply merges
    merges = snapshot.get("merges", [])
    for ref in merges:
        parts = ref.split(":")
        start = _cell_ref_to_rc(parts[0])
        end = _cell_ref_to_rc(parts[1]) if len(parts) > 1 else start
        ws.merge_cells(
            min_row=start[0], min_col=start[1],
            max_row=end[0], max_col=end[1]
        )


def _write_basic_bom(ws, sol, solution_id: int, db: Session):
    """Fallback: generate a basic BOM sheet from solution_items."""
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
