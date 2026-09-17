"""Image storage service. Supports local file storage (dev) and S3 (prod)."""
import os
import uuid
from pathlib import Path
import httpx

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
    from app.config import settings
    if not validate_url(source_url):
        raise ValueError(f"URL not allowed: {source_url}")

    # Stream with a hard size cap so a malicious URL cannot exhaust memory.
    limit = settings.IMAGE_MAX_SIZE
    chunks = []
    total = 0
    with httpx.stream(
        "GET", source_url, timeout=30, follow_redirects=False,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    ) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_bytes(65536):
            total += len(chunk)
            if total > limit:
                raise ValueError(f"Downloaded file too large (max {limit // (1024 * 1024)}MB)")
            chunks.append(chunk)

    content = b"".join(chunks)
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


async def read_limited(file, max_size: int) -> bytes:
    """Stream-read an UploadFile, raising ValueError if it exceeds max_size.

    Reads in 256KB chunks so oversized uploads are rejected without loading
    the entire body into memory first.
    """
    chunks = []
    total = 0
    while True:
        chunk = await file.read(256 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise ValueError(f"File too large (max {max_size // (1024 * 1024)}MB)")
        chunks.append(chunk)
    return b"".join(chunks)


# --- 上传内容的类型判定（按内容，而不是客户端声明的 Content-Type / 文件名） ---
#
# 背景：agent 上传曾直接采信客户端 Content-Type 并把用户文件名的扩展名原样落盘，
# 配合 uploads 目录的无鉴权静态托管，可以存出 .html/.svg 并诱导管理员打开，
# 构成同源存储型 XSS（可读走 localStorage 里的 JWT）。扩展名必须由服务端决定。

_TEXT_EXTENSIONS = {".txt", ".csv", ".json", ".md", ".xml"}
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# BMP 的 DIB 头长度取值（字节 14-17，小端），用来避免把 "BM" 开头的文本误判成图片
_BMP_DIB_SIZES = {12, 40, 52, 56, 64, 108, 124}


def _is_plain_text(content: bytes) -> bool:
    """无 NUL 字节且可解码为 UTF-8/GBK 的文本（用于 txt/csv/json/md/xml 判定）。"""
    if not content or b"\x00" in content[:4096]:
        return False
    for codec in ("utf-8", "gbk"):
        try:
            content.decode(codec)
            return True
        except UnicodeDecodeError:
            continue
    return False


def _ooxml_extension(content: bytes) -> str:
    """xlsx/docx/pptx 都是 zip 容器，按内部目录判定真实类型。"""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            names = z.namelist()
    except Exception:
        return ""
    for prefix, ext in (("xl/", ".xlsx"), ("word/", ".docx"), ("ppt/", ".pptx")):
        if any(n.startswith(prefix) for n in names):
            return ext
    return ""


def detect_upload_extension(content: bytes, filename: str = "") -> str:
    """按内容判定扩展名（含点）；无法确认属于允许类型时返回空串。

    只有文本类（txt/csv/json/md/xml）与旧版 Office（OLE2，doc/xls/ppt）才沿用
    原文件名的扩展名，且必须落在白名单内 —— 这样 .html/.svg/.js 无论叫什么名字、
    声称什么 Content-Type，都不可能被保存。
    """
    if not content:
        return ""
    original = Path(filename or "").suffix.lower()

    # 图片：魔数
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    if content.startswith(b"BM") and len(content) > 17 and \
            int.from_bytes(content[14:18], "little") in _BMP_DIB_SIZES:
        return ".bmp"

    if content.startswith(b"%PDF-"):
        return ".pdf"

    if content.startswith(b"PK\x03\x04"):
        return _ooxml_extension(content)

    if content.startswith(_OLE2_MAGIC):
        return original if original in (".doc", ".xls", ".ppt") else ""

    # 文本类：沿用原扩展名，但必须是文本白名单里的类型
    if _is_plain_text(content) and original in _TEXT_EXTENSIONS:
        return original

    return ""


# 允许通过静态路径直接下载的扩展名（= 允许上传的文档/图片 + 文本类）
# 静态服务只白名单放行，浏览器可当脚本执行的一律不服务。
SERVABLE_EXTENSIONS = ALLOWED_EXTENSIONS | {".json", ".md", ".xml"}
