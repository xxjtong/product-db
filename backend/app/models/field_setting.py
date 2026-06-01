"""Field visibility — admin controls which fields are visible to non-admin users."""
from app.database import Base
from sqlalchemy import Column, Integer, String, Boolean


class FieldSetting(Base):
    __tablename__ = "field_settings"

    id = Column(Integer, primary_key=True)
    field_name = Column(String(50), unique=True, nullable=False, index=True)
    user_visible = Column(Boolean, default=True)

    def to_dict(self):
        return {"field_name": self.field_name, "user_visible": self.user_visible}
