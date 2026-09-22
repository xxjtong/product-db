"""Quotation CRUD + export."""
from __future__ import annotations
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func, update
from app.database import get_db
from app.utils.helpers import (get_or_404, apply_partial_update, format_description_with_specs,
                               discount_percent, number_or)
from app.models.quotation import Quotation, QuotationItem
from app.models.product import Product
from app.models.solution import Solution
from app.auth import get_current_user, filter_by_ownership, check_ownership
from app.models.user import User
from app.services.field_visibility import cost_visible
from app.utils.escape import escape_like, LIKE_ESCAPE
from app.schemas.quotation import (QuotationCreate, QuotationUpdate, QuotationItemCreate,
                                   QuotationItemUpdate, QuotationBOMSave)
from app.schemas.solution import BatchDeleteRequest
from app.services.quotation_service import create_quotation_from_solution
from datetime import datetime, timezone
from io import BytesIO

router = APIRouter()


def _strip_cost_from_snapshot(snapshot: dict) -> dict:
    """Return a snapshot copy without cost_price (used for non-admin responses)."""
    if isinstance(snapshot, dict) and "cost_price" in snapshot:
        snapshot = dict(snapshot)
        snapshot.pop("cost_price", None)
    return snapshot


def _filter_quotation_items_cost(items: list, user, db) -> list:
    """Remove cost_price from each item's product_snapshot when hidden."""
    if cost_visible(user, db):
        return items
    for item in items:
        snap = item.get("product_snapshot") or {}
        if "cost_price" in snap:
            item["product_snapshot"] = _strip_cost_from_snapshot(snap)
    return items


def _fmt_rate(rate) -> str:
    """税率展示格式：整数不带小数点（13 → '13'，13.5 → '13.5'）

    Numeric(5,2) 取出来是 Decimal('13.00')，直接 f-string 会打成「13.0%」。
    """
    try:
        value = float(rate or 0)
    except (TypeError, ValueError):
        return "0"
    return str(int(value)) if value == int(value) else f"{value:g}"


