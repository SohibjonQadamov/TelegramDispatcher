from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..keyboards import main_menu_keyboard


router = Router()


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "Yordam: buyruqlarni yuboring yoki menyudan tanlang.",
        reply_markup=main_menu_keyboard(),
    )


__all__ = ["router"]









