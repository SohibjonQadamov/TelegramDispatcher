from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .utils import OrderAction, OrderCallback


def build_group_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="☑️ Qabul qildim",
            callback_data=f"accept:{order_id}",
        )
    )
    return builder.as_markup()


def build_dm_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Yetkazildi",
            callback_data=OrderCallback(
                order_id=order_id, action=OrderAction.DELIVER
            ).pack(),
        ),
        InlineKeyboardButton(
            text="❌ Bekor qilindi",
            callback_data=OrderCallback(
                order_id=order_id, action=OrderAction.CANCEL
            ).pack(),
        ),
    )
    return builder.as_markup()


def courier_location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Lokatsiya yuborish", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