def _recalc_total(qt: Quotation, db: Session):
    items = db.query(QuotationItem).filter_by(quotation_id=qt.id).all()
    total = 0
    for item in items:
        qty = float(item.quantity or 0)
        price = float(item.unit_price or 0)
        rate = discount_percent(item.discount_rate)
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
    q = filter_by_ownership(q, Quotation, user, strict=True)
    if status:
        q = q.filter(Quotation.status == status)
    if search:
        q = q.filter(
            Quotation.quote_number.ilike(f"%{escape_like(search)}%", escape=LIKE_ESCAPE)
            | Quotation.title.ilike(f"%{escape_like(search)}%", escape=LIKE_ESCAPE)
            | Quotation.client_name.ilike(f"%{escape_like(search)}%", escape=LIKE_ESCAPE)
        )
    from app.utils.helpers import paginate
    quotations, total = paginate(q.order_by(Quotation.updated_at.desc()), page, per_page)
    quotation_list = [qt.to_dict() for qt in quotations]
    for qt_dict in quotation_list:
        _filter_quotation_items_cost(qt_dict.get("items") or [], user, db)
    return {
        "quotations": quotation_list,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/quotations", status_code=201)
def create_quotation(data: QuotationCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """建报价单。实现集中在 `services/quotation_service`（REST / AI / Hermes 共用一份）。"""
    solution = None
    if data.solution_id:
        solution = db.get(Solution, data.solution_id)
        if not solution:
            # 以前这里 `if sol:` 为假时静默跳过，调用方以为复制了方案、实际拿到一张空单
            raise HTTPException(404, "方案不存在")
        # 归属校验：否则任意登录用户传别人的 solution_id 就能把该方案的
        # 条目/单价/产品快照整体复制进自己的报价单（ai_tools 里同一动作是 strict）
        check_ownership(solution, user, strict=True)

    try:
        qt = create_quotation_from_solution(
            db, solution, user,
            title=data.title,
            client_name=data.client_name,
            client_contact=data.client_contact,
            valid_days=data.valid_days,
            tax_rate=data.tax_rate,
            status=data.status,
            notes=data.notes,
            extra_items=data.extra_items,
        )
        db.commit()
    except IntegrityError:
        # 并发建单取到同一编号（SQLite 无 SELECT FOR UPDATE，取号无法加锁）：
        # 与其抛 500，不如明确告诉调用方重试（R56）
        db.rollback()
        raise HTTPException(409, "报价单号生成冲突，请重试")
    db.refresh(qt)
    result = qt.to_dict()
    _filter_quotation_items_cost(result.get("items") or [], user, db)
    return {"quotation": result}


@router.post("/quotations/batch-delete")
def batch_delete_quotations(data: BatchDeleteRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not data.ids:
        raise HTTPException(400, "ids is required")
    if user.role != "admin":
        owned = db.query(Quotation.id).filter(
            Quotation.id.in_(data.ids),
            Quotation.created_by == user.id,
        ).all()
        owned_ids = {r[0] for r in owned}
        forbidden = [i for i in data.ids if i not in owned_ids]
        if forbidden:
            raise HTTPException(403, f"Access denied for quotations: {forbidden}")
    # 同 solutions.batch-delete：bulk DELETE 不触发 ORM 的 cascade，`Quotation.items`
    # 的级联不会跑，逐条 ORM 删除才稳妥（R57 起外键已强制开启，但 bulk delete 绕过的
    # 正是这一层）。
    rows = db.query(Quotation).filter(Quotation.id.in_(data.ids)).all()
    for row in rows:
        db.delete(row)
    db.commit()
    return {"ok": True, "deleted": len(rows)}


@router.get("/quotations/{quotation_id}")
def get_quotation(quotation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = db.scalar(select(Quotation).options(
        selectinload(Quotation.items),
    ).where(Quotation.id == quotation_id))
    if not qt:
        raise HTTPException(404, "Quotation not found")
    check_ownership(qt, user, strict=True)
    result = qt.to_dict()
    _filter_quotation_items_cost(result.get("items") or [], user, db)
    return {"quotation": result}


@router.put("/quotations/{quotation_id}")
def update_quotation(quotation_id: int, data: QuotationUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = get_or_404(db, Quotation, quotation_id, "Quotation not found")
    check_ownership(qt, user, strict=True)
    apply_partial_update(qt, data, ["title", "client_name", "client_contact", "valid_days", "tax_rate", "status", "notes"])
    qt.updated_at = datetime.now(timezone.utc)
    db.commit()
    qt = db.scalar(select(Quotation).options(
        selectinload(Quotation.items),
    ).where(Quotation.id == quotation_id))
    result = qt.to_dict()
    _filter_quotation_items_cost(result.get("items") or [], user, db)
    return {"quotation": result}


@router.delete("/quotations/{quotation_id}")
def delete_quotation(quotation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = get_or_404(db, Quotation, quotation_id, "Quotation not found")
    check_ownership(qt, user, strict=True)
    db.delete(qt)
    db.commit()
    return {"ok": True}


# --- Quotation Items ---

@router.get("/quotations/{quotation_id}/items")
def list_quotation_items(quotation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = get_or_404(db, Quotation, quotation_id, "Quotation not found")
    check_ownership(qt, user, strict=True)
    items = db.query(QuotationItem).filter_by(quotation_id=quotation_id)\
        .order_by(QuotationItem.sort_order).all()
    item_list = [i.to_dict() for i in items]
    if not cost_visible(user, db):
        for item in item_list:
            item["product_snapshot"] = _strip_cost_from_snapshot(item.get("product_snapshot") or {})
    return {"items": item_list}


@router.post("/quotations/{quotation_id}/items", status_code=201)
def add_quotation_item(quotation_id: int, data: QuotationItemCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = get_or_404(db, Quotation, quotation_id, "Quotation not found")
    check_ownership(qt, user, strict=True)
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
    # 快照直接来⾃ prod.to_dict()，含真实 cost_price —— 与列表接口一样要按权限裁剪，
    # 否则这条路会成为成本出口（列表裁了、写接口没裁就等于没裁）。
    return {"item": _filter_quotation_items_cost([qi.to_dict()], user, db)[0]}


@router.put("/quotations/{quotation_id}/items/{item_id}")
def update_quotation_item(quotation_id: int, item_id: int, data: QuotationItemUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = get_or_404(db, Quotation, quotation_id, "Quotation not found")
    check_ownership(qt, user, strict=True)
    qi = db.get(QuotationItem, item_id)
    if not qi or qi.quotation_id != quotation_id:
        raise HTTPException(404, "Item not found")
    apply_partial_update(qi, data, ["product_id", "quantity", "unit_price", "amount", "discount_rate", "remark", "sort_order"])
    db.commit()
    qt = db.get(Quotation, quotation_id)
    _recalc_total(qt, db)
    db.commit()
    db.refresh(qi)
    return {"item": _filter_quotation_items_cost([qi.to_dict()], user, db)[0]}


@router.delete("/quotations/{quotation_id}/items/{item_id}")
def delete_quotation_item(quotation_id: int, item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = get_or_404(db, Quotation, quotation_id, "Quotation not found")
    check_ownership(qt, user, strict=True)
    qi = db.get(QuotationItem, item_id)
    if not qi or qi.quotation_id != quotation_id:
        raise HTTPException(404, "Item not found")
    db.delete(qi)
    db.commit()
    _recalc_total(qt, db)
    db.commit()
    return {"ok": True}


# --- Export ---

@router.get("/quotations/{quotation_id}/export-xlsx")
def export_quotation_xlsx(quotation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = get_or_404(db, Quotation, quotation_id, "Quotation not found")
    check_ownership(qt, user, strict=True)
    # 成本可见性必须走 cost_visible（admin → 按用户三态覆盖 → 全局开关）。
    # 这里原来只读全局开关，会让「按用户单独放行/禁止成本」在导出路径上失效。
    show_cost = cost_visible(user, db)

    import openpyxl
    from app.utils.excel_style import (
        apply_info_row, apply_title_row, apply_header_row, apply_data_row,
        apply_total_row, apply_note_row, apply_footer_row, apply_column_widths,
        num_to_chinese_uppercase, NUM_FMT_CURRENCY, NUM_FMT_NUMBER, NUM_FMT_PERCENT,
        embed_image,
    )
    from datetime import date

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "报价单"
    apply_column_widths(ws, include_cost=show_cost)

    # Row 1: info row
    today = date.today().isoformat()
    project_name = ""
    if qt.solution_id:
        sol = db.get(Solution, qt.solution_id)
        if sol:
            project_name = sol.project_name or ""
    info_text = f"客户：{qt.client_name or ''}  |  项目：{project_name}  |  日期：{today}"
    apply_info_row(ws, 1, info_text)

    # Row 2: title
    title = qt.title or qt.quote_number or "报价单"
    apply_title_row(ws, 2, title)

    # Row 3: headers
    headers = ["序号", "名称", "规格型号", "型号", "功能描述", "单价", "数量", "合计", "折扣率", "成交价", "备注", "图片"]
    apply_header_row(ws, 3, headers)
    # 成本表头（M）：看不到成本时连表头都不写 —— 否则表格里留一个「成本」
    # 却整列空值，看起来像数据漏了
    if show_cost:
        ws.cell(row=3, column=13).value = "成本"

    # Data rows
    items = db.query(QuotationItem).filter_by(quotation_id=quotation_id)\
        .order_by(QuotationItem.sort_order).all()
    for idx, item in enumerate(items, 1):
        snap = item.product_snapshot or {}
        qty = float(item.quantity or 0)
        price = float(item.unit_price or 0)
        discount = discount_percent(item.discount_rate)
        row = 3 + idx
        formats = {6: NUM_FMT_CURRENCY, 7: NUM_FMT_NUMBER, 8: NUM_FMT_CURRENCY,
                   9: NUM_FMT_PERCENT, 10: NUM_FMT_CURRENCY}
        apply_data_row(ws, row, [
            idx,
            snap.get("name", ""),
            snap.get("model", "") or snap.get("sku", ""),
            snap.get("model", ""),
            format_description_with_specs((snap.get("description", "") or ""), snap.get("specs", {})),
            price,
            qty,
            price * qty,  # H placeholder, replaced by formula below
            discount / 100,  # I: 折扣率(小数)
            price * qty * (discount / 100),  # J placeholder
            item.remark or "",
            "",
        ], formats)
        # 成本列（M）：无权限时不创建该单元格
        if show_cost:
            ws.cell(row=row, column=13).value = float(snap.get("cost_price", 0) or 0)
        # Replace H and J with formulas
        ws.cell(row=row, column=8).value = f"=F{row}*G{row}"       # H: 合计 = 单价 × 数量
        ws.cell(row=row, column=10).value = f"=H{row}*I{row}"      # J: 成交价 = 合计 × 折扣率

        # Embed product image in column L
        img_url = snap.get("image_url", "")
        # Fallback: look up product's actual image_url if snapshot lost it
        if not img_url and item.product_id:
            prod = db.get(Product, item.product_id)
            if prod and prod.image_url:
                img_url = prod.image_url
        if img_url:
            import os
            from app.services.storage import UPLOAD_DIR
            if not embed_image(ws, row, 12, img_url, str(UPLOAD_DIR)):
                import logging; logging.getLogger("uvicorn").warning(f"Failed to embed image for quotation item at row {row}: {img_url}")

    # Total row
    total_row = 3 + len(items) + 1
    total_amount = float(qt.total_amount or 0)
    apply_total_row(ws, total_row, f"合计（大写）：{num_to_chinese_uppercase(total_amount)}", col_letter="J")

    # Note row —— 明确「含税」口径：报价单价、成本价都是含税价，合计就是各小计之和，
    # **不要再乘税率**（历史口径即如此，13% 只是说明文字）
    apply_note_row(
        ws, total_row + 1,
        f"注：本报价单有效期 {qt.valid_days or 30} 天；价格为含税价（含 {_fmt_rate(qt.tax_rate)}% 增值税）。",
    )

    # Footer row
    apply_footer_row(ws, total_row + 2, f"报价单编号：{qt.quote_number or ''}  |  {user.username}")

    # Log download
    from app.models.download_log import DownloadLog
    log = DownloadLog(user_id=user.id, file_type="quotation", entity_id=quotation_id, ip_address="")
    db.add(log)
    # 原子自增：读-改-写并发下会丢计数
    db.execute(
        update(Quotation).where(Quotation.id == quotation_id)
        .values(download_count=func.coalesce(Quotation.download_count, 0) + 1)
    )
    db.commit()

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    # 文件名只用「编号 + 标题」：编号本身以 QT（quotation）开头，类型信息已含在编号里，
    # 再写一遍「报价单_」是冗余；客户信息本来也写在标题里（见 R43）
    from app.utils.helpers import attachment_disposition, safe_filename_part
    filename = "_".join(p for p in [
        safe_filename_part(qt.quote_number, f"id{quotation_id}"),
        safe_filename_part(qt.title),
    ] if p) + ".xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": attachment_disposition(filename, f"quotation_{quotation_id}.xlsx")},
    )


# --- Quotation BOM Editor ---

@router.get("/quotations/{quotation_id}/bom")
def get_quotation_bom(quotation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = get_or_404(db, Quotation, quotation_id, "Quotation not found")
    check_ownership(qt, user, strict=True)
    items = db.query(QuotationItem).filter_by(quotation_id=quotation_id)\
        .order_by(QuotationItem.sort_order).all()
    rows = []
    hide_cost = not cost_visible(user, db)
    for idx, item in enumerate(items):
        snap = item.product_snapshot or {}
        rows.append({
            "name": snap.get("name", ""),
            "sku": snap.get("sku", ""),
            "model": snap.get("model", ""),
            "description": (snap.get("description", "") or "")[:200],
            "qty": float(item.quantity or 0),
            "price": float(item.unit_price or 0),
            "discount": discount_percent(item.discount_rate),
            "remark": item.remark or "",
            "cost": None if hide_cost else float(snap.get("cost_price", 0) or 0),
        })
    return {"rows": rows, "total": float(qt.total_amount or 0)}


@router.put("/quotations/{quotation_id}/bom")
def save_quotation_bom(quotation_id: int, data: QuotationBOMSave, db: Session = Depends(get_db), user=Depends(get_current_user)):
    qt = get_or_404(db, Quotation, quotation_id, "Quotation not found")
    check_ownership(qt, user, strict=True)
    rows = data.rows
    can_see_cost = cost_visible(user, db)
    # Preserve old data that BOM editor doesn't carry
    # 旧行按「SKU 优先、位置兜底」匹配：原来只用 sort_order（假定等于行号），
    # 而条目不一定有 sort_order（直接调条目接口创建时为 NULL）→ 匹配不到，
    # specs/image_url/厂商 与成本都保不下来。
    old_items = (db.query(QuotationItem)
                 .filter_by(quotation_id=quotation_id)
                 .order_by(QuotationItem.sort_order, QuotationItem.id).all())
    old_by_sku = {}
    for qi in old_items:
        sku = ((qi.product_snapshot or {}).get("sku") or "").strip()
        if sku:
            old_by_sku.setdefault(sku, qi)
    try:
        db.query(QuotationItem).filter_by(quotation_id=quotation_id).delete()
        for idx, row in enumerate(rows):
            sku = (row.sku or "").strip()
            old_item = old_by_sku.get(sku) if sku else None
            if old_item is None and idx < len(old_items):
                old_item = old_items[idx]
            old_snap = (old_item.product_snapshot or {}) if old_item else {}
            snap = {"name": row.name or "", "sku": row.sku or "",
                    "model": row.model or "", "description": row.description or ""}
            if can_see_cost:
                snap["cost_price"] = float(row.cost or 0)
            elif "cost_price" in old_snap:
                # 看不到成本的用户不得改写成本：前端读到的是被裁掉的 cost（None），
                # 原样采信会把快照里的成本抹成 0 —— 成本以服务端已有值为准
                snap["cost_price"] = old_snap["cost_price"]
            for key in ("specs", "image_url", "manufacturer_name", "category_name"):
                if old_snap.get(key):
                    snap[key] = old_snap[key]
            pid = old_item.product_id if old_item else None
            # 数量 0 是合法值（本次不采购但保留该行），只有空/脏数据才回退默认值 ——
            # 历史写法 `float(row.get("qty", 1) or 1)` 会把 0 悄悄改成 1（R50）
            qty = number_or(row.qty, 1)
            price = number_or(row.price, 0)
            qi = QuotationItem(
                quotation_id=quotation_id,
                product_id=pid,
                product_snapshot=snap,
                quantity=qty,
                unit_price=price,
                amount=qty * price * (discount_percent(row.discount) / 100),
                discount_rate=discount_percent(row.discount),
                remark=str(row.remark or ""),
                sort_order=idx + 1,
            )
            db.add(qi)
        db.flush()
        _recalc_total(qt, db)
        db.commit()
    except Exception as e:
        db.rollback()
        # 原始异常必须留痕：此前直接丢弃，只剩一句通用 500 文案，排障时无从下手
        logging.getLogger("uvicorn").warning("BOM 回写方案明细失败: %s", e, exc_info=True)
        raise HTTPException(500, "BOM 保存失败，请重试")
    return {"ok": True, "total": float(qt.total_amount or 0)}
