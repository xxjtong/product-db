from app.database import Base, JSONBType
from sqlalchemy import (Column, Integer, String, Boolean, DateTime,
                        ForeignKey, Text, Numeric)
from sqlalchemy.orm import relationship
from datetime import datetime


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    model = Column(String(100), nullable=True, index=True)  # 产品型号: EG71, AM307
    name = Column(String(200), nullable=False, index=True)
    sku = Column(String(100), nullable=True, index=True)  # ERP SKU (optional)
    category_id = Column(Integer, ForeignKey("device_categories.id"), nullable=False, index=True)
    manufacturer_id = Column(Integer, ForeignKey("manufacturers.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)

    unit = Column(String(20), default="台")
    base_price = Column(Numeric(10, 2), nullable=True)
    cost_price = Column(Numeric(10, 2), nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)  # 主图 URL (denormalized for list page)
    product_url = Column(String(500), nullable=True)  # 官方详情页链接
    status = Column(String(20), default="active", index=True)
    parent_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)

    specs = Column(JSONBType, default={})  # 物理特性兜底: 尺寸/重量/IP等级/材质等
    urls = Column(JSONBType, default={})
    custom_fields = Column(JSONBType, default={})

    pinyin_search = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    category = relationship("Category", backref="products")
    manufacturer = relationship("Manufacturer", backref="products")
    supplier = relationship("Supplier", backref="products")
    parent = relationship("Product", remote_side=[id], backref="variants")

    # Mapping relationships
    comm_methods = relationship("ProductCommMethod", backref="product", cascade="all, delete-orphan")
    comm_protocols = relationship("ProductCommProtocol", backref="product", cascade="all, delete-orphan")
    power_supplies = relationship("ProductPowerSupply", backref="product", cascade="all, delete-orphan")
    hardware_interfaces = relationship("ProductHardwareInterface", backref="product", cascade="all, delete-orphan",
                                       order_by="ProductHardwareInterface.id")
    sensor_capabilities = relationship("ProductSensorCapability", backref="product", cascade="all, delete-orphan")
    images = relationship("ProductImage", backref="product", cascade="all, delete-orphan",
                          order_by="ProductImage.sort_order")

    def to_dict(self, category_map=None, supplier_map=None, manufacturer_map=None):
        cat_name = None
        if self.category_id:
            if category_map:
                cat_name = category_map.get(self.category_id)
            elif self.category:
                cat_name = self.category.name

        supplier_name = None
        if self.supplier_id:
            if supplier_map:
                supplier_name = supplier_map.get(self.supplier_id)
            elif self.supplier:
                supplier_name = self.supplier.name

        manufacturer_name = None
        if self.manufacturer_id:
            if manufacturer_map:
                manufacturer_name = manufacturer_map.get(self.manufacturer_id)
            elif self.manufacturer:
                manufacturer_name = self.manufacturer.name

        return {
            "id": self.id,
            "model": self.model or "",
            "name": self.name,
            "sku": self.sku or "",
            "category_id": self.category_id,
            "category_name": cat_name or "",
            "manufacturer_id": self.manufacturer_id,
            "manufacturer_name": manufacturer_name or "",
            "supplier_id": self.supplier_id,
            "supplier_name": supplier_name or "",
            "unit": self.unit or "台",
            "base_price": float(self.base_price) if self.base_price else 0,
            "cost_price": float(self.cost_price) if self.cost_price else 0,
            "description": self.description or "",
            "image_url": self.image_url or "",
            "product_url": self.product_url or "",
            "status": self.status or "active",
            "parent_id": self.parent_id,
            "comm_methods": [cm.to_dict() for cm in self.comm_methods] if self.comm_methods else [],
            "comm_protocols": [cp.to_dict() for cp in self.comm_protocols] if self.comm_protocols else [],
            "power_supplies": [ps.to_dict() for ps in self.power_supplies] if self.power_supplies else [],
            "hardware_interfaces": [hi.to_dict() for hi in self.hardware_interfaces] if self.hardware_interfaces else [],
            "sensor_capabilities": [sc.to_dict() for sc in self.sensor_capabilities] if self.sensor_capabilities else [],
            "images": [img.to_dict() for img in self.images] if self.images else [],
            "specs": self.specs or {},
            "urls": self.urls or {},
            "custom_fields": self.custom_fields or {},
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M") if self.updated_at else "",
        }
