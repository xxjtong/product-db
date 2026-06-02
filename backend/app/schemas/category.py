"""Category schemas."""
from typing import Optional
from pydantic import BaseModel


class CategoryCreate(BaseModel):
    name: str
    slug: str = ""
    parent_id: Optional[int] = None
    level: int = 1
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    parent_id: Optional[int] = None
    level: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class SpecDefinitionCreate(BaseModel):
    spec_key: str
    display_name: str
    spec_type: str = "string"
    unit: str = ""
    sort_order: int = 0
    is_filterable: bool = True
    is_comparable: bool = True
    display_group: str = ""
    options: Optional[list] = None
    validation: Optional[dict] = None


class SpecDefinitionUpdate(BaseModel):
    spec_key: Optional[str] = None
    display_name: Optional[str] = None
    spec_type: Optional[str] = None
    unit: Optional[str] = None
    sort_order: Optional[int] = None
    is_filterable: Optional[bool] = None
    is_comparable: Optional[bool] = None
    display_group: Optional[str] = None
    options: Optional[list] = None
    validation: Optional[dict] = None
