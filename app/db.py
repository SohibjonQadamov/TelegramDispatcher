from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

import aiosqlite


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def init_schema(self) -> None:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        async with self._lock:
            await self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    group_message_id INTEGER,
                    assigned_to INTEGER,
                    accepted_at TEXT,
                    finalized_by INTEGER,
                    finalized_at TEXT
                );
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    actor_id INTEGER NOT NULL,
                    actor_name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    extra_json TEXT,
                    FOREIGN KEY(order_id) REFERENCES orders(id)
                );
                """
            )
            await self._conn.commit()

    async def acquire(self) -> AsyncIterator[aiosqlite.Connection]:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        async with self._lock:
            yield self._conn









