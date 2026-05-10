from __future__ import annotations

from aiogram import Router

from .handlers import archive_router, callbacks_router, help_router, order_router, start_router


router = Router()
router.include_router(start_router)
router.include_router(order_router)
router.include_router(callbacks_router)
router.include_router(archive_router)
router.include_router(help_router)


__all__ = ["router"]

