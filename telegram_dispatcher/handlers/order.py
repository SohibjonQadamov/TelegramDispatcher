from __future__ import annotations

import os
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..database import insert_order
from ..keyboards import main_menu_kb


router = Router()


class OrderStates(StatesGroup):
    wait_text = State()


def _group_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
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


@router.message(Command("cancel"))
async def cancel_order(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=main_menu_kb())


@router.message(F.text == "📦 Buyurtma")
async def start_order(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderStates.wait_text)
    await message.answer(
        "Zakazni bitta xabarda yuboring:\n"
        "Nomi/Dokon:\n"
        "Telefon:\n"
        "Manzil:\n"
        "Izoh (ixtiyoriy)"
    )


@router.message(OrderStates.wait_text)
async def order_text(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    raw_text = message.text.strip()
    if not raw_text:
        await message.answer("Zakaz matni bo‘sh bo‘lmasligi kerak.")
        return
    await state.clear()

    created_at = datetime.now(timezone.utc).isoformat()
    order_id = await insert_order(
        user_id=message.from_user.id,
        raw_text=raw_text,
        created_at=created_at,
        status="NEW",
        created_by_name=message.from_user.full_name,
    )

    group_id = os.getenv("GROUP_CHAT_ID", "").strip()
    if group_id:
        try:
            await message.bot.send_message(
                int(group_id),
                f"🆕 Zakaz #{order_id}\n\n{raw_text}",
                reply_markup=_group_order_keyboard(order_id),
            )
        except Exception:
            await message.answer("❌ Guruhga yuborishda xatolik.")
            return

    await message.answer("✅ Buyurtma saqlandi va guruhga yuborildi", reply_markup=main_menu_kb())


__all__ = ["router"]





