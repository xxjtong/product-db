import os
import sys
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = f"sqlite:///{os.path.expanduser('~')}/product-db/backend/product_db.db"
    SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    AI_GATEWAY_URL: str = "http://127.0.0.1:8642"
    AI_GATEWAY_KEY: str = ""
    DEV_MODE: bool = False
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    DISABLE_IP_LOOKUP: bool = False
    LOGIN_RATE_LIMIT: int = 10  # max failed attempts per window
    LOGIN_RATE_WINDOW: int = 300  # window in seconds

    class Config:
        env_file = ".env"


settings = Settings()

if not settings.SECRET_KEY:
    print("ERROR: SECRET_KEY is not set. Use environment variable or .env file.", file=sys.stderr)
    sys.exit(1)
if len(settings.SECRET_KEY) < 32 and not settings.DEV_MODE:
    print("ERROR: SECRET_KEY must be at least 32 characters.", file=sys.stderr)
    sys.exit(1)
