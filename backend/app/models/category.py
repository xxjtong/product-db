from app.database import Base, JSONBType
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime


class Category(Base):
    __tablename__ = "device_categories"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("device_categories.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=True, index=True)
    level = Column(Integer, default=1)  # 1=大类, 2=子类, 3=孙子类
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    parent = relationship("Category", remote_side=[id], backref="children")
    spec_definitions = relationship(
        "CategorySpecDefinition", back_populates="category",
        cascade="all, delete-orphan", order_by="CategorySpecDefinition.sort_order"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "name": self.name,
            "slug": self.slug or "",
            "level": self.level or 1,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }


class CategorySpecDefinition(Base):
    __tablename__ = "category_spec_definitions"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("device_categories.id", ondelete="CASCADE"), nullable=False, index=True)
    spec_key = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=False)
    spec_type = Column(String(50), nullable=False)
    unit = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0)
    is_filterable = Column(Boolean, default=True)
    is_comparable = Column(Boolean, default=True)
    display_group = Column(String(100), nullable=True)
    options = Column(JSONBType, nullable=True)
    validation = Column(JSONBType, nullable=True)

    category = relationship("Category", back_populates="spec_definitions")

    def to_dict(self):
        return {
            "id": self.id,
            "category_id": self.category_id,
            "spec_key": self.spec_key,
            "display_name": self.display_name,
            "spec_type": self.spec_type,
            "unit": self.unit or "",
            "sort_order": self.sort_order,
            "is_filterable": self.is_filterable,
            "is_comparable": self.is_comparable,
            "display_group": self.display_group or "",
            "options": self.options,
            "validation": self.validation,
        }
