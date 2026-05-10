from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Optional

from .db import Database


@dataclass(slots=True)
class Order:
    id: int
    raw_text: str
    status: str
    created_by: int
    created_at: str
    group_message_id: Optional[int]
    assigned_to: Optional[int]
    accepted_at: Optional[str]
    finalized_by: Optional[int]
    finalized_at: Optional[str]


@dataclass(slots=True)
class Action:
    id: int
    order_id: int
    action_type: str
    actor_id: int
    actor_name: str
    timestamp: str
    extra_json: Optional[str]


@dataclass(slots=True)
class CourierStat:
    actor_id: int
    actor_name: str
    delivered_count: int


class OrderRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_order(
        self, raw_text: str, created_by: int, created_at: str
    ) -> int:
        async for conn in self._db.acquire():
            cursor = await conn.execute(
                """
                INSERT INTO orders (raw_text, status, created_by, created_at)
                VALUES (?, 'NEW', ?, ?)
                """,
                (raw_text, created_by, created_at),
            )
            await conn.commit()
            return int(cursor.lastrowid)
        raise RuntimeError("DB acquire failed")

    async def set_group_message_id(self, order_id: int, message_id: int) -> None:
        async for conn in self._db.acquire():
            await conn.execute(
                "UPDATE orders SET group_message_id = ? WHERE id = ?",
                (message_id, order_id),
            )
            await conn.commit()

    async def clear_group_message_id(self, order_id: int) -> None:
        async for conn in self._db.acquire():
            await conn.execute(
                "UPDATE orders SET group_message_id = NULL WHERE id = ?",
                (order_id,),
            )
            await conn.commit()

    async def get_order(self, order_id: int) -> Optional[Order]:
        async for conn in self._db.acquire():
            cursor = await conn.execute(
                "SELECT * FROM orders WHERE id = ?",
                (order_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return Order(**dict(row))
        return None

    async def get_active_order_for_courier(self, courier_id: int) -> Optional[Order]:
        async for conn in self._db.acquire():
            cursor = await conn.execute(
                """
                SELECT * FROM orders
                WHERE assigned_to = ?
                  AND status = 'ACCEPTED'
                ORDER BY accepted_at DESC
                LIMIT 1
                """,
                (courier_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return Order(**dict(row))
        return None

    async def update_accept(
        self,
        order_id: int,
        courier_id: int,
        accepted_at: str,
    ) -> None:
        async for conn in self._db.acquire():
            await conn.execute(
                """
                UPDATE orders
                SET status = 'ACCEPTED',
                    assigned_to = ?,
                    accepted_at = ?
                WHERE id = ?
                """,
                (courier_id, accepted_at, order_id),
            )
            await conn.commit()

    async def update_finalize(
        self,
        order_id: int,
        status: str,
        actor_id: int,
        finalized_at: str,
    ) -> None:
        async for conn in self._db.acquire():
            await conn.execute(
                """
                UPDATE orders
                SET status = ?,
                    finalized_by = ?,
                    finalized_at = ?
                WHERE id = ?
                """,
                (status, actor_id, finalized_at, order_id),
            )
            await conn.commit()

    async def add_action(
        self,
        order_id: int,
        action_type: str,
        actor_id: int,
        actor_name: str,
        timestamp: str,
        extra: dict | None = None,
    ) -> None:
        extra_json = json.dumps(extra, ensure_ascii=True) if extra else None
        async for conn in self._db.acquire():
            await conn.execute(
                """
                INSERT INTO actions
                    (order_id, action_type, actor_id, actor_name, timestamp, extra_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (order_id, action_type, actor_id, actor_name, timestamp, extra_json),
            )
            await conn.commit()

    async def list_actions(self, order_id: int) -> Iterable[Action]:
        async for conn in self._db.acquire():
            cursor = await conn.execute(
                """
                SELECT * FROM actions
                WHERE order_id = ?
                ORDER BY id ASC
                """,
                (order_id,),
            )
            rows = await cursor.fetchall()
            return [Action(**dict(row)) for row in rows]
        return []

    async def get_stats(self, date: str) -> tuple[dict[str, int], list[CourierStat]]:
        async for conn in self._db.acquire():
            cursor = await conn.execute(
                """
                SELECT action_type, COUNT(*) as count
                FROM actions
                WHERE DATE(timestamp) = DATE(?)
                GROUP BY action_type
                """,
                (date,),
            )
            rows = await cursor.fetchall()
            counts = {row["action_type"]: int(row["count"]) for row in rows}

            cursor = await conn.execute(
                """
                SELECT actor_id, actor_name, COUNT(*) as delivered_count
                FROM actions
                WHERE action_type = 'DELIVERED'
                  AND DATE(timestamp) = DATE(?)
                GROUP BY actor_id, actor_name
                ORDER BY delivered_count DESC
                LIMIT 5
                """,
                (date,),
            )
            rows = await cursor.fetchall()
            top = [
                CourierStat(
                    actor_id=int(row["actor_id"]),
                    actor_name=row["actor_name"],
                    delivered_count=int(row["delivered_count"]),
                )
                for row in rows
            ]
            return counts, top
        return {}, []

