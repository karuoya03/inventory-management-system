"""Pydantic request/response models — server-side validation lives here."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.models import Role, TransactionType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ==========================================================================
# Auth
# ==========================================================================
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=72)
    role: Role = Role.CLERK

    @field_validator("password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password is too long.")
        if not any(c.isalpha() for c in value):
            raise ValueError("Password must contain at least one letter.")
        if not any(c.isdigit() for c in value):
            raise ValueError("Password must contain at least one digit.")
        return value

class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    
class UserPublic(ORMModel):
    id: int
    username: str
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ==========================================================================
# Categories
# ==========================================================================
class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class CategoryOut(ORMModel):
    id: int
    name: str
    description: str | None
    created_at: datetime


# ==========================================================================
# Suppliers
# ==========================================================================
class SupplierCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=30, pattern=r"^[0-9+\-\s()]{7,30}$")
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=500)


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class SupplierOut(ORMModel):
    id: int
    name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    address: str | None
    is_active: bool
    created_at: datetime


# ==========================================================================
# Products
# ==========================================================================
class ProductCreate(BaseModel):
    sku: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    category_id: int | None = Field(default=None, ge=1)
    category_name: str | None = Field(default=None, min_length=1, max_length=80)
    supplier_id: int | None = Field(default=None, ge=1)
    supplier_name: str | None = Field(default=None, min_length=1, max_length=150)
    unit: str = Field(default="pcs", min_length=1, max_length=20)
    cost_price: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    unit_price: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    reorder_level: int = Field(default=10, ge=0, le=1_000_000)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    category_id: int | None = Field(default=None, ge=1)
    supplier_id: int | None = Field(default=None, ge=1)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    reorder_level: int | None = Field(default=None, ge=0, le=1_000_000)
    is_active: bool | None = None


class ProductOut(ORMModel):
    id: int
    sku: str
    name: str
    description: str | None
    category_id: int | None
    supplier_id: int | None
    unit: str
    cost_price: Decimal
    unit_price: Decimal
    quantity_in_stock: int
    reorder_level: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ==========================================================================
# Stock transactions
# ==========================================================================
class StockTransactionCreate(BaseModel):
    product_id: int = Field(ge=1)
    type: TransactionType
    quantity: int = Field(ge=0, le=10_000_000)
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate_quantity(self) -> "StockTransactionCreate":
        if self.type in (TransactionType.IN, TransactionType.OUT) and self.quantity <= 0:
            raise ValueError("Quantity must be greater than zero for IN and OUT transactions.")
        return self


class StockTransactionOut(ORMModel):
    id: int
    product_id: int
    user_id: int
    type: TransactionType
    quantity: int
    unit_cost: Decimal | None
    balance_after: int
    reference: str | None
    notes: str | None
    created_at: datetime