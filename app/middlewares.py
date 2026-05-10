from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram.dispatcher.middlewares.base import BaseMiddleware

from .config import Settings
from .repository import OrderRepository


class ContextMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings, repo: OrderRepository) -> None:
        self._settings = settings
        self._repo = repo

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        data["settings"] = self._settings
        data["repo"] = self._repo
        return await handler(event, data)









