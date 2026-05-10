from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "orders.db"


def _ensure_tables() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                created_at TEXT NOT NULL,
                raw_text TEXT,
                status TEXT NOT NULL DEFAULT 'NEW',
                created_by_name TEXT,
                accepted_by_id INTEGER,
                accepted_by_name TEXT
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()}
        if "raw_text" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN raw_text TEXT")
        if "status" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN status TEXT NOT NULL DEFAULT 'NEW'")
        if "created_by_name" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN created_by_name TEXT")
        if "accepted_by_id" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN accepted_by_id INTEGER")
        if "accepted_by_name" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN accepted_by_name TEXT")
        conn.commit()


async def init_db() -> None:
    await asyncio.to_thread(_ensure_tables)


__all__ = ["DB_PATH", "init_db"]





