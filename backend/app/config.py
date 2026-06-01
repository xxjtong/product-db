import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = f"sqlite:///{os.path.expanduser('~')}/product-db/backend/product_db.db"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    AI_GATEWAY_URL: str = "http://127.0.0.1:8642"
    AI_GATEWAY_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
