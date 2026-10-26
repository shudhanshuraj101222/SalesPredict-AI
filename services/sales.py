from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from database.db import execute, query


def get_sales(database: str, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
    conditions: list[str] = []
    parameters: list[str] = []
    if start:
        conditions.append("sale_date >= ?")
        parameters.append(start)
    if end:
        conditions.append("sale_date <= ?")
        parameters.append(end)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = query(database, f"SELECT * FROM sales {where} ORDER BY sale_date DESC, id DESC", tuple(parameters))
    return [dict(row) for row in rows]


def add_sale(database: str, sale_date: str, product: str, category: str, quantity: int, unit_price: float) -> int:
    return execute(
        database,
        "INSERT INTO sales (sale_date, product, category, quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
        (sale_date, product, category, quantity, unit_price),
    )


def update_sale(database: str, sale_id: int, sale_date: str, product: str, category: str, quantity: int, unit_price: float) -> None:
    execute(
        database,
        "UPDATE sales SET sale_date = ?, product = ?, category = ?, quantity = ?, unit_price = ? WHERE id = ?",
        (sale_date, product, category, quantity, unit_price, sale_id),
    )


def delete_sale(database: str, sale_id: int) -> None:
    execute(database, "DELETE FROM sales WHERE id = ?", (sale_id,))


def sale_by_id(database: str, sale_id: int) -> dict[str, Any] | None:
    rows = query(database, "SELECT * FROM sales WHERE id = ?", (sale_id,))
    return dict(rows[0]) if rows else None


def sales_frame(database: str) -> pd.DataFrame:
    records = query(
        database,
        "SELECT sale_date, product, category, quantity, unit_price, quantity * unit_price AS revenue FROM sales ORDER BY sale_date",
    )
    frame = pd.DataFrame([dict(record) for record in records])
    if not frame.empty:
        frame["sale_date"] = pd.to_datetime(frame["sale_date"])
    return frame


def parse_sale(payload: Any) -> tuple[str, str, str, int, float]:
    if not hasattr(payload, "get"):
        raise ValueError("Submit valid sales details.")
    sale_date = str(payload.get("sale_date", "")).strip()
    try:
        parsed_date = date.fromisoformat(sale_date)
    except ValueError:
        raise ValueError("Enter a valid sale date.") from None
    if parsed_date.isoformat() != sale_date:
        raise ValueError("Enter a valid sale date.")
    product = str(payload.get("product", "")).strip()
    category = str(payload.get("category", "")).strip()
    if not product or len(product) > 120:
        raise ValueError("Product is required and must be 120 characters or fewer.")
    if len(category) > 100:
        raise ValueError("Category must be 100 characters or fewer.")
    try:
        quantity = int(payload.get("quantity", ""))
        price = float(payload.get("unit_price", ""))
    except (TypeError, ValueError):
        raise ValueError("Quantity and unit price must be valid numbers.") from None
    if quantity <= 0 or quantity > 1_000_000:
        raise ValueError("Quantity must be between 1 and 1,000,000.")
    if not 0 <= price <= 1_000_000_000:
        raise ValueError("Unit price must be between 0 and 1,000,000,000.")
    return sale_date, product, category, quantity, price
