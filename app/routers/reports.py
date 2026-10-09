"""Automated reports — the 'automated report generation' deliverable."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession, require_roles
from app.models import (
    Category,
    Product,
    Role,
    StockTransaction,
    Supplier,
    TransactionType,
    User,
)

router = APIRouter(prefix="/api/reports", tags=["Reports"])

AdminOnly = Annotated[User, Depends(require_roles(Role.ADMIN))]


def _csv_response(rows: list[list], filename: str) -> Response:
    """Build a UTF-8 CSV download response."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------
# Dashboard summary
# --------------------------------------------------------------------------
@router.get("/summary", summary="Dashboard totals")
def summary(db: DbSession, _user: CurrentUser) -> dict:
    total_products = db.scalar(
        select(func.count()).select_from(Product).where(Product.is_active.is_(True))
    ) or 0
    total_categories = db.scalar(select(func.count()).select_from(Category)) or 0
    total_suppliers = db.scalar(
        select(func.count()).select_from(Supplier).where(Supplier.is_active.is_(True))
    ) or 0

    low_stock_count = db.scalar(
        select(func.count())
        .select_from(Product)
        .where(
            Product.is_active.is_(True),
            Product.quantity_in_stock <= Product.reorder_level,
        )
    ) or 0

    total_units = db.scalar(
        select(func.coalesce(func.sum(Product.quantity_in_stock), 0))
        .where(Product.is_active.is_(True))
    ) or 0

    cost_value = db.scalar(
        select(func.coalesce(func.sum(Product.cost_price * Product.quantity_in_stock), 0))
        .where(Product.is_active.is_(True))
    ) or Decimal("0.00")

    retail_value = db.scalar(
        select(func.coalesce(func.sum(Product.unit_price * Product.quantity_in_stock), 0))
        .where(Product.is_active.is_(True))
    ) or Decimal("0.00")

    week_ago = datetime.utcnow() - timedelta(days=7)
    movements_7d = db.scalar(
        select(func.count())
        .select_from(StockTransaction)
        .where(StockTransaction.created_at >= week_ago)
    ) or 0

    return {
        "total_products": total_products,
        "total_categories": total_categories,
        "total_suppliers": total_suppliers,
        "low_stock_count": low_stock_count,
        "total_units_in_stock": int(total_units),
        "inventory_cost_value": str(Decimal(cost_value).quantize(Decimal("0.01"))),
        "inventory_retail_value": str(Decimal(retail_value).quantize(Decimal("0.01"))),
        "potential_margin": str(
            (Decimal(retail_value) - Decimal(cost_value)).quantize(Decimal("0.01"))
        ),
        "movements_last_7_days": movements_7d,
    }


# --------------------------------------------------------------------------
# Low stock
# --------------------------------------------------------------------------
@router.get("/low-stock", summary="Products at or below reorder level")
def low_stock(db: DbSession, _user: CurrentUser) -> dict:
    rows = db.scalars(
        select(Product)
        .where(
            Product.is_active.is_(True),
            Product.quantity_in_stock <= Product.reorder_level,
        )
        .order_by(Product.quantity_in_stock.asc(), Product.name.asc())
    ).all()

    items = [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "quantity_in_stock": p.quantity_in_stock,
            "reorder_level": p.reorder_level,
            "shortfall": max(p.reorder_level - p.quantity_in_stock, 0),
            "supplier_id": p.supplier_id,
        }
        for p in rows
    ]
    return {"count": len(items), "items": items}


# --------------------------------------------------------------------------
# Inventory valuation
# --------------------------------------------------------------------------
@router.get("/valuation", summary="Inventory value by category")
def valuation(
    db: DbSession,
    _user: CurrentUser,
    group_by: Literal["category", "supplier", "none"] = Query(default="category"),
) -> dict:
    qty = func.coalesce(func.sum(Product.quantity_in_stock), 0).label("units")
    cost = func.coalesce(
        func.sum(Product.cost_price * Product.quantity_in_stock), 0
    ).label("cost_value")
    retail = func.coalesce(
        func.sum(Product.unit_price * Product.quantity_in_stock), 0
    ).label("retail_value")

    if group_by == "none":
        row = db.execute(
            select(qty, cost, retail).where(Product.is_active.is_(True))
        ).one()
        return {
            "group_by": "none",
            "groups": [
                {
                    "key": "all",
                    "units": int(row.units),
                    "cost_value": str(Decimal(row.cost_value).quantize(Decimal("0.01"))),
                    "retail_value": str(Decimal(row.retail_value).quantize(Decimal("0.01"))),
                }
            ],
        }

    if group_by == "category":
        stmt = (
            select(Category.id, Category.name, qty, cost, retail)
            .join(Product, Product.category_id == Category.id)
            .where(Product.is_active.is_(True))
            .group_by(Category.id, Category.name)
            .order_by(Category.name)
        )
    else:
        stmt = (
            select(Supplier.id, Supplier.name, qty, cost, retail)
            .join(Product, Product.supplier_id == Supplier.id)
            .where(Product.is_active.is_(True))
            .group_by(Supplier.id, Supplier.name)
            .order_by(Supplier.name)
        )

    groups = [
        {
            "key": key,
            "name": name,
            "units": int(units),
            "cost_value": str(Decimal(cost_value).quantize(Decimal("0.01"))),
            "retail_value": str(Decimal(retail_value).quantize(Decimal("0.01"))),
        }
        for key, name, units, cost_value, retail_value in db.execute(stmt)
    ]
    return {"group_by": group_by, "groups": groups}


