"""Shared utility helpers for route handlers."""
from fastapi import HTTPException
from sqlalchemy.orm import Session


def apply_partial_update(obj, data, fields: list[str]):
    """Apply non-None values from data (dict or Pydantic model) to obj for given fields."""
    for f in fields:
        val = data.get(f) if isinstance(data, dict) else getattr(data, f, None)
        if val is not None:
            setattr(obj, f, val)


def get_or_404(db: Session, model, obj_id: int, detail: str = "Not found"):
    """Get a single object by ID or raise 404."""
    obj = db.get(model, obj_id)
    if not obj:
        raise HTTPException(404, detail)
    return obj


def paginate(query, page: int = 1, per_page: int = 20):
    """Return (items, total, page, per_page) from a SQLAlchemy query."""
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total
