"""Stock transactions — the only way to move stock."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession, require_roles
from app.models import Product, Role, StockTransaction, TransactionType, User
from app.schemas import StockTransactionCreate, StockTransactionOut
from app.services import audit, stock

router = APIRouter(prefix="/api/transactions", tags=["Stock transactions"])

# Clerks can post stock; admins and managers can too.
StaffOrAbove = Annotated[
    User, Depends(require_roles(Role.ADMIN, Role.MANAGER, Role.CLERK))
]


@router.get("", response_model=list[StockTransactionOut], summary="List transactions")
def list_transactions(
    db: DbSession,
    _user: CurrentUser,
    product_id: int | None = Query(default=None, ge=1),
    type: TransactionType | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[StockTransaction]:
    stmt = select(StockTransaction).order_by(StockTransaction.created_at.desc())
    if product_id is not None:
        stmt = stmt.where(StockTransaction.product_id == product_id)
    if type is not None:
        stmt = stmt.where(StockTransaction.type == type)
    if date_from is not None:
        stmt = stmt.where(StockTransaction.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(StockTransaction.created_at <= date_to)
    stmt = stmt.limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.get(
    "/{transaction_id}",
    response_model=StockTransactionOut,
    summary="Get one transaction",
)
def get_transaction(
    transaction_id: int, db: DbSession, _user: CurrentUser
) -> StockTransaction:
    txn = db.get(StockTransaction, transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return txn


@router.post(
    "",
    response_model=StockTransactionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Post a stock movement",
)
def create_transaction(
    payload: StockTransactionCreate,
    db: DbSession,
    user: StaffOrAbove,
    request: Request,
) -> StockTransaction:
    txn = stock.post_transaction(db, payload=payload, user=user)

    audit.record(
        db,
        user_id=user.id,
        action=f"stock_{payload.type.value.lower()}",
        entity="product",
        entity_id=payload.product_id,
        details=f"qty={payload.quantity} balance_after={txn.balance_after}",
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(txn)
    return txn


@router.get(
    "/product/{product_id}/history",
    response_model=list[StockTransactionOut],
    summary="Full ledger for one product",
)
def product_history(
    product_id: int,
    db: DbSession,
    _user: CurrentUser,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[StockTransaction]:
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    stmt = (
        select(StockTransaction)
        .where(StockTransaction.product_id == product_id)
        .order_by(StockTransaction.created_at.desc(), StockTransaction.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))