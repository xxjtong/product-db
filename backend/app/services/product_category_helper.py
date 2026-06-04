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
        rows = db.execute(text(
            'SELECT product_id, category_id FROM product_categories WHERE product_id IN (SELECT id FROM products WHERE status=:s)'
        ), {'s': 'active'}).fetchall()
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
