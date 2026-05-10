from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def archive_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Bugungi zakazlar", callback_data="archive:today")],
            [InlineKeyboardButton(text="🗓 Oylik zakazlar", callback_data="archive:month")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="archive:back")],
        ]
    )


__all__ = ["archive_menu_kb"]





