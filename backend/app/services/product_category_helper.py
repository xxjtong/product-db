"""Shared helpers for product_categories many-to-many table — replaces raw SQL scattered across routers."""
from __future__ import annotations
from sqlalchemy import text, table, column, select
from sqlalchemy.orm import Session

_product_categories = table('product_categories',
    column('product_id'),
    column('category_id'),
)


def add_product_categories(db: Session, product_id: int, category_ids: list[int]):
    """Replace all category assignments for a product."""
    db.execute(text('DELETE FROM product_categories WHERE product_id = :pid'), {'pid': product_id})
    for cid in category_ids:
        db.execute(text('INSERT OR IGNORE INTO product_categories (product_id, category_id) VALUES (:pid, :cid)'),
                   {'pid': product_id, 'cid': cid})


def get_product_category_ids(db: Session, product_id: int) -> list[int]:
    """Get category IDs for a single product."""
    rows = db.execute(text('SELECT category_id FROM product_categories WHERE product_id = :pid'), {'pid': product_id}).fetchall()
    return [r[0] for r in rows]


def get_product_category_map(db: Session, product_ids: list[int] | None = None) -> dict[int, list[int]]:
    """Get {product_id: [category_ids]} map. If product_ids is None, loads all."""
    if product_ids is not None and not product_ids:
        return {}
    if product_ids is not None:
        # Build parameterized IN clause
        placeholders = ','.join(f':pid{i}' for i in range(len(product_ids)))
        rows = db.execute(text(
            f'SELECT product_id, category_id FROM product_categories WHERE product_id IN ({placeholders})'
        ), {f'pid{i}': pid for i, pid in enumerate(product_ids)}).fetchall()
    else:
        rows = db.execute(text('SELECT product_id, category_id FROM product_categories')).fetchall()
    result: dict[int, list[int]] = {}
    for pid, cid in rows:
        result.setdefault(pid, []).append(cid)
    return result


def delete_category_cascade(db: Session, category_id: int):
    """Remove all product_categories rows for a given category."""
    db.execute(text('DELETE FROM product_categories WHERE category_id = :cid'), {'cid': category_id})


def get_products_in_categories(db: Session, category_ids: list[int]) -> list[int]:
    """Get distinct product IDs that belong to any of the given categories."""
    if not category_ids:
        return []
    pc = _product_categories
    rows = db.execute(
        select(pc.c.product_id).where(pc.c.category_id.in_(category_ids)).distinct()
    ).fetchall()
    return [r[0] for r in rows]


def get_category_descendants(db: Session, parent_id: int) -> list[int]:
    """Get all descendant category IDs (batch-loaded, no recursion N+1).

    带 visited 兜底：若库中已存在父子成环（历史数据或并发写入造成），递归会无限下去
    直到 RecursionError → 500。命中已访问节点就直接剪枝（R56）。
    """
    from app.models.category import Category
    all_cats = db.query(Category).all()
    children_map: dict = {}
    for c in all_cats:
        children_map.setdefault(c.parent_id, []).append(c.id)

    visited: set = set()

    def _walk(pid):
        if pid in visited:
            return []
        visited.add(pid)
        ids = [pid]
        for child_id in children_map.get(pid, []):
            ids.extend(_walk(child_id))
        return ids
    return _walk(parent_id)


def would_create_category_cycle(db: Session, category_id: int, new_parent_id: int | None) -> bool:
    """把 category_id 的父级改成 new_parent_id 会不会成环。

    成环的两种情况：父级设成自己，或父级落在自己的后代集合里（那样会形成闭环，
    之后任何一次「取后代」都会递归到崩溃）。R56。
    """
    if new_parent_id is None:
        return False
    if new_parent_id == category_id:
        return True
    return new_parent_id in get_category_descendants(db, category_id)
