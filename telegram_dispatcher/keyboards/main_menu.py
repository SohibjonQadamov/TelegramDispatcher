from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Buyurtma")],
            [KeyboardButton(text="🗂 Arxiv")],
        ],
        resize_keyboard=True,
    )


__all__ = ["main_menu_kb"]

