from app.database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func


class ProductFile(Base):
    __tablename__ = "product_files"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_url = Column(String(500), nullable=False)
    file_size = Column(Integer, default=0)
    file_type = Column(String(50), default="")
    label = Column(String(100), default="")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "filename": self.filename,
            "file_url": self.file_url,
            "file_size": self.file_size,
            "file_type": self.file_type or "",
            "label": self.label or "",
            "sort_order": self.sort_order or 0,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }
