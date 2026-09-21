"""Shared utility helpers for route handlers."""
import re
from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.orm import Session


# 文件名里不允许出现的字符：路径分隔符、通配符、控制字符 —— 客户名/项目名是用户
# 自由输入的，直接拼进文件名可能带出目录、把下游客户端写歪，或让 Content-Disposition
# 被截断。
_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def safe_filename_part(value, fallback: str = "", max_len: int = 40) -> str:
    """把客户名/项目名等清理成可放进文件名的片段（过长会截断，空则用 fallback）"""
    text = _UNSAFE_FILENAME_CHARS.sub(" ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:max_len].strip() or fallback


def attachment_disposition(filename: str, ascii_fallback: str = "download") -> str:
    """构造下载用的 Content-Disposition：ASCII 回退名 + RFC 5987 编码名。

    HTTP header 只能放 latin-1，中文文件名必须走 `filename*=UTF-8''<百分号编码>`，
    否则部分客户端会乱码甚至直接报错；同时保留一个纯 ASCII 的 `filename=`，
    兼容不支持 `filename*` 的老客户端。
    """
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(filename, safe="")}'


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


def format_description_with_specs(description: str = "", specs: Optional[dict] = None) -> str:
    """Combine product description and spec parameters into single display string.

    Strips URLs from description. Example: "光照传感器 | 防护等级:IP67 | 尺寸:100×80×30mm"
    """
    parts = []
    if description:
        clean = re.sub(r'https?://\S+', '', description).strip()
        if clean:
            parts.append(clean)
    if specs:
        spec_items = [f"{k}: {v}" for k, v in specs.items() if v not in (None, "", [])]
        if spec_items:
            parts.append(" | ".join(spec_items))
    return " | ".join(parts)
