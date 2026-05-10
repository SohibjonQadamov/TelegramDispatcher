from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from ..keyboards import main_menu_kb


router = Router()


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "Salom 👋 Bot ishlayapti!",
        reply_markup=main_menu_kb(),
    )


__all__ = ["router"]

