import json
from sqlalchemy import create_engine, TypeDecorator, Text, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=False,
)

# SQLite 默认**不强制**外键，且必须在**每个连接**上显式打开。不开的时候，模型里写的
# ondelete（CASCADE / SET NULL / RESTRICT）全部形同虚设：删除父行只会静默留下孤儿。
# R57 起在连接建立时打开 —— 前提是存量违规已清理、缺失的 ON DELETE 已由迁移
# e0f1a2b3c4d5 补齐（否则删用户/删模板这类操作会从"留孤儿"变成直接报错）。
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class JSONBType(TypeDecorator):
    """JSONB on PostgreSQL, JSON text on SQLite."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return "{}"
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
