"""Product import — Excel preview and confirm."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.product import Product
from app.models.category import Category
from app.models.dictionary import Manufacturer
from app.auth import get_current_user
from app.utils.escape import escape_like, LIKE_ESCAPE
from app.schemas.product import ProductImportConfirm
import openpyxl
from io import BytesIO

router = APIRouter()


@router.post("/products/import-preview")
async def import_preview(file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Parse Excel file and return preview rows with column mapping."""
    from app.config import settings
    from app.services.storage import read_limited

    # 流式读 + 大小上限：原来直接 file.file.read() 把整个文件读进内存，普通用户
    # 上传一个几百 MB 的 xlsx 就能把工作进程内存打满（xlsx 是 zip，解压后更大）
    try:
        raw = await read_limited(file, settings.FILE_MAX_SIZE)
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        wb = openpyxl.load_workbook(BytesIO(raw), data_only=True)
    except Exception:
        raise HTTPException(400, "Invalid Excel file")
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(400, "Empty file")
    headers = [str(c) if c else "" for c in rows[0]]
    data_rows = []
    for row in rows[1:]:
        if not any(row):
            continue
        data_rows.append([str(c) if c is not None else "" for c in row])

    return {"sheet_name": sheet.title, "headers": headers, "rows": data_rows, "row_count": len(data_rows)}


@router.post("/products/import-confirm")
def import_confirm(data: ProductImportConfirm, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Save products from imported data with column mapping."""
    mapping = data.mapping
    rows = data.rows
    if not rows or not mapping:
        raise HTTPException(400, "No data to import")

    # 先整体解析 + 校验，再落库：products.category_id 是 NOT NULL（模型与生产库一致），
    # 品类名匹配不到时若直接插 None，整批会在 commit 处 IntegrityError → 500，
    # 且因为只在最后 commit 一次，用户拿不到任何可操作的提示、也丢掉了整批数据。
    parsed = []
    unmatched = set()
    # row_no 是「数据行」序号（表头之外，从 1 起）：报错时用户能对上表格里第几行数据
    for row_no, row in enumerate(rows, start=1):
        pdata = {}
        for col_idx, field in mapping.items():
            idx = int(col_idx)
            if idx < len(row):
                pdata[field] = str(row[idx]).strip() if row[idx] else ""

        name = pdata.get("name", "")
        model = pdata.get("model", "")
        if not name and not model:
            continue   # 空行/无关键字段的行按既有语义跳过

        cat_name = pdata.get("category", "")
        category_id = None
        if cat_name:
            cat = db.query(Category).filter(Category.name == cat_name).first()
            if not cat:
                cat = db.query(Category).filter(
                    Category.name.ilike(f"%{escape_like(cat_name)}%", escape=LIKE_ESCAPE)
                ).first()
            if cat:
                category_id = cat.id
        if not category_id:
            unmatched.add(cat_name or "（本行未填品类）")
            continue
        parsed.append((row_no, pdata, category_id))

    if unmatched:
        raise HTTPException(
            400,
            "以下品类在系统中不存在，请先在「品类管理」中创建或修正表格后重试："
            + "、".join(sorted(unmatched)),
        )
    if not parsed:
        raise HTTPException(400, "没有可导入的行：每行至少需要「产品名称」或「型号」，且必须能匹配到已有品类")

    imported = 0
    skipped = 0
    seen_keys: set = set()
    for row_no, pdata, category_id in parsed:
        # 去重：products 上没有唯一约束兜底，同一份表格导入两次就会翻倍；
        # 同一次导入的表格里出现两遍同样要挡。业务标识取「名称 + 型号」，
        # 比较时忽略大小写（表格里改个大小写不该多出一条产品）。
        name = (pdata.get("name") or pdata.get("model") or "").strip()
        model = (pdata.get("model") or "").strip()
        key = (name.lower(), model.lower())
        if key in seen_keys:
            skipped += 1
            continue
        if db.query(Product.id).filter(
            func.lower(Product.name) == key[0],
            func.lower(func.coalesce(Product.model, "")) == key[1],
        ).first():
            skipped += 1
            continue
        seen_keys.add(key)

        mfg_name = (pdata.get("manufacturer") or "").strip()
        manufacturer_id = None
        if mfg_name:
            # 大小写不敏感：Acme / acme / ACME 是同一个厂商，否则每导一次就多一条
            mfg = db.query(Manufacturer).filter(
                func.lower(Manufacturer.name) == mfg_name.lower()
            ).first()
            if not mfg:
                mfg = Manufacturer(name=mfg_name)
                db.add(mfg)
                db.flush()
            manufacturer_id = mfg.id

        spec_items = {k.replace("spec:", ""): v for k, v in pdata.items() if k.startswith("spec:")}

        p = Product(
            name=name,
            model=model,
            sku=pdata.get("sku", ""),
            category_id=category_id,
            manufacturer_id=manufacturer_id,
            base_price=_num_or_400(pdata.get("price"), "价格", row_no),
            cost_price=_num_or_400(pdata.get("cost"), "成本", row_no),
            description=pdata.get("description", ""),
            product_url=pdata.get("product_url", ""),
            specs=spec_items,
        )
        db.add(p)
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped}


def _num_or_400(value, label: str, row_no: int) -> Optional[float]:
    """把表格里的价格/成本转成数字；无效值报错并指出行号（R56）。

    早前是裸 `float(...)`：一格填成「1,200」「面议」「¥500」会让整批导入 500，
    且看不出是哪一行。

    **空值返回 None 而不是 0**（R75）：`products.base_price` 是可空列，「表格里没填」
    与「填了 0 元」是两件事 —— 一律落 0 会让未定价的产品看起来是免费的，也让
    「哪些产品还没定价」这种查询无从下手。数值本身仍按 0 元正常入库。
    """
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"第 {row_no} 个数据行（表头之外）：{label}「{value}」不是有效数字")
