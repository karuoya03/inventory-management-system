"""Supplier CRUD."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession, require_roles
from app.models import Role, Supplier, User
from app.schemas import SupplierCreate, SupplierOut, SupplierUpdate
from app.services import audit

router = APIRouter(prefix="/api/suppliers", tags=["Suppliers"])

ManagerOnly = Annotated[User, Depends(require_roles(Role.ADMIN, Role.MANAGER))]


@router.get("", response_model=list[SupplierOut], summary="List suppliers")
def list_suppliers(
    db: DbSession,
    _user: CurrentUser,
    q: str | None = Query(default=None, max_length=150),
    active_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Supplier]:
    stmt = select(Supplier).order_by(Supplier.name).limit(limit).offset(offset)
    if q:
        stmt = stmt.where(Supplier.name.like(f"%{q}%"))
    if active_only:
        stmt = stmt.where(Supplier.is_active.is_(True))
    return list(db.scalars(stmt))


@router.get("/{supplier_id}", response_model=SupplierOut, summary="Get one supplier")
def get_supplier(supplier_id: int, db: DbSession, _user: CurrentUser) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return supplier


@router.post(
    "",
    response_model=SupplierOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create supplier",
)
def create_supplier(
    payload: SupplierCreate,
    db: DbSession,
    user: ManagerOnly,
    request: Request,
) -> Supplier:
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    db.flush()
    audit.record(
        db,
        user_id=user.id,
        action="create",
        entity="supplier",
        entity_id=supplier.id,
        details=f"name={supplier.name}",
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(supplier)
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierOut, summary="Update supplier")
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    db: DbSession,
    user: ManagerOnly,
    request: Request,
) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(supplier, field, value)

    audit.record(
        db,
        user_id=user.id,
        action="update",
        entity="supplier",
        entity_id=supplier.id,
        details=",".join(updates.keys()),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete(
    "/{supplier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate supplier",
)
def delete_supplier(
    supplier_id: int,
    db: DbSession,
    user: ManagerOnly,
    request: Request,
) -> Response:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    linked = db.scalar(
        select(func.count()).select_from(Supplier).join(Supplier.products)
        .where(Supplier.id == supplier_id)
    )

    if linked:
        supplier.is_active = False
        action, detail = "deactivate", f"soft-delete, {linked} linked product(s)"
    else:
        action, detail = "delete", f"name={supplier.name}"
        db.delete(supplier)

    audit.record(
        db,
        user_id=user.id,
        action=action,
        entity="supplier",
        entity_id=supplier_id,
        details=detail,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)