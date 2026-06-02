from app.database import Base, JSONBType
from sqlalchemy import (Column, Integer, String, Boolean, DateTime,
                        ForeignKey, Text, Numeric)
from sqlalchemy.orm import relationship
from datetime import datetime


class BOMTemplate(Base):
    __tablename__ = "bom_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    sheet_name = Column(String(100), default="Sheet1")
    snapshot = Column(JSONBType, nullable=False)
    is_default = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "sheet_name": self.sheet_name or "Sheet1",
            "snapshot": self.snapshot or {},
            "is_default": self.is_default,
            "created_by": self.created_by,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M") if self.updated_at else "",
        }


class SolutionBOMSnapshot(Base):
    __tablename__ = "solution_bom_snapshots"

    id = Column(Integer, primary_key=True)
    solution_id = Column(Integer, ForeignKey("solutions.id", ondelete="CASCADE"), nullable=False, unique=True)
    template_id = Column(Integer, ForeignKey("bom_templates.id", ondelete="CASCADE"), nullable=True)
    snapshot = Column(JSONBType, nullable=False)
    exported_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    solution = relationship("Solution", back_populates="bom_snapshot")
    template = relationship("BOMTemplate")

    def to_dict(self):
        return {
            "id": self.id,
            "solution_id": self.solution_id,
            "template_id": self.template_id,
            "snapshot": self.snapshot or {},
            "exported_at": self.exported_at.strftime("%Y-%m-%d %H:%M") if self.exported_at else "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M") if self.updated_at else "",
        }
