"""Solution (BOM) CRUD + dependency check + suggest."""
from __future__ import annotations
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from app.database import get_db
from app.utils.helpers import get_or_404, apply_partial_update
from app.models.solution import Solution, SolutionItem
from app.models.product import Product
from app.models.category import Category
from app.models.dependency import ProductDependency
from app.auth import get_current_user, filter_by_ownership, check_ownership
from app.utils.escape import escape_like
from app.models.user import User
from app.schemas.solution import SolutionCreate, SolutionUpdate, SolutionItemCreate, SolutionItemUpdate, BatchDeleteRequest
from datetime import datetime, timezone

router = APIRouter()


def _recalc_totals(sol: Solution, db: Session):
    """Recalculate solution total_cost and total_price from items."""
    items = db.query(SolutionItem).options(
        selectinload(SolutionItem.product),
    ).filter_by(solution_id=sol.id).all()
    total_cost = 0
    total_price = 0
    for item in items:
        qty = float(item.quantity or 0)
        price = float(item.unit_price or 0)
        rate = float(item.discount_rate or 100)
        total_cost += qty * (float(item.product.cost_price or 0) if item.product else 0)
        total_price += qty * price * (rate / 100)
    sol.total_cost = total_cost
    sol.total_price = total_price


@router.get("/solutions")
def list_solutions(
    status: Optional[str] = None,
    search: str = "",
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    q = db.query(Solution).options(
        selectinload(Solution.items).selectinload(SolutionItem.product),
    )
    q = filter_by_ownership(q, Solution, user, strict=True)
    if status:
        q = q.filter(Solution.status == status)
    if search:
        q = q.filter(
            Solution.name.ilike(f"%{escape_like(search)}%")
            | Solution.client_name.ilike(f"%{escape_like(search)}%")
            | Solution.project_name.ilike(f"%{escape_like(search)}%")
        )
    from app.utils.helpers import paginate
    solutions, total = paginate(q.order_by(Solution.updated_at.desc()), page, per_page)
    return {
        "solutions": [s.to_dict() for s in solutions],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/solutions/batch-delete")
def batch_delete_solutions(data: BatchDeleteRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not data.ids:
        raise HTTPException(400, "ids is required")
    if user.role != "admin":
        owned = db.query(Solution.id).filter(
            Solution.id.in_(data.ids),
            Solution.created_by == user.id,
        ).all()
        owned_ids = {r[0] for r in owned}
        forbidden = [i for i in data.ids if i not in owned_ids]
        if forbidden:
            raise HTTPException(403, f"Access denied for solutions: {forbidden}")
    deleted = db.query(Solution).filter(Solution.id.in_(data.ids)).delete(synchronize_session="fetch")
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.post("/solutions", status_code=201)
def create_solution(data: SolutionCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = Solution(
        name=data.name,
        description=data.description,
        client_name=data.client_name,
        project_name=data.project_name,
        status=data.status,
        notes=data.notes,
        created_by=user.id,
    )
    db.add(sol)
    db.commit()
    db.refresh(sol)
    return {"solution": sol.to_dict()}


@router.get("/solutions/{solution_id}")
def get_solution(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = db.scalar(select(Solution).options(
        selectinload(Solution.items).selectinload(SolutionItem.product),
    ).where(Solution.id == solution_id))
    if not sol:
        raise HTTPException(404, "Solution not found")
    check_ownership(sol, user, strict=True)
    return {"solution": sol.to_dict()}


@router.put("/solutions/{solution_id}")
def update_solution(solution_id: int, data: SolutionUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = get_or_404(db, Solution, solution_id, "Solution not found")
    check_ownership(sol, user, strict=True)
    apply_partial_update(sol, data, ["name", "description", "client_name", "project_name", "status", "notes"])
    sol.updated_at = datetime.now(timezone.utc)
    db.commit()
    sol = db.scalar(select(Solution).options(
        selectinload(Solution.items).selectinload(SolutionItem.product),
    ).where(Solution.id == solution_id))
    return {"solution": sol.to_dict()}


@router.delete("/solutions/{solution_id}")
def delete_solution(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = get_or_404(db, Solution, solution_id, "Solution not found")
    check_ownership(sol, user, strict=True)
    db.delete(sol)
    db.commit()
    return {"ok": True}


# --- Solution Items ---

@router.get("/solutions/{solution_id}/items")
def list_items(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = get_or_404(db, Solution, solution_id, "Solution not found")
    check_ownership(sol, user, strict=True)
    items = db.query(SolutionItem).options(
        selectinload(SolutionItem.product),
    ).filter_by(solution_id=solution_id)\
        .order_by(SolutionItem.sort_order).all()
    return {"items": [i.to_dict() for i in items]}


@router.post("/solutions/{solution_id}/items", status_code=201)
def add_item(solution_id: int, data: SolutionItemCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = get_or_404(db, Solution, solution_id, "Solution not found")
    check_ownership(sol, user, strict=True)
    product = db.get(Product, data.product_id)
    if not product:
        raise HTTPException(400, "Product not found")

    item = SolutionItem(
        solution_id=solution_id,
        product_id=data.product_id,
        quantity=data.quantity,
        unit_price=data.unit_price if data.unit_price is not None else (
            float(product.base_price) if product.base_price else None
        ),
        discount_rate=data.discount_rate,
        remark=data.remark,
        sort_order=data.sort_order,
    )
    db.add(item)
    db.commit()
    _recalc_totals(sol, db)
    db.commit()
    db.refresh(item)
    return {"item": item.to_dict()}


@router.put("/solutions/{solution_id}/items/{item_id}")
def update_item(solution_id: int, item_id: int, data: SolutionItemUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = get_or_404(db, Solution, solution_id, "Solution not found")
    check_ownership(sol, user, strict=True)
    item = db.get(SolutionItem, item_id)
    if not item or item.solution_id != solution_id:
        raise HTTPException(404, "Item not found")
    apply_partial_update(item, data, ["product_id", "quantity", "unit_price", "discount_rate", "remark", "sort_order"])
    db.commit()
    sol = db.get(Solution, solution_id)
    _recalc_totals(sol, db)
    db.commit()
    db.refresh(item)
    return {"item": item.to_dict()}


@router.delete("/solutions/{solution_id}/items/{item_id}")
def delete_item(solution_id: int, item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = get_or_404(db, Solution, solution_id, "Solution not found")
    check_ownership(sol, user, strict=True)
    item = db.get(SolutionItem, item_id)
    if not item or item.solution_id != solution_id:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()
    _recalc_totals(sol, db)
    db.commit()
    return {"ok": True}


# --- Dependency Check ---

@router.get("/solutions/{solution_id}/check")
def check_solution(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Check solution completeness: find unmet required dependencies."""
    sol = get_or_404(db, Solution, solution_id, "Solution not found")
    check_ownership(sol, user, strict=True)

    items = db.query(SolutionItem).filter_by(solution_id=solution_id).all()
    solution_product_ids = {i.product_id for i in items}
    solution_products = db.query(Product).filter(Product.id.in_(solution_product_ids)).all()
    solution_category_ids = {p.category_id for p in solution_products}

    # Preload all dependencies for products in solution
    all_deps = db.query(ProductDependency).filter(
        ProductDependency.product_id.in_(solution_product_ids),
        ProductDependency.dependency_type == "required",
    ).all()
    deps_by_product: dict = {}
    for d in all_deps:
        deps_by_product.setdefault(d.product_id, []).append(d)

    # Preload missing target products and categories
    missing_ids = {d.depends_on_product_id for d in all_deps if d.depends_on_product_id and d.depends_on_product_id not in solution_product_ids}
    missing_cat_ids = {d.depends_on_category_id for d in all_deps if d.depends_on_category_id and d.depends_on_category_id not in solution_category_ids}
    product_map = {p.id: p for p in db.query(Product).filter(Product.id.in_(missing_ids)).all()} if missing_ids else {}
    cat_map = {c.id: c for c in db.query(Category).filter(Category.id.in_(missing_cat_ids)).all()} if missing_cat_ids else {}

    warnings = []
    for item in items:
        deps = deps_by_product.get(item.product_id, [])
        for dep in deps:
            if dep.depends_on_product_id and dep.depends_on_product_id not in solution_product_ids:
                target = product_map.get(dep.depends_on_product_id)
                warnings.append({
                    "type": "missing_product",
                    "product_id": item.product_id,
                    "depends_on_product_id": dep.depends_on_product_id,
                    "target_name": target.name if target else "Unknown",
                    "description": dep.description or "",
                })
            if dep.depends_on_category_id and dep.depends_on_category_id not in solution_category_ids:
                cat = cat_map.get(dep.depends_on_category_id)
                warnings.append({
                    "type": "missing_category",
                    "product_id": item.product_id,
                    "depends_on_category_id": dep.depends_on_category_id,
                    "target_name": cat.name if cat else "Unknown",
                    "description": dep.description or "",
                })

    return {"warnings": warnings, "ok": len(warnings) == 0}


@router.get("/solutions/{solution_id}/suggest")
def suggest_solution(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Suggest products to fulfill unmet dependencies."""
    sol = get_or_404(db, Solution, solution_id, "Solution not found")
    check_ownership(sol, user, strict=True)

    items = db.query(SolutionItem).filter_by(solution_id=solution_id).all()
    solution_product_ids = {i.product_id for i in items}
    solution_products = db.query(Product).filter(Product.id.in_(solution_product_ids)).all()
    solution_category_ids = {p.category_id for p in solution_products}

    # Preload categories for name lookup
    cat_map = {c.id: c for c in db.query(Category).all()}

    suggestions = []
    seen = set()
    for item in items:
        deps = db.query(ProductDependency).filter_by(product_id=item.product_id, dependency_type="required").all()
        for dep in deps:
            if dep.depends_on_category_id and dep.depends_on_category_id not in solution_category_ids:
                if dep.depends_on_category_id in seen:
                    continue
                seen.add(dep.depends_on_category_id)
                candidates = db.query(Product).options(
                    selectinload(Product.manufacturer),
                ).filter_by(category_id=dep.depends_on_category_id, status="active").all()
                cat = cat_map.get(dep.depends_on_category_id)
                suggestions.append({
                    "missing_category": cat.name if cat else "Unknown",
                    "category_id": dep.depends_on_category_id,
                    "products": [
                        {"id": p.id, "name": p.name, "model": p.model or "", "sku": p.sku or "",
                         "manufacturer_name": p.manufacturer.name if p.manufacturer else "",
                         "base_price": float(p.base_price or 0),
                         "max_endpoints": (p.specs or {}).get("max_endpoints")}
                        for p in candidates[:10]
                    ],
                })

    return {"suggestions": suggestions}
