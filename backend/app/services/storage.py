"""Image storage service. Supports local file storage (dev) and S3 (prod)."""
import os
import uuid
from pathlib import Path

UPLOAD_DIR = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp',
                       '.pdf', '.doc', '.docx', '.xls', '.xlsx',
                       '.zip', '.rar', '.bin', '.hex', '.txt', '.csv'}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
VALID_SIGNATURES = [
    b'\xff\xd8\xff',       # JPEG
    b'\x89PNG\r\n\x1a\n',  # PNG
    b'GIF8',               # GIF
    b'RIFF',               # WebP (RIFF container)
    b'BM',                 # BMP
]


def save_upload(file_bytes: bytes, filename: str, product_id: int = 0) -> str:
    """Save uploaded file and return the URL path."""
    ext = Path(filename).suffix or ".jpg"
    safe_name = f"{product_id}_{uuid.uuid4().hex[:8]}{ext}" if product_id else f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, safe_name)
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return f"/product-db/api/uploads/{safe_name}"


def delete_file(url: str) -> bool:
    """Delete a file by its URL path."""
    if not url:
        return False
    for prefix in ("/product-db/api/uploads/",):
        if prefix in url:
            filename = url.split(prefix)[-1]
            break
    else:
        return False
    filepath = Path(os.path.join(UPLOAD_DIR, filename)).resolve()
    if not filepath.is_relative_to(UPLOAD_DIR.resolve()):
        return False
    if filepath.exists():
        filepath.unlink()
        return True
    return False


def upload_from_url(source_url: str, product_id: int = 0) -> str:
    """Download image from URL and save locally. Returns local URL path."""
    from app.utils.security import validate_url
    if not validate_url(source_url):
        raise ValueError(f"URL not allowed: {source_url}")
    import httpx
    resp = httpx.get(source_url, timeout=30, follow_redirects=False, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    })
    resp.raise_for_status()

    content = resp.content
    if len(content) < 8:
        raise ValueError("Downloaded file is too small to be a valid image")

    # Magic bytes validation
    header = content[:8]
    if not any(header.startswith(sig) for sig in VALID_SIGNATURES):
        raise ValueError("Downloaded file does not match a valid image format")

    # Determine extension from magic bytes
    ext = ".jpg"
    if header.startswith(b'\xff\xd8\xff'):
        ext = ".jpg"
    elif header.startswith(b'\x89PNG'):
        ext = ".png"
    elif header.startswith(b'GIF8'):
        ext = ".gif"
    elif header.startswith(b'RIFF'):
        ext = ".webp"
    elif header.startswith(b'BM'):
        ext = ".bmp"

    # Validate extension is allowed
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File extension '{ext}' not allowed")

    return save_upload(content, f"download{ext}", product_id)


def save_file(file_bytes: bytes, original_filename: str) -> str:
    """Save uploaded document file. Returns local URL path.
    Validates extension and size, generates safe filename."""
    ext = Path(original_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File extension '{ext}' not allowed")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)")
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, safe_name)
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return f"/product-db/api/uploads/{safe_name}"
