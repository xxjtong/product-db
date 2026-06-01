"""Solution (BOM) CRUD + dependency check + suggest."""
from __future__ import annotations
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.solution import Solution, SolutionItem
from app.models.product import Product
from app.models.category import Category
from app.models.dependency import ProductDependency
from app.auth import get_current_user
from app.models.user import User
from datetime import datetime

router = APIRouter()


def _recalc_totals(sol: Solution, db: Session):
    """Recalculate solution total_cost and total_price from items."""
    items = db.query(SolutionItem).filter_by(solution_id=sol.id).all()
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
    q = db.query(Solution)
    if status:
        q = q.filter(Solution.status == status)
    if search:
        q = q.filter(
            Solution.name.ilike(f"%{search}%")
            | Solution.client_name.ilike(f"%{search}%")
            | Solution.project_name.ilike(f"%{search}%")
        )
    total = q.count()
    solutions = q.order_by(Solution.updated_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "solutions": [s.to_dict() for s in solutions],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/solutions")
def create_solution(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = Solution(
        name=data["name"],
        description=data.get("description"),
        client_name=data.get("client_name"),
        project_name=data.get("project_name"),
        status=data.get("status", "draft"),
        notes=data.get("notes"),
        created_by=user.id,
    )
    db.add(sol)
    db.commit()
    db.refresh(sol)
    return {"solution": sol.to_dict()}


@router.get("/solutions/{solution_id}")
def get_solution(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")
    product_map = {p.id: p.name for p in db.query(Product).all()}
    return {"solution": sol.to_dict(product_map)}


@router.put("/solutions/{solution_id}")
def update_solution(solution_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")
    for f in ["name", "description", "client_name", "project_name", "status", "notes"]:
        if f in data:
            setattr(sol, f, data[f])
    sol.updated_at = datetime.now()
    db.commit()
    product_map = {p.id: p.name for p in db.query(Product).all()}
    return {"solution": sol.to_dict(product_map)}


@router.delete("/solutions/{solution_id}")
def delete_solution(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")
    db.delete(sol)
    db.commit()
    return {"ok": True}


# --- Solution Items ---

@router.get("/solutions/{solution_id}/items")
def list_items(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")
    product_map = {p.id: p.name for p in db.query(Product).all()}
    items = db.query(SolutionItem).filter_by(solution_id=solution_id)\
        .order_by(SolutionItem.sort_order).all()
    return {"items": [i.to_dict(product_map) for i in items]}


@router.post("/solutions/{solution_id}/items")
def add_item(solution_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")
    product = db.get(Product, data["product_id"])
    if not product:
        raise HTTPException(400, "Product not found")

    item = SolutionItem(
        solution_id=solution_id,
        product_id=data["product_id"],
        quantity=data.get("quantity", 1),
        unit_price=data.get("unit_price", float(product.base_price or 0)),
        discount_rate=data.get("discount_rate", 100),
        remark=data.get("remark"),
        sort_order=data.get("sort_order", 0),
    )
    db.add(item)
    db.commit()
    _recalc_totals(sol, db)
    db.commit()
    product_map = {p.id: p.name for p in db.query(Product).all()}
    db.refresh(item)
    return {"item": item.to_dict(product_map)}


@router.put("/solutions/{solution_id}/items/{item_id}")
def update_item(solution_id: int, item_id: int, data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.get(SolutionItem, item_id)
    if not item or item.solution_id != solution_id:
        raise HTTPException(404, "Item not found")
    for f in ["product_id", "quantity", "unit_price", "discount_rate", "remark", "sort_order"]:
        if f in data:
            setattr(item, f, data[f])
    db.commit()
    sol = db.get(Solution, solution_id)
    _recalc_totals(sol, db)
    db.commit()
    product_map = {p.id: p.name for p in db.query(Product).all()}
    db.refresh(item)
    return {"item": item.to_dict(product_map)}


@router.delete("/solutions/{solution_id}/items/{item_id}")
def delete_item(solution_id: int, item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.get(SolutionItem, item_id)
    if not item or item.solution_id != solution_id:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()
    sol = db.get(Solution, solution_id)
    _recalc_totals(sol, db)
    db.commit()
    return {"ok": True}


# --- Dependency Check ---

@router.get("/solutions/{solution_id}/check")
def check_solution(solution_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Check solution completeness: find unmet required dependencies."""
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")

    items = db.query(SolutionItem).filter_by(solution_id=solution_id).all()
    solution_product_ids = {i.product_id for i in items}
    solution_category_ids = set()
    for pid in solution_product_ids:
        p = db.get(Product, pid)
        if p:
            solution_category_ids.add(p.category_id)

    warnings = []
    for item in items:
        deps = db.query(ProductDependency).filter_by(product_id=item.product_id, dependency_type="required").all()
        for dep in deps:
            if dep.depends_on_product_id and dep.depends_on_product_id not in solution_product_ids:
                target = db.get(Product, dep.depends_on_product_id)
                warnings.append({
                    "type": "missing_product",
                    "product_id": item.product_id,
                    "depends_on_product_id": dep.depends_on_product_id,
                    "target_name": target.name if target else "Unknown",
                    "description": dep.description or "",
                })
            if dep.depends_on_category_id and dep.depends_on_category_id not in solution_category_ids:
                cat = db.get(Category, dep.depends_on_category_id)
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
    sol = db.get(Solution, solution_id)
    if not sol:
        raise HTTPException(404, "Solution not found")

    items = db.query(SolutionItem).filter_by(solution_id=solution_id).all()
    solution_product_ids = {i.product_id for i in items}
    solution_category_ids = set()
    for pid in solution_product_ids:
        p = db.get(Product, pid)
        if p:
            solution_category_ids.add(p.category_id)

    suggestions = []
    seen = set()
    for item in items:
        deps = db.query(ProductDependency).filter_by(product_id=item.product_id, dependency_type="required").all()
        for dep in deps:
            if dep.depends_on_category_id and dep.depends_on_category_id not in solution_category_ids:
                if dep.depends_on_category_id in seen:
                    continue
                seen.add(dep.depends_on_category_id)
                candidates = db.query(Product).filter_by(category_id=dep.depends_on_category_id, status="active").all()
                cat = db.get(Category, dep.depends_on_category_id)
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
