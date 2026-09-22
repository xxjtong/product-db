from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi import HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.database import Base
from app.auth import client_ip
from app.models import *  # noqa: ensure all models registered
from app.routers import products, product_import, categories, suppliers, solutions, quotations, bom_templates, ai, dictionaries, auth_routes, admin_routes, system_settings, product_files, agent
from app.config import settings
from app.services.approval_manager import reaper_loop as approval_reaper_loop
from loguru import logger
from contextlib import asynccontextmanager, suppress
import asyncio
import logging
import os
import sys
import time
import mimetypes

# Table creation is handled by Alembic migrations.
# Do NOT use Base.metadata.create_all here — always run alembic upgrade head.

# Configure structured logging
# 日志文件用绝对路径：之前写成 "app.log" 是相对路径，落点取决于进程 CWD，
# 历史上不同 CWD 导致日志散落在 /opt/product-db/、backend/、frontend/ 三处，
# 且部分残留文件权限是 644（world-readable）。
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(_BACKEND_DIR, "app.log")

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | <level>{message}</level>",
    level="DEBUG" if settings.DEV_MODE else "INFO",
)
logger.add(
    LOG_FILE,
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} | {message}",
    level="INFO",
)


class _LoguruBridge(logging.Handler):
    """把 stdlib logging 的记录转给 loguru。

    backend 里有二十来处用 `logging.getLogger(__name__)`（agent、登录地区、AI 提取…），
    它们**不经过 loguru**：INFO 级默认不落盘，WARNING 级只进 journalctl。结果是排查
    agent/AI 问题时只看 app.log 会误判成「没有日志」（曾被记在 DEPLOY.md 里当成已知坑）。

    只挂在 `app` 这个父 logger 上：这样 `app.*` 模块的日志会进 app.log，而 uvicorn
    自己的访问日志不受影响（它们的 logger 名是 uvicorn.*，不会冒泡到这里）。
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # 起点必须用 `sys._getframe(1)`（emit 的调用者，两个版本都在 logging 内部），
        # **不要**用官方配方里的 `logging.currentframe()`：它是个 lambda，3.9 里是
        # `sys._getframe(3)`、3.11 里是 `sys._getframe(1)`，于是在 emit 里拿到的是
        # 不同层级的帧 —— 3.11 上它返回的就是 emit 自己那一帧，循环一次都不走、
        # depth 恒为 2，日志里的 {name}:{line} 全变成 `logging:1706`（线上实测）。
        frame, depth = sys._getframe(1), 1
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


_app_logger = logging.getLogger("app")
_app_logger.setLevel(logging.INFO)
_app_logger.addHandler(_LoguruBridge())

if settings.DEV_MODE:
    # Safety: refuse DEV_MODE under systemd unless explicitly forced
    if os.environ.get('INVOCATION_ID') and not os.environ.get('FORCE_DEV_MODE'):
        logger.error("DEV_MODE=true refused under systemd. Set FORCE_DEV_MODE=true to override.")
        sys.exit(1)
    logger.warning("=" * 60)
    logger.warning("⚠️  DEV_MODE=true — auto-creates admin/admin, skips auth checks")
    logger.warning("    NEVER use in production. Set DEV_MODE=false in .env")
    logger.warning("=" * 60)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 审批任务的过期回收：原先只在 create() 里顺带做 —— 长时间没有新审批创建的
    # 实例上，过期任务会一直挂在内存里（R68 审查发现「只在 create 时触发」）。
    # 起一个后台循环兜住，关闭时取消。
    reaper = asyncio.create_task(approval_reaper_loop())
    try:
        yield
    finally:
        reaper.cancel()
        with suppress(asyncio.CancelledError):
            await reaper
        # 关闭 agent 代理复用的连接池（R64：以前每个请求各建一个 client）
        await agent.close_http_client()


app = FastAPI(title="物联网产品中心", version="2.0.0", lifespan=lifespan)

# 全局限流 —— 按 IP 计。**只有 default_limits 生效**：slowapi 的 SlowAPIMiddleware
# 一律按「解析到的 handler 名字」匹配限流规则，而 SPA catch-all
# `/product-db/{full_path:path}` 注册在最后、匹配所有路径 → handler 恒为 serve_spa，
# 于是函数级 `@limiter.exempt` / `@limiter.limit` 全部失效（R35 实测 exempt 无效）。
# 需要针对单个端点限流时，请用**手写计数**（见 auth_routes 的 LOGIN_RATE_LIMIT），
# 不要用 @limiter.limit。
limiter = Limiter(
    key_func=client_ip,
    default_limits=[
        f"{settings.RATE_LIMIT_PER_DAY}/day",
        f"{settings.RATE_LIMIT_PER_MINUTE}/minute",
    ],
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda req, exc: JSONResponse(
    status_code=429,
    content={"detail": "Too many requests. Please try again later."},
))

# 不计入限流配额的路径：
#   · /product-db/api/health、/product-db/（可用性探针每 2 分钟打这两个）
#   · /product-db/assets/、uploads（页面加载的静态资源与图片，逐个计入配额会
#     让正常浏览产品页很快触顶）
# 为什么要在中间件层豁免：见上面 limiter 的注释 —— 函数级豁免与限流都不生效，
# 只能在这里按路径提前放行。
# 不豁免的代价（2026-09 生产实测）：探针 2 请求/2 分钟 = 1440 次/天，3.3 小时
# 就打满 200/天配额 → 此后全天 429，探针天天误报「服务不可用」，还会污染探针的
# 状态机（真宕机时不再产生新告警）。
_RATE_LIMIT_EXEMPT_EXACT = {"/product-db", "/product-db/api/health"}
_RATE_LIMIT_EXEMPT_PREFIXES = ("/product-db/assets/", "/product-db/api/uploads", "/api/uploads")


def rate_limit_exempt(path: str) -> bool:
    """该路径是否不参与限流计数（探针健康检查、SPA 首页与静态资源）"""
    path = path.rstrip("/") or "/"      # /product-db/ 与 /product-db 视为同一路径
    return path in _RATE_LIMIT_EXEMPT_EXACT or path.startswith(_RATE_LIMIT_EXEMPT_PREFIXES)


class RateLimitMiddleware(SlowAPIMiddleware):
    """在 slowapi 之前按路径放行豁免清单（探针/静态资源不消耗也不被限流配额拦住）"""

    async def dispatch(self, request, call_next):
        if rate_limit_exempt(request.url.path):
            return await call_next(request)
        return await super().dispatch(request, call_next)


app.add_middleware(RateLimitMiddleware)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration:.3f}s)")
    response.headers["Content-Security-Policy"] = "upgrade-insecure-requests"
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
app.include_router(agent.router, prefix="/product-db/api", tags=["agent"])

# Static file serving for uploaded images
upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(upload_dir, exist_ok=True)


class UploadsStaticFiles(StaticFiles):
    """上传目录的静态服务，只放行允许上传的扩展名并统一加 nosniff。

    纵深防御：上传入口现在按内容决定扩展名（见 storage.detect_upload_extension），
    这里再白名单挡一次，避免历史遗留或其它写入路径留下的 .html/.svg 被浏览器
    按可执行类型渲染（与主站同源 → 可读走 localStorage 的 JWT）。
    """

    async def get_response(self, path, scope):
        from app.services.storage import SERVABLE_EXTENSIONS

        if os.path.splitext(path)[1].lower() not in SERVABLE_EXTENSIONS:
            return Response(status_code=404)
        resp = await super().get_response(path, scope)
        if resp.status_code == 200:
            resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp


# Serve uploads at both paths: old /api/uploads (compat) and new /product-db/api/uploads
app.mount("/api/uploads", UploadsStaticFiles(directory=upload_dir), name="uploads-legacy")
app.mount("/product-db/api/uploads", UploadsStaticFiles(directory=upload_dir), name="uploads")


@app.get("/product-db/api/health")
def health():
    # 本路由**不计入限流**（见 RateLimitMiddleware 的豁免清单）—— 中间件按路径
    # 提前放行，因为 slowapi 的 SlowAPIMiddleware/`@limiter.exempt` 都按 handler
    # 名字匹配，而 SPA catch-all 把 handler 名字遮蔽了（R35 实测：连打 65 次仍 429）。
    # 历史代价：探针每 2 分钟 2 个请求会在 3.3 小时内打满 200/天配额，此后全天 429。
    return {"status": "ok"}


# --- SPA frontend serving ---
_frontend_dist = settings.FRONTEND_DIST
if not os.path.isabs(_frontend_dist):
    _frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", _frontend_dist)
_frontend_dist = os.path.abspath(_frontend_dist)

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
