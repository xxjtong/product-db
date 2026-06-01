"""Pydantic schemas for request/response validation."""
from app.schemas.auth import LoginRequest, TokenResponse, CreateUserRequest, UpdateUserRequest, UpdateProfileRequest
from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductResponse, ProductListResponse,
    AIFetchRequest, AIFetchResponse, ProductCompareResponse,
)
from app.schemas.category import CategoryCreate, CategoryUpdate, SpecDefinitionCreate, SpecDefinitionUpdate
from app.schemas.solution import SolutionCreate, SolutionUpdate, SolutionItemCreate, SolutionItemUpdate, BOMSnapshotSave

__all__ = [
    "LoginRequest", "TokenResponse", "CreateUserRequest", "UpdateUserRequest", "UpdateProfileRequest",
    "ProductCreate", "ProductUpdate", "ProductResponse", "ProductListResponse",
    "AIFetchRequest", "AIFetchResponse", "ProductCompareResponse",
    "CategoryCreate", "CategoryUpdate", "SpecDefinitionCreate", "SpecDefinitionUpdate",
    "SolutionCreate", "SolutionUpdate", "SolutionItemCreate", "SolutionItemUpdate", "BOMSnapshotSave",
]
