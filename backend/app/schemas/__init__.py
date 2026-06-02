"""Pydantic schemas for request/response validation."""
from app.schemas.auth import (
    LoginRequest, TokenResponse, CreateUserRequest, UpdateUserRequest, UpdateProfileRequest,
    RegistrationRequest, ResetPasswordRequest, FieldVisibilityUpdate, AIPromptUpdate,
)
from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductResponse, ProductListResponse,
    AIFetchRequest, AIFetchResponse, ProductCompareResponse,
    ProductImportConfirm, DownloadImageRequest,
    ProductDependencyCreate, ProductDependencyUpdate,
)
from app.schemas.category import CategoryCreate, CategoryUpdate, SpecDefinitionCreate, SpecDefinitionUpdate
from app.schemas.solution import SolutionCreate, SolutionUpdate, SolutionItemCreate, SolutionItemUpdate, BOMSnapshotSave
from app.schemas.supplier import SupplierCreate, SupplierUpdate
from app.schemas.quotation import (
    QuotationCreate, QuotationUpdate, QuotationItemCreate, QuotationItemUpdate,
)
from app.schemas.bom_template import BOMTemplateCreate, BOMTemplateUpdate, SaveAsTemplateRequest
from app.schemas.dictionary import ManufacturerCreate, ManufacturerUpdate, SystemSettingUpdate

__all__ = [
    # Auth
    "LoginRequest", "TokenResponse", "CreateUserRequest", "UpdateUserRequest", "UpdateProfileRequest",
    "RegistrationRequest", "ResetPasswordRequest", "FieldVisibilityUpdate", "AIPromptUpdate",
    # Product
    "ProductCreate", "ProductUpdate", "ProductResponse", "ProductListResponse",
    "AIFetchRequest", "AIFetchResponse", "ProductCompareResponse",
    "ProductImportConfirm", "DownloadImageRequest",
    "ProductDependencyCreate", "ProductDependencyUpdate",
    # Category
    "CategoryCreate", "CategoryUpdate", "SpecDefinitionCreate", "SpecDefinitionUpdate",
    # Solution
    "SolutionCreate", "SolutionUpdate", "SolutionItemCreate", "SolutionItemUpdate", "BOMSnapshotSave",
    # Supplier
    "SupplierCreate", "SupplierUpdate",
    # Quotation
    "QuotationCreate", "QuotationUpdate", "QuotationItemCreate", "QuotationItemUpdate",
    # BOM Template
    "BOMTemplateCreate", "BOMTemplateUpdate", "SaveAsTemplateRequest",
    # Dictionary
    "ManufacturerCreate", "ManufacturerUpdate", "SystemSettingUpdate",
]
