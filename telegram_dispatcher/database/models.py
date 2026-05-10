from __future__ import annotations

import asyncio
import sqlite3

from .db import DB_PATH


def _insert_order_sync(
    user_id: int,
    raw_text: str,
    created_at: str,
    status: str,
    created_by_name: str | None,
) -> int:
    full_name = "-"
    phone = "-"
    address = "-"
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO orders
                (user_id, full_name, phone, address, created_at, status, created_by_name, raw_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                full_name,
                phone,
                address,
                created_at,
                status,
                created_by_name,
                raw_text,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


async def insert_order(
    user_id: int,
    raw_text: str,
    created_at: str,
    status: str = "NEW",
    created_by_name: str | None = None,
) -> int:
    return await asyncio.to_thread(
        _insert_order_sync,
        user_id,
        raw_text,
        created_at,
        status,
        created_by_name,
    )


def _fetch_orders_between_sync(
    start_iso: str, end_iso: str, limit: int
) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


async def fetch_orders_between(
    start_iso: str, end_iso: str, limit: int = 10
) -> list[dict]:
    return await asyncio.to_thread(_fetch_orders_between_sync, start_iso, end_iso, limit)


def _count_status_between_sync(start_iso: str, end_iso: str) -> dict[str, int]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT status, COUNT(*) as count
            FROM orders
            WHERE created_at >= ? AND created_at <= ?
            GROUP BY status
            """,
            (start_iso, end_iso),
        )
        rows = cursor.fetchall()
        return {row["status"]: int(row["count"]) for row in rows}


async def count_status_between(start_iso: str, end_iso: str) -> dict[str, int]:
    return await asyncio.to_thread(_count_status_between_sync, start_iso, end_iso)


def _fetch_order_by_id_sync(order_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM orders WHERE id = ?",
            (order_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


async def fetch_order_by_id(order_id: int) -> dict | None:
    return await asyncio.to_thread(_fetch_order_by_id_sync, order_id)


def _mark_order_accepted_sync(order_id: int, courier_id: int, courier_name: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE orders
            SET status = 'ACCEPTED',
                accepted_by_id = ?,
                accepted_by_name = ?
            WHERE id = ?
            """,
            (courier_id, courier_name, order_id),
        )
        conn.commit()


async def mark_order_accepted(order_id: int, courier_id: int, courier_name: str) -> None:
    await asyncio.to_thread(_mark_order_accepted_sync, order_id, courier_id, courier_name)


__all__ = [
    "insert_order",
    "fetch_orders_between",
    "count_status_between",
    "fetch_order_by_id",
    "mark_order_accepted",
]





