"""Download ticket and log models for secure download tracking."""
from app.database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime


class DownloadTicket(Base):
    __tablename__ = "download_tickets"

    id = Column(Integer, primary_key=True)
    ticket = Column(String(64), unique=True, nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "ticket": self.ticket,
            "file_path": self.file_path,
            "expires_at": self.expires_at.strftime("%Y-%m-%d %H:%M:%S") if self.expires_at else "",
        }


class DownloadLog(Base):
    __tablename__ = "download_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    file_type = Column(String(50), nullable=False)  # quotation, spec-sheet, bom, export
    entity_id = Column(Integer, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "file_type": self.file_type,
            "entity_id": self.entity_id or 0,
            "ip_address": self.ip_address or "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
        }
