"""Download log models for download audit tracking."""
from app.database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime, timezone


class DownloadLog(Base):
    __tablename__ = "download_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    file_type = Column(String(50), nullable=False)  # quotation, spec-sheet, bom, export
    entity_id = Column(Integer, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "file_type": self.file_type,
            "entity_id": self.entity_id or 0,
            "ip_address": self.ip_address or "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
        }
