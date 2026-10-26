from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


@contextmanager
def connect(database: str) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def init_db(database: str) -> None:
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_date TEXT NOT NULL,
                product TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price REAL NOT NULL CHECK (unit_price >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
            CREATE INDEX IF NOT EXISTS idx_sales_product ON sales(product);
            CREATE TABLE IF NOT EXISTS forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                start_date TEXT NOT NULL,
                periods INTEGER NOT NULL CHECK (periods > 0),
                model_name TEXT NOT NULL,
                predicted_total REAL NOT NULL,
                predictions_json TEXT NOT NULL,
                metrics_json TEXT,
                actual_total REAL
            );
            """
        )


def query(database: str, sql: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with connect(database) as connection:
        return connection.execute(sql, parameters).fetchall()


def execute(database: str, sql: str, parameters: tuple[Any, ...] = ()) -> int:
    with connect(database) as connection:
        cursor = connection.execute(sql, parameters)
        return int(cursor.lastrowid or 0)
