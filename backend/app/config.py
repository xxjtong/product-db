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
    AGENT_UPLOAD_DIR: str = ""  # upload dir path for Hermes to read files directly
    DEV_MODE: bool = False
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    DISABLE_IP_LOOKUP: bool = False
    LOGIN_RATE_LIMIT: int = 10  # max failed attempts per window
    LOGIN_RATE_WINDOW: int = 300  # window in seconds
    WEASYPRINT_PATH: str = ""  # custom weasyprint binary path, blank = auto-detect
    FRONTEND_DIST: str = "frontend/dist"  # relative to backend dir
    IMAGE_MAX_SIZE: int = 5 * 1024 * 1024  # 5MB
    FILE_MAX_SIZE: int = 20 * 1024 * 1024  # 20MB
    AI_MAX_REDIRECTS: int = 3
    AI_CONTEXT_CACHE_TTL: int = 300  # seconds
    AI_EXTRACT_MAX_CHARS: int = 12000

    class Config:
        env_file = ".env"


settings = Settings()

# Resolve filesystem DB path
if settings.DATABASE_PATH:
    DB_FILESYSTEM_PATH = settings.DATABASE_PATH
else:
    # Derive from DATABASE_URL: sqlite:///path → /path
    DB_FILESYSTEM_PATH = settings.DATABASE_URL.replace("sqlite:///", "", 1)

if not settings.SECRET_KEY:
    print("ERROR: SECRET_KEY is not set. Use environment variable or .env file.", file=sys.stderr)
    sys.exit(1)
if len(settings.SECRET_KEY) < 32 and not settings.DEV_MODE:
    print("ERROR: SECRET_KEY must be at least 32 characters.", file=sys.stderr)
    sys.exit(1)
