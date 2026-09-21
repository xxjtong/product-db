from app.database import Base
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id = Column(Integer, primary_key=True)
    # user_id 可空：删用户时置 NULL 以保留用量审计（迁移 e0f1a2b3c4d5 去掉的 NOT NULL）
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    operation = Column(String(50), nullable=False)
    model = Column(String(50), nullable=True)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    duration_ms = Column(Float, default=0)
    success = Column(Boolean, default=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", foreign_keys=[user_id])

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else (str(self.user_id) if self.user_id else "已删除用户"),
            "operation": self.operation,
            "model": self.model or "",
            "tokens_in": self.tokens_in or 0,
            "tokens_out": self.tokens_out or 0,
            "duration_ms": self.duration_ms or 0,
            "success": bool(self.success),
            "error": self.error or "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
        }
