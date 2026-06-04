from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import HTTPException
from app.database import Base
from app.models import *  # noqa: ensure all models registered
from app.routers import products, product_import, categories, suppliers, solutions, quotations, bom_templates, ai, dictionaries, auth_routes, admin_routes, system_settings, product_files
from app.config import settings
from loguru import logger
import os
import sys
import time

# Table creation is handled by Alembic migrations.
# Do NOT use Base.metadata.create_all here — always run alembic upgrade head.

# Configure structured logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | <level>{message}</level>",
    level="DEBUG" if settings.DEV_MODE else "INFO",
)
logger.add(
    "app.log",
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} | {message}",
    level="INFO",
)

app = FastAPI(title="物联网产品中心", version="2.0.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration:.3f}s)")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dictionaries.router, prefix="/product-db/api", tags=["dictionaries"])
app.include_router(categories.router, prefix="/product-db/api", tags=["categories"])
app.include_router(products.router, prefix="/product-db/api", tags=["products"])
app.include_router(product_import.router, prefix="/product-db/api", tags=["products"])
app.include_router(suppliers.router, prefix="/product-db/api", tags=["suppliers"])
app.include_router(solutions.router, prefix="/product-db/api", tags=["solutions"])
app.include_router(quotations.router, prefix="/product-db/api", tags=["quotations"])
app.include_router(bom_templates.router, prefix="/product-db/api", tags=["bom-templates"])
app.include_router(ai.router, prefix="/product-db/api", tags=["ai"])
app.include_router(auth_routes.router, prefix="/product-db/api", tags=["auth"])
app.include_router(admin_routes.router, prefix="/product-db/api", tags=["admin"])
app.include_router(system_settings.router, prefix="/product-db/api", tags=["settings"])
app.include_router(product_files.router, prefix="/product-db/api", tags=["product-files"])

# Static file serving for uploaded images
upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(upload_dir, exist_ok=True)
# Serve uploads at both paths: old /api/uploads (compat) and new /product-db/api/uploads
app.mount("/api/uploads", StaticFiles(directory=upload_dir), name="uploads-legacy")
app.mount("/product-db/api/uploads", StaticFiles(directory=upload_dir), name="uploads")


@app.get("/product-db/api/health")
def health():
    return {"status": "ok"}


# --- SPA frontend serving ---
_frontend_dist = "/opt/product-db/frontend/dist"
import mimetypes

# Nginx no longer strips prefix — backend serves at /product-db/
@app.get("/product-db/assets/{file_path:path}")
async def serve_assets(file_path: str):
    """Serve SPA static assets with explicit content-type headers."""
    full_path = os.path.join(_frontend_dist, "assets", file_path)
    if not os.path.abspath(full_path).startswith(os.path.abspath(_frontend_dist)):
        raise HTTPException(status_code=403)
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="Not Found")
    media_type, _ = mimetypes.guess_type(full_path)
    return FileResponse(full_path, media_type=media_type)

# API routes need /product-db/ prefix since Nginx preserves it
# (include_router calls below use prefix="/api" — need prefix="/product-db/api")

# Serve SPA index.html for all routes, except univer-bom.html standalone page
@app.get("/product-db")
@app.get("/product-db/")
@app.get("/product-db/{full_path:path}")
async def serve_spa(full_path: str = ""):
    # Univer BOM editor is a standalone multi-page entry
    if full_path == "univer-bom.html":
        univer_path = os.path.join(_frontend_dist, "univer-bom.html")
        if os.path.isfile(univer_path):
            return FileResponse(univer_path)

    index_path = f"{_frontend_dist}/index.html"
    if not os.path.isfile(index_path):
        return JSONResponse({"detail": "Frontend not built"}, status_code=503)
    return FileResponse(index_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
