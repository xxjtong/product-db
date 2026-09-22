import os
import sys
from pydantic_settings import BaseSettings


_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/


class Settings(BaseSettings):
    # 默认库文件放在**代码同目录**（backend/product_db.db）。
    # 早前这里写的是 f"sqlite:///{os.path.expanduser('~')}/product-db/backend/product_db.db"，
    # 依赖运行用户的 HOME —— R51 就因此出事：systemd 加固启用 ProtectHome 后 /home 被隐藏，
    # 服务能启动但所有查库接口 500（unable to open database file）。路径不应随用户/家目录漂移。
    DATABASE_URL: str = f"sqlite:///{os.path.join(_BACKEND_DIR, 'product_db.db')}"
    # 已废弃：库路径的唯一来源是 DATABASE_URL（engine 与 alembic 都读它）。
    # 字段保留仅为兼容旧 .env（pydantic-settings 对未知字段会直接报错），不再参与任何推导。
    DATABASE_PATH: str = ""
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
    # 注册限流（按 IP 的**尝试**次数，不分成败）：挡的是批量注册账号 / 用户名枚举。
    # 正常用户一小时内不会注册 5 次，所以额度给小一点不影响使用。
    REGISTER_RATE_LIMIT: int = 5
    REGISTER_RATE_WINDOW: int = 3600
    # 可信反向代理列表：只有直连对端是这些地址时，才采信 X-Forwarded-For /
    # X-Real-IP。否则客户端自带一个 XFF 就能改变限流 key（绕过全局限流与登录
    # 爆破限流）并污染 login_logs 的 IP/地区审计。默认是本机 nginx。
    TRUSTED_PROXIES: str = "127.0.0.1,::1"
    # 全局限流（按 IP），可用环境变量覆盖（回归测试/E2E 期间需要临时放宽）。
    # 健康检查与静态资源已在中间件层豁免，见 main.py 的 rate_limit_exempt ——
    # 这里的额度是给 API 用的。
    # 2026-09 前是 200/天，实测两个问题：单个 SPA 用户正常浏览就可能触顶（近 5 天
    # 出现过 1 次真实用户 429），而探针与 Hermes agent 都从服务器本机 IP 出发、
    # 共用同一份额度。调到 3000/天 + 120/分：既不影响正常使用，又能拦住明显滥用。
    RATE_LIMIT_PER_DAY: int = 3000
    RATE_LIMIT_PER_MINUTE: int = 120
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

# 库路径的**唯一来源**是 DATABASE_URL（database.py 建 engine、alembic 迁移都用它）；
# DB_FILESYSTEM_PATH 只是它的文件系统视图，供 agent 展示与运维脚本使用 ——
# 以前会优先取 DATABASE_PATH，于是出现「engine 用 A 路径、这里报告 B 路径」的不一致（R51 复盘）。
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
