from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message


router = Router()


@router.message(F.chat.type == "private", CommandStart())
async def start_command(message: Message) -> None:
    await message.answer(
        "Salom! Bot ishlayapti ✅\n"
        "Admin bo‘lsangiz, oddiy matn yuboring — men uni zakaz sifatida guruhga chiqaraman."
    )









