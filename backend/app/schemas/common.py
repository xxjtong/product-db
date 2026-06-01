"""Shared Pydantic schemas."""
from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int


class MessageResponse(BaseModel):
    ok: bool = True
    message: str = ""
