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


# 判断两个片段是否「重复」时要忽略的分隔符：空格、连字符、各类括号与标点。
# 目的是让「CT303/CT305」与「CT303 CT305」这类写法差异不影响判重。
_FILENAME_JOINERS = re.compile(r"[\s\-–—_()（）\[\]【】{},，、.。/\\]+")


def _dedup_key(value) -> str:
    return _FILENAME_JOINERS.sub("", str(value or "")).lower()


def dedup_filename_part(part, container, fallback: str = "") -> str:
    """清理 part；若它已经出现在 container 里则返回空串（不重复拼进文件名）。

    型号常整段出现在产品名里（型号「WTS506」+ 名称「WTS506 气象站」），直接拼接会让
    文件名出现重复内容。比较时忽略空格、连字符与括号，所以「CT303 CT305 CT310」
    与「CT303/CT305/CT310」视为同一个型号。

    只做单向判断（part 是否已被 container 覆盖）：反过来不处理，因为那种情况下
    保留 part 反而更有信息量。

    目前只有产品规格书用得到（报价单与方案 BOM 的文件名不含客户维度 ——
    客户信息本来就在标题/方案名里，见 R43）。
    """
    key = _dedup_key(part)
    if key and key in _dedup_key(container):
        return ""
    return safe_filename_part(part, fallback)


def number_or(value, default: float = 0.0) -> float:
    """数值标准化 —— 只有 None/空串/脏数据才取 default，**0 是合法值**。

    Excel 导入、BOM 快照同步这些入口拿到的可能是字符串；历史写法 `value or default`
    会把 0 当成「未填」（折扣率 0 被按 100% 算、数量 0 被改成 1）。所有这类判定都走这里。
    """
    if value is None or value == "":
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def discount_percent(value, default: float = 100.0) -> float:
    """折扣率（百分数）标准化 —— 折扣率 0 是**合法值**（免费/赠品），只有 None/空才取默认值。

    历史缺陷：多处写成 `value or 100`，于是 0 被当成「未设置」按 100% 计算：
    明细金额、方案合计、导出表格、AI 建单全都会算错。判定一律走这里。
    """
    return number_or(value, default)


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
    page, per_page = clamp_page(page, per_page)
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


# 列表接口的单页上限（R76）。前端最大会请求 per_page=1000（品类/字典全量下拉），
# 产品列表的「全部」选项更是直接发 per_page=<total>，所以取等值上限、留足余量。
# 不设上限的隐患：`per_page=-1` 到 SQLite 就是 `LIMIT -1` ＝ **不限量**，整表灌进内存。
MAX_PER_PAGE = 1000


def clamp_page(page: int, per_page: int):
    """把 page / per_page 收进合法区间，返回 (page, per_page)。

    选择**收口**而不是回 422：`per_page` 越界时拒绝会让前端「全部」选项（发 total）
    在产品数增长到上限以上时直接报错，属功能回退；收口只是分页到上限，响应里回的
    也是生效值，调用方看得见（R76）。
    """
    page = max(1, int(page or 1))
    per_page = min(max(1, int(per_page or 1)), MAX_PER_PAGE)
    return page, per_page


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
