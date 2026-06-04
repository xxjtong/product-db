"""Product file upload/download API."""
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.product_file import ProductFile
from app.services.storage import save_file, delete_file, UPLOAD_DIR

router = APIRouter()


@router.get("/products/{product_id}/files")
def list_files(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    files = db.query(ProductFile).filter_by(product_id=product_id)\
        .order_by(ProductFile.sort_order, ProductFile.id).all()
    return {"files": [f.to_dict() for f in files]}


@router.post("/products/{product_id}/files")
async def upload_file(
    product_id: int,
    file: UploadFile = File(...),
    label: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    content = await file.read()
    try:
        file_url = save_file(content, file.filename or "file")
    except ValueError as e:
        raise HTTPException(400, str(e))

    pf = ProductFile(
        product_id=product_id,
        filename=file.filename or "",
        file_url=file_url,
        file_size=len(content),
        file_type=os.path.splitext(file.filename or "")[1].lstrip("."),
        label=label or file.filename or "",
    )
    db.add(pf)
    db.commit()
    db.refresh(pf)
    return {"file": pf.to_dict()}


@router.get("/products/files/{file_id}")
def download_file(file_id: int, inline: bool = False, db: Session = Depends(get_db)):
    pf = db.get(ProductFile, file_id)
    if not pf:
        raise HTTPException(404, "File not found")

    fname = pf.file_url.split("/")[-1]
    filepath = os.path.join(UPLOAD_DIR, fname)
    if not os.path.exists(filepath):
        raise HTTPException(404, "File not found on disk")

    media_map = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "zip": "application/zip",
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    }
    media_type = media_map.get(pf.file_type, "application/octet-stream")

    safe_filename = pf.filename.replace('"', '').replace('\\', '')
    from urllib.parse import quote
    disposition = "inline" if inline else "attachment"
    return FileResponse(
        filepath,
        media_type=media_type,
        filename=safe_filename,
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(safe_filename)}"},
    )


@router.delete("/products/files/{file_id}")
def delete_product_file(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    pf = db.get(ProductFile, file_id)
    if not pf:
        raise HTTPException(404, "File not found")
    try:
        delete_file(pf.file_url)
    except Exception:
        pass  # file already gone
    db.delete(pf)
    db.commit()
    return {"ok": True}