# --------------------------------------------------------------------------
# Stock movement over a date range
# --------------------------------------------------------------------------
@router.get("/stock-movement", summary="Units in / out over a date range")
def stock_movement(
    db: DbSession,
    _user: CurrentUser,
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> dict:
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="date_to must be on or after date_from.")

    start = datetime.combine(date_from, time.min)
    end = datetime.combine(date_to, time.max)

    stmt = (
        select(
            StockTransaction.type,
            func.coalesce(func.sum(StockTransaction.quantity), 0).label("qty"),
            func.count().label("count"),
        )
        .where(
            StockTransaction.created_at >= start,
            StockTransaction.created_at <= end,
        )
        .group_by(StockTransaction.type)
    )

    by_type: dict[str, dict] = {
        t.value: {"quantity": 0, "count": 0} for t in TransactionType
    }
    for txn_type, qty, count in db.execute(stmt):
        by_type[txn_type.value] = {"quantity": int(qty), "count": int(count)}

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "movements": by_type,
    }


# --------------------------------------------------------------------------
# Downloadable reports — admin only
# --------------------------------------------------------------------------
@router.get("/download/daily.csv", summary="Daily transaction report (CSV)")
def download_daily(
    db: DbSession,
    _admin: AdminOnly,
    report_date: date = Query(..., alias="date", description="YYYY-MM-DD"),
) -> Response:
    start = datetime.combine(report_date, time.min)
    end = datetime.combine(report_date, time.max)

    rows: list[list] = [
        ["Inventory Management System — Daily report"],
        ["Date", report_date.isoformat()],
        [],
        ["When", "SKU", "Product", "Type", "Quantity", "Balance after",
         "Unit cost", "Reference", "Recorded by"],
    ]

    stmt = (
        select(StockTransaction, Product, User)
        .join(Product, StockTransaction.product_id == Product.id)
        .join(User, StockTransaction.user_id == User.id)
        .where(StockTransaction.created_at >= start, StockTransaction.created_at <= end)
        .order_by(StockTransaction.created_at.asc())
    )
    total_in = total_out = 0
    for txn, product, user in db.execute(stmt):
        if txn.type is TransactionType.IN:
            total_in += txn.quantity
        elif txn.type is TransactionType.OUT:
            total_out += txn.quantity
        rows.append([
            txn.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            product.sku,
            product.name,
            txn.type.value,
            txn.quantity,
            txn.balance_after,
            str(txn.unit_cost) if txn.unit_cost is not None else "",
            txn.reference or "",
            user.full_name,
        ])

    rows.extend([
        [],
        ["Units in", total_in],
        ["Units out", total_out],
        ["Net movement", total_in - total_out],
    ])

    return _csv_response(rows, f"daily-report-{report_date.isoformat()}.csv")


@router.get("/download/monthly.csv", summary="Monthly summary report (CSV)")
def download_monthly(
    db: DbSession,
    _admin: AdminOnly,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
) -> Response:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    start = datetime.combine(date(year, month, 1), time.min)
    end = datetime.combine(next_month, time.min)

    day_rows = db.execute(
        select(
            func.date(StockTransaction.created_at).label("day"),
            StockTransaction.type,
            func.coalesce(func.sum(StockTransaction.quantity), 0).label("qty"),
            func.count().label("count"),
        )
        .where(StockTransaction.created_at >= start, StockTransaction.created_at < end)
        .group_by(func.date(StockTransaction.created_at), StockTransaction.type)
        .order_by(func.date(StockTransaction.created_at))
    ).all()

    by_day: dict[str, dict] = {}
    for day, txn_type, qty, count in day_rows:
        key = day.isoformat() if hasattr(day, "isoformat") else str(day)
        bucket = by_day.setdefault(
            key,
            {"IN": 0, "OUT": 0, "ADJUSTMENT": 0,
             "count_in": 0, "count_out": 0, "count_adj": 0},
        )
        bucket[txn_type.value] = int(qty)
        if txn_type is TransactionType.IN:
            bucket["count_in"] = int(count)
        elif txn_type is TransactionType.OUT:
            bucket["count_out"] = int(count)
        else:
            bucket["count_adj"] = int(count)

    rows: list[list] = [
        ["Inventory Management System — Monthly summary"],
        ["Period", f"{year:04d}-{month:02d}"],
        [],
        ["Day", "Units in", "Units out", "Adjustments",
         "Transactions in", "Transactions out", "Net movement"],
    ]
    total_in = total_out = 0
    for day in sorted(by_day):
        b = by_day[day]
        net = b["IN"] - b["OUT"]
        total_in += b["IN"]
        total_out += b["OUT"]
        rows.append([
            day, b["IN"], b["OUT"], b["ADJUSTMENT"],
            b["count_in"], b["count_out"], net,
        ])

    rows.extend([
        [],
        ["Month total units in", total_in],
        ["Month total units out", total_out],
        ["Month net movement", total_in - total_out],
    ])

    return _csv_response(rows, f"monthly-report-{year:04d}-{month:02d}.csv")


