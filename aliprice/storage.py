"""SQLite-backed storage for tracked products and their price history."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional

DEFAULT_DB_PATH = os.environ.get(
    "ALIPRICE_DB",
    os.path.join(os.path.expanduser("~"), ".aliprice", "aliprice.sqlite3"),
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   TEXT NOT NULL UNIQUE,
    url          TEXT NOT NULL,
    title        TEXT,
    nickname     TEXT,
    currency     TEXT,
    created_at   TEXT NOT NULL,
    last_checked TEXT
);

CREATE TABLE IF NOT EXISTS price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    price      REAL NOT NULL,
    currency   TEXT,
    captured_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_history_product
    ON price_history (product_id, captured_at);
"""


@dataclass
class Product:
    product_id: str
    url: str
    title: Optional[str]
    nickname: Optional[str]
    currency: Optional[str]
    created_at: str
    last_checked: Optional[str]


@dataclass
class PricePoint:
    price: float
    currency: Optional[str]
    captured_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Storage:
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add_product(
        self,
        product_id: str,
        url: str,
        title: Optional[str] = None,
        nickname: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> Product:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO products (product_id, url, title, nickname, currency, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    url      = excluded.url,
                    title    = COALESCE(excluded.title, products.title),
                    nickname = COALESCE(excluded.nickname, products.nickname),
                    currency = COALESCE(excluded.currency, products.currency)
                """,
                (product_id, url, title, nickname, currency, _now_iso()),
            )
        product = self.get_product(product_id)
        assert product is not None
        return product

    def remove_product(self, product_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM products WHERE product_id = ?", (product_id,)
            )
            conn.execute(
                "DELETE FROM price_history WHERE product_id = ?", (product_id,)
            )
            return cur.rowcount > 0

    def get_product(self, product_id: str) -> Optional[Product]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE product_id = ?", (product_id,)
            ).fetchone()
        return _row_to_product(row) if row else None

    def find_product(self, query: str) -> Optional[Product]:
        """Look up a product by product_id or nickname."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE product_id = ? OR nickname = ?",
                (query, query),
            ).fetchone()
        return _row_to_product(row) if row else None

    def list_products(self) -> list[Product]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM products ORDER BY created_at"
            ).fetchall()
        return [_row_to_product(r) for r in rows]

    def update_metadata(
        self,
        product_id: str,
        *,
        title: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE products
                SET title    = COALESCE(?, title),
                    currency = COALESCE(?, currency),
                    last_checked = ?
                WHERE product_id = ?
                """,
                (title, currency, _now_iso(), product_id),
            )

    def record_price(
        self,
        product_id: str,
        price: float,
        currency: Optional[str] = None,
        *,
        captured_at: Optional[str] = None,
    ) -> PricePoint:
        ts = captured_at or _now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO price_history (product_id, price, currency, captured_at)
                VALUES (?, ?, ?, ?)
                """,
                (product_id, price, currency, ts),
            )
        return PricePoint(price=price, currency=currency, captured_at=ts)

    def history(self, product_id: str, limit: Optional[int] = None) -> list[PricePoint]:
        sql = (
            "SELECT price, currency, captured_at FROM price_history "
            "WHERE product_id = ? ORDER BY captured_at ASC"
        )
        params: tuple = (product_id,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (product_id, limit)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            PricePoint(price=r["price"], currency=r["currency"], captured_at=r["captured_at"])
            for r in rows
        ]

    def latest_price(self, product_id: str) -> Optional[PricePoint]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT price, currency, captured_at FROM price_history
                WHERE product_id = ?
                ORDER BY captured_at DESC
                LIMIT 1
                """,
                (product_id,),
            ).fetchone()
        if not row:
            return None
        return PricePoint(
            price=row["price"], currency=row["currency"], captured_at=row["captured_at"]
        )


def _row_to_product(row: sqlite3.Row) -> Product:
    return Product(
        product_id=row["product_id"],
        url=row["url"],
        title=row["title"],
        nickname=row["nickname"],
        currency=row["currency"],
        created_at=row["created_at"],
        last_checked=row["last_checked"],
    )
