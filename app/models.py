"""SQLAlchemy 2.0 models — the single source of truth for the schema."""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------
class Role(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    CLERK = "clerk"


class TransactionType(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"
    ADJUSTMENT = "ADJUSTMENT"


def _enum_values(enum_cls) -> list[str]:
    """Store the enum *value* (lowercase) rather than the member name."""
    return [member.value for member in enum_cls]


def _role_column() -> SAEnum:
    return SAEnum(Role, native_enum=False, length=20, values_callable=_enum_values)


def _type_column() -> SAEnum:
    return SAEnum(
        TransactionType, native_enum=False, length=20, values_callable=_enum_values
    )


# --------------------------------------------------------------------------
# Mixins
# --------------------------------------------------------------------------
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(_role_column(), default=Role.CLERK, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    transactions: Mapped[list["StockTransaction"]] = relationship(
        back_populates="user", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.id} {self.username} ({self.role.value})>"


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------
class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


# --------------------------------------------------------------------------
# Suppliers
# --------------------------------------------------------------------------
class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    contact_person: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    products: Mapped[list["Product"]] = relationship(back_populates="supplier")


# --------------------------------------------------------------------------
# Products
# --------------------------------------------------------------------------
class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("quantity_in_stock >= 0", name="ck_products_stock_non_negative"),
        CheckConstraint("reorder_level >= 0", name="ck_products_reorder_non_negative"),
        CheckConstraint("cost_price >= 0", name="ck_products_cost_non_negative"),
        CheckConstraint("unit_price >= 0", name="ck_products_price_non_negative"),
        Index("ix_products_active_name", "is_active", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    unit: Mapped[str] = mapped_column(String(20), default="pcs", nullable=False)
    cost_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )

    # Only ever mutated through stock transactions — never directly by an update.
    quantity_in_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_level: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped["Category | None"] = relationship(back_populates="products")
    supplier: Mapped["Supplier | None"] = relationship(back_populates="products")
    transactions: Mapped[list["StockTransaction"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    @property
    def is_low_stock(self) -> bool:
        return self.quantity_in_stock <= self.reorder_level

    @property
    def stock_value(self) -> Decimal:
        return (self.cost_price or Decimal("0.00")) * self.quantity_in_stock


# --------------------------------------------------------------------------
# Stock transactions (the ledger — append only)
# --------------------------------------------------------------------------
class StockTransaction(Base):
    __tablename__ = "stock_transactions"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_txn_quantity_non_negative"),
        Index("ix_txn_product_created", "product_id", "created_at"),
        Index("ix_txn_type_created", "type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    type: Mapped[TransactionType] = mapped_column(_type_column(), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)

    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    product: Mapped["Product"] = relationship(back_populates="transactions")
    user: Mapped["User"] = relationship(back_populates="transactions")


# --------------------------------------------------------------------------
# Audit log
# --------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )