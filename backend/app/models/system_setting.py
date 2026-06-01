"""System settings — key-value config."""
from app.database import Base
from sqlalchemy import Column, Integer, String, Text


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(String(200), nullable=True)

    def to_dict(self):
        return {"id": self.id, "key": self.key, "value": self.value or "", "description": self.description or ""}
