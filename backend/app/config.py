import os
import sys
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = f"sqlite:///{os.path.expanduser('~')}/product-db/backend/product_db.db"
    DATABASE_PATH: str = ""  # filesystem path, derived from DATABASE_URL if empty
    SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    AI_GATEWAY_URL: str = "http://127.0.0.1:8642"
    AI_GATEWAY_KEY: str = ""
    HERMES_API_URL: str = "http://127.0.0.1:8642"
    HERMES_API_KEY: str = ""
    AGENT_API_BASE: str = ""  # API base URL for Agent to call, defaults to localhost:8000/8002
    DEV_MODE: bool = False
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    DISABLE_IP_LOOKUP: bool = False
    # IP → 地区：ip2region 离线库优先，未命中/不适用时才回落 ipapi.co（见 auth_routes）。
    # 相对路径以 backend/ 为基准；文件是 11MB 的只读数据（见 DEPLOY.md）。
    IP2REGION_XDB: str = "data/ip2region_v4.xdb"
    LOGIN_RATE_LIMIT: int = 10  # max failed attempts per window
    LOGIN_RATE_WINDOW: int = 300  # window in seconds
    # 可信反向代理列表：只有直连对端是这些地址时，才采信 X-Forwarded-For /
    # X-Real-IP。否则客户端自带一个 XFF 就能改变限流 key（绕过全局限流与登录
    # 爆破限流）并污染 login_logs 的 IP/地区审计。默认是本机 nginx。
    TRUSTED_PROXIES: str = "127.0.0.1,::1"
    # 全局限流（每 IP）—— 可配置：回归测试期间需要临时放宽，
    # 否则一次全量 E2E 就会撞上日配额。
    RATE_LIMIT_PER_DAY: int = 200
    RATE_LIMIT_PER_MINUTE: int = 60
    WEASYPRINT_PATH: str = ""  # custom weasyprint binary path, blank = auto-detect
    FRONTEND_DIST: str = "frontend/dist"  # relative to backend dir
    IMAGE_MAX_SIZE: int = 5 * 1024 * 1024  # 5MB
    FILE_MAX_SIZE: int = 20 * 1024 * 1024  # 20MB
    AI_MAX_REDIRECTS: int = 3
    AI_CONTEXT_CACHE_TTL: int = 300  # seconds
    AI_EXTRACT_MAX_CHARS: int = 12000
    VISION_BASE_URL: str = "https://api.xiaomimimo.com/v1"
    VISION_MODEL: str = "mimo-v2.5"
    VISION_API_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()

# Resolve filesystem DB path
if settings.DATABASE_PATH:
    DB_FILESYSTEM_PATH = settings.DATABASE_PATH
else:
    # Derive from DATABASE_URL: sqlite:///path → /path
    DB_FILESYSTEM_PATH = settings.DATABASE_URL.replace("sqlite:///", "", 1)

# Resolve the ip2region xdb path against the backend dir（进程 CWD 不可靠）
if not os.path.isabs(settings.IP2REGION_XDB):
    settings.IP2REGION_XDB = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        settings.IP2REGION_XDB,
    ))

if not settings.SECRET_KEY:
    print("ERROR: SECRET_KEY is not set. Use environment variable or .env file.", file=sys.stderr)
    sys.exit(1)
if len(settings.SECRET_KEY) < 32 and not settings.DEV_MODE:
    print("ERROR: SECRET_KEY must be at least 32 characters.", file=sys.stderr)
    sys.exit(1)
