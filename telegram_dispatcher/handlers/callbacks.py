from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery

from ..database import fetch_order_by_id, mark_order_accepted


logger = logging.getLogger(__name__)
router = Router()


@router.callback_query()
async def debug_cb(callback: CallbackQuery) -> None:
    print("DEBUG CALLBACK:", callback.data)
    await callback.answer("DEBUG: callback received", show_alert=False)


@router.callback_query()
async def accept_order(callback: CallbackQuery) -> None:
    if callback.data is None or not callback.data.startswith("accept:"):
        return
    await callback.answer("Qabul qilindi ✅", show_alert=False)
    print("ACCEPT CLICKED data=%s user=%s", callback.data, callback.from_user.id if callback.from_user else None)

    if callback.from_user is None:
        return
    try:
        order_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.message.answer("Zakaz ID noto‘g‘ri.")
        return
    order = await fetch_order_by_id(order_id)
    if order is None:
        await callback.message.answer("Zakaz topilmadi.")
        return

    try:
        await callback.bot.send_message(
            callback.from_user.id,
            f"🆕 Zakaz #{order['id']}\n\n{order.get('raw_text') or ''}",
        )
        await mark_order_accepted(
            order_id=order["id"],
            courier_id=callback.from_user.id,
            courier_name=callback.from_user.full_name,
        )
        if callback.message:
            try:
                await callback.bot.delete_message(
                    callback.message.chat.id,
                    callback.message.message_id,
                )
            except TelegramBadRequest:
                try:
                    await callback.bot.edit_message_text(
                        chat_id=callback.message.chat.id,
                        message_id=callback.message.message_id,
                        text=f"✅ {callback.from_user.full_name} qabul qildi.",
                    )
                    await callback.bot.edit_message_reply_markup(
                        chat_id=callback.message.chat.id,
                        message_id=callback.message.message_id,
                        reply_markup=None,
                    )
                except Exception:
                    logger.exception("Failed to edit group message for order %s", order["id"])
    except TelegramForbiddenError:
        await callback.message.answer(
            f"⚠️ {callback.from_user.full_name}, botga shaxsiy chatdan /start bosing."
        )
    except Exception:
        logger.exception("Failed to DM courier")


__all__ = ["router"]

