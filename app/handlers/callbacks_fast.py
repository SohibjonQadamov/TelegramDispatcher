from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery


logger = logging.getLogger(__name__)
router = Router()


@router.callback_query()
async def accept_fast(callback: CallbackQuery, bot: Bot) -> None:
    if callback.data is None or not callback.data.startswith("accept:"):
        return
    if callback.from_user is None:
        return
    try:
        order_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Noto‘g‘ri buyurtma ID.", show_alert=True)
        return

    await callback.answer("Qabul qilindi ✅", show_alert=False)

    try:
        await bot.send_message(
            callback.from_user.id,
            f"🧾 Zakaz #{order_id} qabul qilindi",
        )
    except Exception:
        logger.exception("Failed to DM courier for order %s", order_id)

    if callback.message:
        try:
            await bot.delete_message(
                callback.message.chat.id,
                callback.message.message_id,
            )
        except TelegramBadRequest:
            try:
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    text=f"✅ {callback.from_user.full_name} qabul qildi.",
                )
                await bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    reply_markup=None,
                )
            except Exception:
                logger.exception("Failed to edit group message for order %s", order_id)
        except Exception:
            logger.exception("Failed to delete group message for order %s", order_id)





