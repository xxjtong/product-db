from app.database import Base, JSONBType
from sqlalchemy import (Column, Integer, String, Boolean, DateTime,
                        ForeignKey, Text, Float, Numeric, CheckConstraint)
from sqlalchemy.orm import relationship
from datetime import datetime


class ProductDependency(Base):
    __tablename__ = "product_dependencies"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    depends_on_product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    depends_on_category_id = Column(Integer, ForeignKey("device_categories.id", ondelete="CASCADE"), nullable=True)
    dependency_type = Column(String(20), default="required")
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)

    __table_args__ = (
        CheckConstraint(
            "depends_on_product_id IS NOT NULL OR depends_on_category_id IS NOT NULL",
            name="ck_dependency_target"
        ),
    )

    product = relationship("Product", foreign_keys=[product_id], backref="dependencies")
    target_product = relationship("Product", foreign_keys=[depends_on_product_id])
    target_category = relationship("Category")

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "depends_on_product_id": self.depends_on_product_id,
            "depends_on_category_id": self.depends_on_category_id,
            "dependency_type": self.dependency_type,
            "description": self.description or "",
            "sort_order": self.sort_order,
        }
