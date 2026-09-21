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


def cost_visible(user, db: Session) -> bool:
    """成本价可见性的**唯一判定入口**。

    产品列表/详情/导出、方案、报价单、BOM 模板的所有成本出口都必须走这里 ——
    此前各路由各写一套（products 里直接读全局、quotations 有 `_should_hide_cost`、
    bom_templates 有 `_cost_visible`），漏改一处就等于成本泄漏。

    admin 恒可见；其他用户看全局字段开关。按用户覆盖（users.can_view_cost）
    只需改这一个函数。
    """
    if getattr(user, "role", "") == "admin":
        return True
    return bool(get_field_visibility(db).get("cost_price", True))


# 序列化结果里所有与成本相关的键名 —— 少列一个就是漏一个出口
_COST_KEYS = ("cost_price", "product_cost_price", "total_cost")


def hide_cost_in(data, user, db: Session):
    """按权限裁掉序列化结果里的成本字段（就地修改并返回）

    - `cost_price`：产品字段、报价单条目快照
    - `product_cost_price`：方案条目的产品成本
    - `total_cost`：方案汇总成本

    带 `items` 的结果会一并处理一层子项（方案 → 方案条目）。
    """
    if not isinstance(data, dict) or cost_visible(user, db):
        return data
    for key in _COST_KEYS:
        data.pop(key, None)
    for item in data.get("items") or []:
        if isinstance(item, dict):
            for key in _COST_KEYS:
                item.pop(key, None)
    return data
