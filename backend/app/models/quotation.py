from app.database import Base, JSONBType
from sqlalchemy import (Column, Integer, String, DateTime,
                        ForeignKey, Text, Numeric)
from sqlalchemy.orm import relationship
from datetime import datetime


class Quotation(Base):
    __tablename__ = "quotations"

    id = Column(Integer, primary_key=True)
    solution_id = Column(Integer, ForeignKey("solutions.id", ondelete="SET NULL"), nullable=True)
    quote_number = Column(String(50), unique=True, nullable=True)
    title = Column(String(200), nullable=True)
    client_name = Column(String(200), nullable=True)
    client_contact = Column(String(100), nullable=True)
    valid_days = Column(Integer, default=15)
    tax_rate = Column(Numeric(5, 2), default=0)
    status = Column(String(20), default="draft")
    total_amount = Column(Numeric(14, 2), default=0)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    items = relationship("QuotationItem", back_populates="quotation",
                         cascade="all, delete-orphan", order_by="QuotationItem.sort_order")

    def to_dict(self):
        return {
            "id": self.id,
            "solution_id": self.solution_id,
            "quote_number": self.quote_number or "",
            "title": self.title or "",
            "client_name": self.client_name or "",
            "client_contact": self.client_contact or "",
            "valid_days": self.valid_days,
            "tax_rate": float(self.tax_rate) if self.tax_rate else 0,
            "status": self.status,
            "total_amount": float(self.total_amount) if self.total_amount else 0,
            "notes": self.notes or "",
            "created_by": self.created_by,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M") if self.updated_at else "",
            "items": [item.to_dict() for item in self.items],
        }


class QuotationItem(Base):
    __tablename__ = "quotation_items"

    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True)
    solution_item_id = Column(Integer, ForeignKey("solution_items.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    product_snapshot = Column(JSONBType, nullable=False)
    quantity = Column(Numeric(10, 2), default=1)
    unit_price = Column(Numeric(12, 2), nullable=True)
    amount = Column(Numeric(14, 2), nullable=True)
    discount_rate = Column(Numeric(5, 2), default=100)
    remark = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)

    quotation = relationship("Quotation", back_populates="items")

    def to_dict(self):
        return {
            "id": self.id,
            "quotation_id": self.quotation_id,
            "solution_item_id": self.solution_item_id,
            "product_id": self.product_id,
            "product_snapshot": self.product_snapshot or {},
            "quantity": float(self.quantity) if self.quantity else 0,
            "unit_price": float(self.unit_price) if self.unit_price else 0,
            "amount": float(self.amount) if self.amount else 0,
            "discount_rate": float(self.discount_rate) if self.discount_rate else 100,
            "remark": self.remark or "",
            "sort_order": self.sort_order,
        }
