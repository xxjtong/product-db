"""Product spec sheet — HTML/PDF generation and AI content extraction."""
from __future__ import annotations
import re
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.product import Product
from app.auth import get_current_user
from app.config import settings
from app.services.spec_generator import build_spec_html
from app.services.ai_extract import call_ai_extract, regex_extract_from_text
from app.schemas.product import AIFetchRequest
import httpx
from bs4 import BeautifulSoup

router = APIRouter()


# --- URL validation (SSRF prevention) ---

ALLOWED_URL_SCHEMES = {"http", "https"}
BLOCKED_HOSTS = {"169.254.169.254", "localhost", "0.0.0.0", "127.0.0.1", "metadata.google.internal"}


def validate_url(url: str) -> bool:
    """Validate URL scheme and block private/metadata hosts (SSRF prevention)."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        return False
    hostname = (parsed.hostname or "").lower()
    for blocked in BLOCKED_HOSTS:
        if hostname == blocked or hostname.endswith("." + blocked):
            return False
    return True


@router.get("/products/{product_id}/spec-sheet")
def spec_sheet(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Generate product spec sheet (HTML or PDF)."""
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    html_content = build_spec_html(p, db)
    return HTMLResponse(content=html_content)


@router.post("/products/ai-fetch")
def ai_fetch_product(data: AIFetchRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """AI-assisted product info extraction from URL or text."""
    url = data.url.strip()
    raw_text = data.text.strip()

    if raw_text:
        result = call_ai_extract("", "", raw_text, db) if settings.AI_GATEWAY_KEY \
            else regex_extract_from_text("", raw_text, db)
        return {"fetched": result}

    if not url:
        raise HTTPException(400, "URL or text is required")

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(400, "Invalid URL")

    if not validate_url(url):
        raise HTTPException(400, "URL not allowed")

    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(400, f"Failed to fetch URL: {str(e)}")

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "path"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title else ""
    body = soup.body
    text = body.get_text(separator="\n", strip=True) if body else resp.text
    text = re.sub(r'\n{3,}', '\n\n', text)[:8000]

    if not text:
        raise HTTPException(400, "No text content extracted from URL")

    result = call_ai_extract(url, title, text, db)
    return {"fetched": {"url": url, "title": title, **result}}
