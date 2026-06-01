from app.database import Base
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship


class ProductCommMethod(Base):
    __tablename__ = "product_comm_methods"

    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    method_id = Column(Integer, ForeignKey("dict_comm_methods.id", ondelete="CASCADE"), primary_key=True)
    details = Column(String(255), nullable=True)  # e.g. "CN470 8通道", "CAT1 B1/B3/B5/B8"

    method = relationship("DictCommMethod")

    def to_dict(self):
        return {
            "method_id": self.method_id,
            "method_name": self.method.name if self.method else "",
            "method_type": self.method.method_type if self.method else "",
            "details": self.details or "",
        }


class ProductCommProtocol(Base):
    __tablename__ = "product_comm_protocols"

    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    protocol_id = Column(Integer, ForeignKey("dict_comm_protocols.id", ondelete="CASCADE"), primary_key=True)
    direction = Column(String(20), default="both")  # "acquisition" / "forwarding" / "both"

    protocol = relationship("DictCommProtocol")

    def to_dict(self):
        return {
            "protocol_id": self.protocol_id,
            "protocol_name": self.protocol.name if self.protocol else "",
            "direction": self.direction,
        }


class ProductPowerSupply(Base):
    __tablename__ = "product_power_supplies"

    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    power_id = Column(Integer, ForeignKey("dict_power_supplies.id", ondelete="CASCADE"), primary_key=True)
    voltage_range = Column(String(100), nullable=True)  # e.g. "9-24V DC", "5V/1A"
    battery_life = Column(String(100), nullable=True)  # e.g. "5.5年(10分钟上报)"

    power = relationship("DictPowerSupply")

    def to_dict(self):
        return {
            "power_id": self.power_id,
            "power_name": self.power.name if self.power else "",
            "power_category": self.power.supply_category if self.power else "",
            "voltage_range": self.voltage_range or "",
            "battery_life": self.battery_life or "",
        }


class ProductHardwareInterface(Base):
    __tablename__ = "product_hardware_interfaces"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    interface_name = Column(String(50), nullable=False)  # e.g. "RS485", "DI(干接点)", "DO(继电器)"
    quantity = Column(Integer, default=1)
    description = Column(String(255), nullable=True)  # e.g. "波特率1200~115200bps, 每总线128设备"

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "interface_name": self.interface_name,
            "quantity": self.quantity,
            "description": self.description or "",
        }


class ProductSensorCapability(Base):
    __tablename__ = "product_sensor_capabilities"

    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    metric_id = Column(Integer, ForeignKey("dict_sensor_metrics.id", ondelete="CASCADE"), primary_key=True)
    measure_range = Column(String(100), nullable=True)  # e.g. "-20°C~60°C"
    accuracy = Column(String(100), nullable=True)  # e.g. "±0.2°C"
    resolution = Column(String(50), nullable=True)  # e.g. "0.1°C"

    metric = relationship("DictSensorMetric")

    def to_dict(self):
        return {
            "metric_id": self.metric_id,
            "metric_name": self.metric.name if self.metric else "",
            "unit": self.metric.unit if self.metric else "",
            "measure_range": self.measure_range or "",
            "accuracy": self.accuracy or "",
            "resolution": self.resolution or "",
        }


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(500), nullable=False)  # CDN URL or local path
    is_primary = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    alt_text = Column(String(200), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "url": self.url,
            "is_primary": self.is_primary,
            "sort_order": self.sort_order,
            "alt_text": self.alt_text or "",
        }
