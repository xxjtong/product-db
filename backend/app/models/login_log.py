"""Login log model."""
from app.database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime


class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    region = Column(String(100), nullable=True)  # IP geolocation
    success = Column(String(1), default="1")  # "1" = success, "0" = failure
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "ip_address": self.ip_address or "",
            "region": self.region or "",
            "success": self.success == "1",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }
