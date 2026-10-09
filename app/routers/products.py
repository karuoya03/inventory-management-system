"""Product CRUD. `quantity_in_stock` is read-only here — use /api/transactions."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession, require_roles
from app.models import Category, Product, Role, Supplier, User
from app.schemas import ProductCreate, ProductOut, ProductUpdate
from app.services import audit

router = APIRouter(prefix="/api/products", tags=["Products"])

ManagerOnly = Annotated[User, Depends(require_roles(Role.ADMIN, Role.MANAGER))]

SortField = Literal["name", "sku", "quantity_in_stock", "unit_price", "created_at"]


def _resolve_category(
    db: DbSession,
    category_id: int | None,
    category_name: str | None,
) -> int | None:
    """Return a category ID. Creates the category if only a name is given."""
    if category_id is not None:
        if db.get(Category, category_id) is None:
            raise HTTPException(
                status_code=400, detail=f"Category {category_id} does not exist."
            )
        return category_id

    if category_name:
        name = category_name.strip()
        if name:
            existing = db.scalar(
                select(Category).where(func.lower(Category.name) == name.lower())
            )
            if existing:
                return existing.id
            new_cat = Category(name=name)
            db.add(new_cat)
            db.flush()
            return new_cat.id

    return None


def _resolve_supplier(
    db: DbSession,
    supplier_id: int | None,
    supplier_name: str | None,
) -> int | None:
    if supplier_id is not None:
        if db.get(Supplier, supplier_id) is None:
            raise HTTPException(
                status_code=400, detail=f"Supplier {supplier_id} does not exist."
            )
        return supplier_id

    if supplier_name:
        name = supplier_name.strip()
        if name:
            existing = db.scalar(
                select(Supplier).where(func.lower(Supplier.name) == name.lower())
            )
            if existing:
                return existing.id
            new_sup = Supplier(name=name, is_active=True)
            db.add(new_sup)
            db.flush()
            return new_sup.id

    return None


@router.get("", response_model=list[ProductOut], summary="List products")
def list_products(
    db: DbSession,
    _user: CurrentUser,
    q: str | None = Query(default=None, max_length=150, description="Search SKU or name"),
    category_id: int | None = Query(default=None, ge=1),
    supplier_id: int | None = Query(default=None, ge=1),
    low_stock_only: bool = Query(default=False),
    active_only: bool = Query(default=True),
    sort: SortField = Query(default="name"),
    order: Literal["asc", "desc"] = Query(default="asc"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Product]:
    stmt = select(Product)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Product.name.like(like) | Product.sku.like(like))
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if supplier_id is not None:
        stmt = stmt.where(Product.supplier_id == supplier_id)
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
    if low_stock_only:
        stmt = stmt.where(Product.quantity_in_stock <= Product.reorder_level)

    column = getattr(Product, sort)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc())
    stmt = stmt.limit(limit).offset(offset)

    return list(db.scalars(stmt))


@router.get("/{product_id}", response_model=ProductOut, summary="Get one product")
def get_product(product_id: int, db: DbSession, _user: CurrentUser) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product


@router.post(
    "",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create product",
)
def create_product(
    payload: ProductCreate,
    db: DbSession,
    user: ManagerOnly,
    request: Request,
) -> Product:
    if db.scalar(select(Product).where(Product.sku == payload.sku)):
        raise HTTPException(status_code=409, detail="That SKU is already in use.")

    data = payload.model_dump()
    category_id = _resolve_category(
        db, data.pop("category_id", None), data.pop("category_name", None)
    )
    supplier_id = _resolve_supplier(
        db, data.pop("supplier_id", None), data.pop("supplier_name", None)
    )

    product = Product(category_id=category_id, supplier_id=supplier_id, **data)
    db.add(product)
    db.flush()
    audit.record(
        db,
        user_id=user.id,
        action="create",
        entity="product",
        entity_id=product.id,
        details=f"sku={product.sku}",
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductOut, summary="Update product")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: DbSession,
    user: ManagerOnly,
    request: Request,
) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")

    updates = payload.model_dump(exclude_unset=True)

    if "category_id" in updates or "category_name" in updates:
        updates["category_id"] = _resolve_category(
            db,
            updates.pop("category_id", None),
            updates.pop("category_name", None),
        )
    if "supplier_id" in updates or "supplier_name" in updates:
        updates["supplier_id"] = _resolve_supplier(
            db,
            updates.pop("supplier_id", None),
            updates.pop("supplier_name", None),
        )

    for field, value in updates.items():
        setattr(product, field, value)

    audit.record(
        db,
        user_id=user.id,
        action="update",
        entity="product",
        entity_id=product.id,
        details=",".join(updates.keys()),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(product)
    return product


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate product",
)
def delete_product(
    product_id: int,
    db: DbSession,
    user: ManagerOnly,
    request: Request,
) -> Response:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")

    product.is_active = False

    audit.record(
        db,
        user_id=user.id,
        action="deactivate",
        entity="product",
        entity_id=product.id,
        details=f"sku={product.sku}",
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)