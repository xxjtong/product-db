"""Field visibility — controls which fields are visible to non-admin users."""
import time
from sqlalchemy.orm import Session
from app.models.field_setting import FieldSetting

_cache: dict = {"data": None, "ts": 0}
_CACHE_TTL = 30  # seconds


def get_field_visibility(db: Session) -> dict:
    """Return {field_name: bool} dict, cached for 30s."""
    global _cache
    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["data"]

    settings = db.query(FieldSetting).all()
    _cache["data"] = {s.field_name: s.user_visible for s in settings}
    _cache["ts"] = now
    return _cache["data"]


def filter_fields_for_user(data: dict, is_admin: bool, db: Session = None) -> dict:
    """Set invisible fields to None for non-admin users."""
    if is_admin:
        return data
    if db is None:
        return data
    visibility = get_field_visibility(db)
    for field_name, visible in visibility.items():
        if not visible and field_name in data:
            data[field_name] = None
    return data
