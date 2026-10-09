"""Category CRUD."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession, require_roles
from app.models import Category, Role, User
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate
from app.services import audit

router = APIRouter(prefix="/api/categories", tags=["Categories"])

ManagerOnly = Annotated[User, Depends(require_roles(Role.ADMIN, Role.MANAGER))]


@router.get("", response_model=list[CategoryOut], summary="List categories")
def list_categories(
    db: DbSession,
    _user: CurrentUser,
    q: str | None = Query(default=None, max_length=80, description="Search by name"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Category]:
    stmt = select(Category).order_by(Category.name).limit(limit).offset(offset)
    if q:
        stmt = stmt.where(Category.name.like(f"%{q}%"))
    return list(db.scalars(stmt))


@router.get("/{category_id}", response_model=CategoryOut, summary="Get one category")
def get_category(category_id: int, db: DbSession, _user: CurrentUser) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    return category


@router.post(
    "",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create category",
)
def create_category(
    payload: CategoryCreate,
    db: DbSession,
    user: ManagerOnly,
    request: Request,
) -> Category:
    exists = db.scalar(select(Category).where(Category.name == payload.name))
    if exists:
        raise HTTPException(status_code=409, detail="That category name is already in use.")

    category = Category(name=payload.name, description=payload.description)
    db.add(category)
    db.flush()
    audit.record(
        db,
        user_id=user.id,
        action="create",
        entity="category",
        entity_id=category.id,
        details=f"name={category.name}",
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryOut, summary="Update category")
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: DbSession,
    user: ManagerOnly,
    request: Request,
) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] != category.name:
        clash = db.scalar(select(Category).where(Category.name == updates["name"]))
        if clash:
            raise HTTPException(status_code=409, detail="That category name is already in use.")

    for field, value in updates.items():
        setattr(category, field, value)

    audit.record(
        db,
        user_id=user.id,
        action="update",
        entity="category",
        entity_id=category.id,
        details=",".join(updates.keys()),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(category)
    return category


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete category",
)
def delete_category(
    category_id: int,
    db: DbSession,
    user: ManagerOnly,
    request: Request,
) -> Response:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")

    in_use = db.scalar(
        select(func.count()).select_from(Category).join(Category.products)
        .where(Category.id == category_id)
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: {in_use} product(s) still use this category.",
        )

    audit.record(
        db,
        user_id=user.id,
        action="delete",
        entity="category",
        entity_id=category.id,
        details=f"name={category.name}",
        ip_address=request.client.host if request.client else None,
    )
    db.delete(category)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)