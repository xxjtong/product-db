"""报价单创建 —— 唯一实现（REST / AI 工具 / Hermes 共用）。

此前「创建报价单」有**两套并行实现**：`POST /quotations` 一份（快照取完整
`prod.to_dict()`、编号冲突回 409），`ai_tools.execute_tool("create_quotation")`
另一份（快照只有 name/model/sku、无冲突处理，还会在用户没确认时就把 AI 猜的
产品写进方案）。两者只有编号生成是共用的 —— 结果是 AI 建的报价单导出时
「功能描述」列缺规格参数，与主流程产出的报价单不一致。

现在收敛到这里，调用方只负责鉴权与参数拼装：

- 路由 `POST /quotations` → `create_quotation_from_solution`
- AI 工具 `create_quotation` → `preview_quotation`（**只算不写**，等用户点确认）
- Hermes agent → 按 prompt 调 `POST /quotations`，天然复用本模块
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.quotation import Quotation, QuotationItem
from app.models.solution import Solution, SolutionItem
from app.utils.helpers import discount_percent


def _next_quote_number(db: Session) -> str:
    """报价单号 QT-YYYYMMDD-NNN：取当天**已用编号的最大序号 +1**。

    早前是按 id 倒序取最后一条再 +1 —— 当天编号一旦出现乱序（手工改号、删单后重建）
    就会取到已存在的号并撞唯一约束。取号本身不带锁（SQLite 不支持
    `SELECT ... FOR UPDATE`），真正的并发冲突由调用方捕获 IntegrityError 回 409 兜底。
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"QT-{today}-"
    max_seq = 0
    rows = db.query(Quotation.quote_number).filter(Quotation.quote_number.like(f"{prefix}%")).all()
    for (num,) in rows:
        try:
            max_seq = max(max_seq, int(str(num).split("-")[-1]))
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_seq + 1:03d}"


def _as_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _full_snapshot(db: Session, product_id: int) -> dict:
    """产品快照取**完整** `to_dict()`（含 specs / 图片 / 成本），与主流程一致。

    成本进快照是既有设计：出口（列表 / 详情 / BOM / 导出）一律按 `cost_visible`
    裁剪，写入口不必也不该在这里判断。
    """
    p = db.query(Product).options(
        selectinload(Product.category),
        selectinload(Product.manufacturer),
        selectinload(Product.supplier),
        selectinload(Product.comm_methods),
        selectinload(Product.comm_protocols),
        selectinload(Product.power_supplies),
        selectinload(Product.hardware_interfaces),
        selectinload(Product.sensor_capabilities),
        selectinload(Product.images),
    ).filter(Product.id == product_id).first()
    return p.to_dict() if p else {}


def resolve_items(db: Session, solution_id: int, extra_items: Optional[list] = None):
    """算出「将要进入报价单」的条目，以及需要新并入方案的产品。

    `extra_items` 形如 `[{"product_id": 1, "quantity": 2}]` —— 尚未进方案的产品
    （AI 建议、外部调用方指定）。方案里已有的产品**不重复添加、不改数量**，只补缺的。

    返回 `(items, added)`：
    - items：每项 {product_id, quantity, unit_price, discount_rate, remark,
      solution_item_id, snapshot(none 表示待取)}
    - added：本次需要写入 `solution_items` 的条目
    """
    rows = db.query(SolutionItem).filter_by(solution_id=solution_id).all()
    seen = {si.product_id for si in rows}
    items: list = []
    added: list = []

    for si in sorted(rows, key=lambda x: (x.sort_order or 0, x.id)):
        items.append({
            "product_id": si.product_id,
            "quantity": float(si.quantity or 0),
            "unit_price": float(si.unit_price or 0),
            "discount_rate": discount_percent(si.discount_rate),
            "remark": si.remark or "",
            "solution_item_id": si.id,
        })

    for raw in (extra_items or []):
        if not isinstance(raw, dict):
            continue
        pid = _as_int(raw.get("product_id"))
        if pid is None or pid in seen:
            continue
        p = db.get(Product, pid)
        if not p:
            continue
        seen.add(pid)
        qty = float(raw.get("quantity") or 1)
        unit = float(p.base_price or 0)
        items.append({
            "product_id": pid,
            "quantity": qty,
            "unit_price": unit,
            "discount_rate": 100.0,
            "remark": "",
            "solution_item_id": None,
        })
        added.append({"product_id": pid, "quantity": qty, "unit_price": unit,
                      "name": p.name, "model": p.model or ""})

    return items, added


