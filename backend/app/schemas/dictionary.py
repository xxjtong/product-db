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


class SystemSettingUpdate(BaseModel):
    value: str = ""
    description: str = ""