@router.get("/download/yearly.csv", summary="Yearly summary report (CSV)")
def download_yearly(
    db: DbSession,
    _admin: AdminOnly,
    year: int = Query(..., ge=2000, le=2100),
) -> Response:
    start = datetime.combine(date(year, 1, 1), time.min)
    end = datetime.combine(date(year + 1, 1, 1), time.min)

    month_rows = db.execute(
        select(
            func.month(StockTransaction.created_at).label("m"),
            StockTransaction.type,
            func.coalesce(func.sum(StockTransaction.quantity), 0).label("qty"),
        )
        .where(StockTransaction.created_at >= start, StockTransaction.created_at < end)
        .group_by(func.month(StockTransaction.created_at), StockTransaction.type)
        .order_by(func.month(StockTransaction.created_at))
    ).all()

    by_month: dict[int, dict] = {}
    for m, txn_type, qty in month_rows:
        bucket = by_month.setdefault(int(m), {"IN": 0, "OUT": 0, "ADJUSTMENT": 0})
        bucket[txn_type.value] = int(qty)

    rows: list[list] = [
        ["Inventory Management System — Yearly summary"],
        ["Year", str(year)],
        [],
        ["Month", "Units in", "Units out", "Adjustments", "Net movement"],
    ]
    total_in = total_out = 0
    for m in range(1, 13):
        b = by_month.get(m, {"IN": 0, "OUT": 0, "ADJUSTMENT": 0})
        net = b["IN"] - b["OUT"]
        total_in += b["IN"]
        total_out += b["OUT"]
        rows.append([f"{year:04d}-{m:02d}", b["IN"], b["OUT"], b["ADJUSTMENT"], net])

    rows.extend([
        [],
        ["Year total units in", total_in],
        ["Year total units out", total_out],
        ["Year net movement", total_in - total_out],
    ])

    return _csv_response(rows, f"yearly-report-{year}.csv")


@router.get("/download/inventory.csv", summary="Current inventory snapshot (CSV)")
def download_inventory(db: DbSession, _admin: AdminOnly) -> Response:
    rows: list[list] = [
        ["Inventory Management System — Inventory snapshot"],
        ["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")],
        [],
        ["SKU", "Product", "Category", "Supplier", "Unit",
         "In stock", "Reorder at", "Low stock?", "Cost price",
         "Unit price", "Cost value", "Retail value"],
    ]

    total_cost = Decimal("0.00")
    total_retail = Decimal("0.00")

    for p in db.scalars(
        select(Product).where(Product.is_active.is_(True)).order_by(Product.name)
    ):
        cost_val = (p.cost_price or Decimal("0.00")) * p.quantity_in_stock
        retail_val = (p.unit_price or Decimal("0.00")) * p.quantity_in_stock
        total_cost += cost_val
        total_retail += retail_val
        rows.append([
            p.sku,
            p.name,
            p.category.name if p.category else "",
            p.supplier.name if p.supplier else "",
            p.unit,
            p.quantity_in_stock,
            p.reorder_level,
            "YES" if p.quantity_in_stock <= p.reorder_level else "no",
            str(p.cost_price),
            str(p.unit_price),
            str(cost_val),
            str(retail_val),
        ])

    rows.extend([
        [],
        ["Totals", "", "", "", "", "", "", "", "", "",
         str(total_cost.quantize(Decimal("0.01"))),
         str(total_retail.quantize(Decimal("0.01")))],
        ["Potential margin", "", "", "", "", "", "", "", "", "", "",
         str((total_retail - total_cost).quantize(Decimal("0.01")))],
    ])

    return _csv_response(rows, f"inventory-{date.today().isoformat()}.csv")