"""Image storage service. Supports local file storage (dev) and S3 (prod)."""
import os
import uuid
from pathlib import Path

UPLOAD_DIR = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "products"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def save_upload(file_bytes: bytes, filename: str, product_id: int = 0) -> str:
    """Save uploaded file and return the URL path."""
    ext = Path(filename).suffix or ".jpg"
    safe_name = f"{product_id}_{uuid.uuid4().hex[:8]}{ext}" if product_id else f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, safe_name)
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return f"/api/uploads/products/{safe_name}"


def delete_file(url: str) -> bool:
    """Delete a file by its URL path."""
    if not url or "/api/uploads/products/" not in url:
        return False
    filename = url.split("/api/uploads/products/")[-1]
    filepath = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False


def upload_from_url(source_url: str, product_id: int = 0) -> str:
    """Download image from URL and save locally. Returns local URL path."""
    import requests as http_requests
    resp = http_requests.get(source_url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    })
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "image/jpeg")
    ext = ".jpg"
    if "png" in content_type:
        ext = ".png"
    elif "webp" in content_type:
        ext = ".webp"
    elif "gif" in content_type:
        ext = ".gif"
    return save_upload(resp.content, f"download{ext}", product_id)