def _amount(item: dict) -> float:
    return item["quantity"] * item["unit_price"] * (item["discount_rate"] / 100)


def preview_quotation(db: Session, solution: Solution, extra_items: Optional[list] = None) -> dict:
    """算出「将要创建的报价单」长什么样，**不写库**。

    这是 AI 工具的输出：用户要先看到具体内容（含将被并入方案的产品）再决定是否生成，
    而不是让模型直接落库、事后才告知。
    """
    items, added = resolve_items(db, solution.id, extra_items)
    pids = [it["product_id"] for it in items]
    pmap = {p.id: p for p in db.query(Product).filter(Product.id.in_(pids)).all()} if pids else {}

    preview_items = []
    for it in items:
        p = pmap.get(it["product_id"])
        preview_items.append({
            "product_id": it["product_id"],
            "name": (p.name if p else "") or "",
            "model": (p.model if p else "") or "",
            "quantity": it["quantity"],
            "unit_price": it["unit_price"],
            "amount": _amount(it),
        })

    return {
        "solution_id": solution.id,
        "title": solution.name or "",
        "client_name": solution.client_name or "",
        "project_name": solution.project_name or "",
        "items": preview_items,
        "new_items": added,     # 确认时会一并并入方案
        "total": sum(x["amount"] for x in preview_items),
        "count": len(preview_items),
    }


def create_quotation_from_solution(
    db: Session,
    solution: Optional[Solution],
    user,
    *,
    title: Optional[str] = None,
    client_name: Optional[str] = None,
    client_contact: Optional[str] = None,
    valid_days: int = 15,
    tax_rate: float = 13,
    status: str = "draft",
    notes: Optional[str] = None,
    extra_items: Optional[list] = None,
) -> Quotation:
    """把方案（+ `extra_items` 中尚未入方案的产品）落成报价单。

    `solution` 可以为 None —— 那就是一张不挂方案的空白报价单（既有用法，不复制条目）。

    **不 commit**：调用方统一提交，好把「并入方案 + 建单 + 建条目」放在同一事务里，
    失败时不会留下半个状态。编号冲突（IntegrityError）也由调用方决定怎么回。
    """
    items: list = []
    added: list = []
    if solution is not None:
        items, added = resolve_items(db, solution.id, extra_items)
        # 新并入方案的产品：用户在预览里看到过这些行才会走到这里
        for a in added:
            db.add(SolutionItem(solution_id=solution.id, product_id=a["product_id"],
                                quantity=a["quantity"], unit_price=a["unit_price"]))
        if added:
            db.flush()

    qt = Quotation(
        solution_id=solution.id if solution else None,
        quote_number=_next_quote_number(db),
        title=title or (solution.name if solution else "") or "",
        client_name=client_name or (solution.client_name if solution else "") or "",
        client_contact=client_contact or "",
        valid_days=valid_days,
        tax_rate=tax_rate,
        status=status,
        notes=notes,
        created_by=user.id,
    )
    db.add(qt)
    db.flush()   # 取 qt.id

    total = 0.0
    for idx, it in enumerate(items, 1):
        amount = _amount(it)
        total += amount
        db.add(QuotationItem(
            quotation_id=qt.id,
            solution_item_id=it["solution_item_id"],
            product_id=it["product_id"],
            product_snapshot=_full_snapshot(db, it["product_id"]),
            quantity=it["quantity"],
            unit_price=it["unit_price"],
            amount=amount,
            discount_rate=it["discount_rate"],
            remark=it["remark"],
            sort_order=idx,
        ))
    qt.total_amount = total
    return qt
