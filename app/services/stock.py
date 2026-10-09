"""Stock ledger: the only code path allowed to change quantity_in_stock.

Rules
-----
* IN         : adds `quantity` to the balance.
* OUT        : subtracts `quantity`; rejected if it would go negative.
* ADJUSTMENT : sets the balance to `quantity` (an absolute count, e.g. from a
               physical stock take), recording the delta as the movement.

Every transaction row stores `balance_after`, so the ledger can always be
reconciled against `products.quantity_in_stock`.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, StockTransaction, TransactionType, User
from app.schemas import StockTransactionCreate


def _lock_product(db: Session, product_id: int) -> Product:
    """Fetch a product with a row-level lock so concurrent writes serialize."""
    product = db.execute(
        select(Product).where(Product.id == product_id).with_for_update()
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found.",
        )
    if not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot post stock against a deactivated product.",
        )
    return product


def _compute_new_balance(
    current: int, txn_type: TransactionType, quantity: int
) -> int:
    if txn_type is TransactionType.IN:
        return current + quantity
    if txn_type is TransactionType.OUT:
        new_balance = current - quantity
        if new_balance < 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Insufficient stock: {current} in stock, "
                    f"{quantity} requested."
                ),
            )
        return new_balance
    # ADJUSTMENT — quantity is the absolute new count
    return quantity


def post_transaction(
    db: Session,
    *,
    payload: StockTransactionCreate,
    user: User,
) -> StockTransaction:
    """Atomically apply a stock movement and write the ledger row.

    Runs inside a single DB transaction: if anything raises, the row lock is
    released and no partial state is persisted.
    """
    try:
        product = _lock_product(db, payload.product_id)
        new_balance = _compute_new_balance(
            product.quantity_in_stock, payload.type, payload.quantity
        )

        # For IN movements, optionally update the moving-average cost price.
        if (
            payload.type is TransactionType.IN
            and payload.unit_cost is not None
            and payload.quantity > 0
        ):
            old_value = product.cost_price * product.quantity_in_stock
            added_value = payload.unit_cost * payload.quantity
            total_qty = product.quantity_in_stock + payload.quantity
            if total_qty > 0:
                product.cost_price = ((old_value + added_value) / total_qty).quantize(
                    Decimal("0.01")
                )

        product.quantity_in_stock = new_balance

        txn = StockTransaction(
            product_id=product.id,
            user_id=user.id,
            type=payload.type,
            quantity=payload.quantity,
            unit_cost=payload.unit_cost,
            balance_after=new_balance,
            reference=payload.reference,
            notes=payload.notes,
        )
        db.add(txn)
        db.commit()
        db.refresh(txn)
        return txn
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise