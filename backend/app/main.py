from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.models import *  # noqa: ensure all models registered
from app.routers import products, product_import, product_specs, categories, suppliers, solutions, quotations, bom_templates, ai, dictionaries, auth_routes, system_settings
from app.config import settings
from loguru import logger
import os
import sys
import time

# Table creation via Alembic for production; auto-create in dev mode
if settings.DEV_MODE:
    Base.metadata.create_all(bind=engine)

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
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dictionaries.router, prefix="/api", tags=["dictionaries"])
app.include_router(categories.router, prefix="/api", tags=["categories"])
app.include_router(products.router, prefix="/api", tags=["products"])
app.include_router(product_import.router, prefix="/api", tags=["products"])
app.include_router(product_specs.router, prefix="/api", tags=["products"])
app.include_router(suppliers.router, prefix="/api", tags=["suppliers"])
app.include_router(solutions.router, prefix="/api", tags=["solutions"])
app.include_router(quotations.router, prefix="/api", tags=["quotations"])
app.include_router(bom_templates.router, prefix="/api", tags=["bom-templates"])
app.include_router(ai.router, prefix="/api", tags=["ai"])
app.include_router(auth_routes.router, prefix="/api", tags=["auth"])
app.include_router(system_settings.router, prefix="/api", tags=["settings"])

# Static file serving for uploaded images
upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(upload_dir, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=upload_dir), name="uploads")


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
