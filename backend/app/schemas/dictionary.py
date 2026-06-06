"""Dictionary entry schemas."""
from typing import Optional
from pydantic import BaseModel


class ManufacturerCreate(BaseModel):
    name: str
    website: str = ""
    description: str = ""
    sort_order: int = 0


class ManufacturerUpdate(BaseModel):
    name: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class CommMethodCreate(BaseModel):
    name: str
    method_type: str = "wired"
    description: str = ""


class CommMethodUpdate(BaseModel):
    name: Optional[str] = None
    method_type: Optional[str] = None
    description: Optional[str] = None


class CommProtocolCreate(BaseModel):
    name: str
    description: str = ""


class CommProtocolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PowerSupplyCreate(BaseModel):
    name: str
    supply_category: str = ""
    description: str = ""


class PowerSupplyUpdate(BaseModel):
    name: Optional[str] = None
    supply_category: Optional[str] = None
    description: Optional[str] = None


class SensorMetricCreate(BaseModel):
    name: str
    unit: str = ""
    accuracy: str = ""
    resolution: str = ""
    description: str = ""


class SensorMetricUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    accuracy: Optional[str] = None
    resolution: Optional[str] = None
    description: Optional[str] = None


class SystemSettingUpdate(BaseModel):
    value: str = ""
    description: str = ""
