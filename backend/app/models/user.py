from app.database import Base
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime, timezone


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(10), default="user")
    is_active = Column(Boolean, default=True)
    email = Column(String(200), nullable=True)
    # 成本价可见性的**按用户覆盖**，三态：
    #   NULL = 跟随全局字段开关（默认，存量用户行为不变）
    #   True = 允许  /  False = 禁止（即使全局开关打开）
    # admin 恒可见，不受此列影响；判定统一走 services.field_visibility.cost_visible
    can_view_cost = Column(Boolean, nullable=True, default=None)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "is_active": self.is_active,
            "email": self.email or "",
            "can_view_cost": self.can_view_cost,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
            "last_login": self.last_login.strftime("%Y-%m-%d %H:%M") if self.last_login else "",
        }
