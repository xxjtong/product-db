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


def apply_field_visibility(data: dict, user, db: Session) -> dict:
    """按用户裁掉序列化结果里不可见的字段（产品数据的统一入口）。

    - **成本**：走 `cost_visible()`（admin → 按用户覆盖 → 全局开关三层判定），
      隐藏时置 `None`，与其它字段的表现一致（前端靠 `|| '—'` 兜底）
    - **其余字段**（manufacturer_name / supplier_name / product_url）：仍只看全局开关

    之所以把成本单独拎出来：全局开关无法表达「给某个用户单独开放/禁止」，
    而按用户的覆盖只在这一层生效。历史教训是这段逻辑曾在 4 处各写一遍。
    """
    if getattr(user, "role", "") == "admin":
        return data
    visibility = get_field_visibility(db)
    for field_name, visible in visibility.items():
        if field_name == "cost_price":
            continue
        if not visible and field_name in data:
            data[field_name] = None
    if "cost_price" in data and not cost_visible(user, db):
        data["cost_price"] = None
    return data


def cost_visible(user, db: Session) -> bool:
    """成本价可见性的**唯一判定入口**。

    产品列表/详情/导出、方案、报价单、BOM 模板的所有成本出口都必须走这里 ——
    此前各路由各写一套（products 里直接读全局、quotations 有 `_should_hide_cost`、
    bom_templates 有 `_cost_visible`），漏改一处就等于成本泄漏。

    ① admin 恒可见；
    ② 否则看按用户的覆盖 `users.can_view_cost`（三态：None=跟随全局）；
    ③ 都没有就用全局字段开关。
    """
    if getattr(user, "role", "") == "admin":
        return True
    override = getattr(user, "can_view_cost", None)
    if override is not None:
        return bool(override)
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
