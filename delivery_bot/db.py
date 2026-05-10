from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DB_PATH = Path(__file__).with_name("orders.db")


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_text TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by_id INTEGER NOT NULL,
                created_by_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                accepted_by_id INTEGER,
                accepted_by_name TEXT,
                accepted_at TEXT,
                closed_at TEXT,
                group_message_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS order_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                courier_id INTEGER NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        await conn.commit()


async def create_order(
    raw_text: str,
    created_by_id: int,
    created_by_name: str,
    created_at: str,
) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """
            INSERT INTO orders
                (raw_text, status, created_by_id, created_by_name, created_at)
            VALUES (?, 'NEW', ?, ?, ?)
            """,
            (raw_text, created_by_id, created_by_name, created_at),
        )
        await conn.commit()
        return int(cursor.lastrowid)


async def set_group_message_id(order_id: int, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE orders SET group_message_id = ? WHERE id = ?",
            (message_id, order_id),
        )
        await conn.commit()


async def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE id = ?",
            (order_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def assign_order_if_new(
    order_id: int,
    courier_id: int,
    courier_name: str,
    accepted_at: str,
) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """
            UPDATE orders
            SET status = 'ACCEPTED',
                accepted_by_id = ?,
                accepted_by_name = ?,
                accepted_at = ?
            WHERE id = ? AND status = 'NEW' AND accepted_by_id IS NULL
            """,
            (courier_id, courier_name, accepted_at, order_id),
        )
        await conn.commit()
        return cursor.rowcount == 1


async def finalize_order(
    order_id: int,
    courier_id: int,
    status: str,
    closed_at: str,
) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """
            UPDATE orders
            SET status = ?, closed_at = ?
            WHERE id = ? AND status = 'ACCEPTED' AND accepted_by_id = ?
            """,
            (status, closed_at, order_id, courier_id),
        )
        await conn.commit()
        return cursor.rowcount == 1


async def get_active_order_for_courier(courier_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT * FROM orders
            WHERE accepted_by_id = ? AND status = 'ACCEPTED'
            ORDER BY accepted_at DESC
            LIMIT 1
            """,
            (courier_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def save_location(
    order_id: int,
    courier_id: int,
    latitude: float,
    longitude: float,
    created_at: str,
) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO order_locations
                (order_id, courier_id, latitude, longitude, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (order_id, courier_id, latitude, longitude, created_at),
        )
        await conn.commit()


async def count_status_between(
    start_iso: str, end_iso: str
) -> Dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT status, COUNT(*) as count
            FROM orders
            WHERE created_at >= ? AND created_at <= ?
            GROUP BY status
            """,
            (start_iso, end_iso),
        )
        rows = await cursor.fetchall()
        return {row["status"]: int(row["count"]) for row in rows}


async def fetch_orders_between(
    start_iso: str, end_iso: str, limit: int = 10
) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT *
            FROM orders
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()





