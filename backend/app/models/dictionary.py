from app.database import Base
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from datetime import datetime


class Manufacturer(Base):
    __tablename__ = "manufacturers"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    website = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "website": self.website or "",
            "description": self.description or "",
        }


class DictCommMethod(Base):
    __tablename__ = "dict_comm_methods"

    id = Column(Integer, primary_key=True)
    method_type = Column(String(20), nullable=False)  # "wired" / "wireless"
    name = Column(String(50), nullable=False, unique=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "method_type": self.method_type,
            "name": self.name,
        }


class DictCommProtocol(Base):
    __tablename__ = "dict_comm_protocols"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
        }


class DictPowerSupply(Base):
    __tablename__ = "dict_power_supplies"

    id = Column(Integer, primary_key=True)
    supply_category = Column(String(50), nullable=False)  # e.g. "内置电池", "外接电源", "PoE"
    name = Column(String(50), nullable=False, unique=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "supply_category": self.supply_category,
            "name": self.name,
        }


class DictSensorMetric(Base):
    __tablename__ = "dict_sensor_metrics"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)  # e.g. "温度", "湿度", "CO2"
    unit = Column(String(20), nullable=True)  # e.g. "℃", "%RH", "ppm"
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "unit": self.unit or "",
        }
