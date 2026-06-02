"""BOM template schemas."""
from typing import Optional
from pydantic import BaseModel


class BOMTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sheet_name: str = "Sheet1"
    snapshot: dict = {}
    is_default: bool = False


class BOMTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sheet_name: Optional[str] = None
    snapshot: Optional[dict] = None
    is_default: Optional[bool] = None


class SaveAsTemplateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sheet_name: str = "Sheet1"
