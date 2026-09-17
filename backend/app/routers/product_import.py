"""Product import — Excel preview and confirm."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
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

    imported = 0
    for row in rows:
        pdata = {}
        for col_idx, field in mapping.items():
            idx = int(col_idx)
            if idx < len(row):
                pdata[field] = str(row[idx]).strip() if row[idx] else ""

        name = pdata.get("name", "")
        model = pdata.get("model", "")
        if not name and not model:
            continue

        cat_name = pdata.get("category", "")
        category_id = None
        if cat_name:
            cat = db.query(Category).filter(Category.name == cat_name).first()
            if not cat:
                cat = db.query(Category).filter(Category.name.ilike(f"%{escape_like(cat_name)}%", escape=LIKE_ESCAPE)).first()
            if cat:
                category_id = cat.id

        mfg_name = pdata.get("manufacturer", "")
        manufacturer_id = None
        if mfg_name:
            mfg = db.query(Manufacturer).filter(Manufacturer.name == mfg_name).first()
            if not mfg:
                mfg = Manufacturer(name=mfg_name)
                db.add(mfg)
                db.flush()
            manufacturer_id = mfg.id

        spec_items = {k.replace("spec:", ""): v for k, v in pdata.items() if k.startswith("spec:")}

        p = Product(
            name=name or model,
            model=model or "",
            sku=pdata.get("sku", ""),
            category_id=category_id,
            manufacturer_id=manufacturer_id,
            base_price=float(pdata.get("price", 0) or 0),
            cost_price=float(pdata.get("cost", 0) or 0),
            description=pdata.get("description", ""),
            product_url=pdata.get("product_url", ""),
            specs=spec_items,
        )
        db.add(p)
        imported += 1

    db.commit()
    return {"imported": imported}
