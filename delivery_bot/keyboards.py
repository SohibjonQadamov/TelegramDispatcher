from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Buyurtma")],
            [KeyboardButton(text="🗂 Arxiv")],
        ],
        resize_keyboard=True,
    )


def group_order_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="☑️ Qabul qildim",
                    callback_data=f"accept:{order_id}",
                )
            ]
        ]
    )


def courier_dm_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Yetkazildi",
                    callback_data=f"done:{order_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Bekor qilindi",
                    callback_data=f"cancel:{order_id}",
                ),
            ]
        ]
    )


def location_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Lokatsiya yuborish", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def archive_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Bugun", callback_data="archive:today")],
            [InlineKeyboardButton(text="🗓 Oylik", callback_data="archive:month")],
        ]
    )





