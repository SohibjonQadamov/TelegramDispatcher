from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message

from ..config import Settings
from ..keyboards import build_dm_order_keyboard, courier_location_keyboard
from ..permissions import is_admin
from ..repository import OrderRepository
from ..utils import OrderAction, OrderCallback, format_order_message, utc_now_iso


logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(OrderCallback.filter())
async def handle_order_callback(
    callback: CallbackQuery,
    callback_data: OrderCallback,
    settings: Settings,
    repo: OrderRepository,
    bot: Bot,
) -> None:
    if callback.from_user is None:
        return
    order = await repo.get_order(callback_data.order_id)
    if order is None:
        await callback.answer("Order not found.", show_alert=True)
        return

    if callback_data.action == OrderAction.ACCEPT:
        await _handle_accept(callback, order, settings, repo, bot)
        return
    await _handle_finalize(callback, order, callback_data.action, settings, repo, bot)


@router.message(F.chat.type == "private", F.location)
async def handle_location(
    message: Message,
    settings: Settings,
    repo: OrderRepository,
    bot: Bot,
) -> None:
    if message.from_user is None or message.location is None:
        return
    order = await repo.get_active_order_for_courier(message.from_user.id)
    if order is None:
        await message.answer("Faol buyurtma topilmadi.")
        return

    location = message.location
    timestamp = utc_now_iso()
    try:
        await repo.add_action(
            order_id=order.id,
            action_type="LOCATION",
            actor_id=message.from_user.id,
            actor_name=message.from_user.full_name,
            timestamp=timestamp,
            extra={"latitude": location.latitude, "longitude": location.longitude},
        )
    except Exception:
        logger.exception("Failed to save location action")

    try:
        await bot.send_location(
            settings.archive_channel_id,
            latitude=location.latitude,
            longitude=location.longitude,
            caption=(
                f"📍 Lokatsiya | Zakaz #{order.id} | "
                f"Kuryer: {message.from_user.full_name}"
            ),
        )
    except Exception:
        logger.exception("Failed to send location to archive")

    for admin_id in settings.admin_ids:
        try:
            await bot.send_location(
                admin_id,
                latitude=location.latitude,
                longitude=location.longitude,
                caption=(
                    f"📍 Lokatsiya | Zakaz #{order.id} | "
                    f"Kuryer: {message.from_user.full_name}"
                ),
            )
        except Exception:
            logger.exception("Failed to send location to admin %s", admin_id)


async def _handle_accept(
    callback: CallbackQuery,
    order,
    settings: Settings,
    repo: OrderRepository,
    bot: Bot,
) -> None:
    if callback.from_user is None:
        return
    if is_admin(callback.from_user.id, settings):
        await callback.answer("Admins cannot accept orders.", show_alert=True)
        return
    if order.status != "NEW":
        await callback.answer("Already taken.", show_alert=True)
        return

    courier_id = callback.from_user.id
    courier_name = callback.from_user.full_name
    accepted_at = utc_now_iso()
    print("ACCEPT clicked", order.id, courier_id)

    await callback.answer("Qabul qilinyapti...", show_alert=False)

    try:
        await bot.send_message(
            courier_id,
            format_order_message(order.id, order.raw_text),
            reply_markup=build_dm_order_keyboard(order.id),
        )
        await bot.send_message(
            courier_id,
            "📍 Lokatsiya yuborish uchun tugmani bosing:",
            reply_markup=courier_location_keyboard(),
        )
        print("DM sent OK")
    except TelegramForbiddenError:
        print("DM failed", "TelegramForbiddenError")
        logger.exception("Failed to DM courier (forbidden)")
        try:
            await bot.send_message(
                settings.group_chat_id,
                f"⚠️ {courier_name}, botga shaxsiy chatdan /start bosing, "
                "keyin qayta 'Qabul qildim' bosing.",
            )
        except Exception:
            logger.exception("Failed to notify group about private start requirement")
        return
    except Exception as exc:
        print("DM failed", repr(exc))
        logger.exception("Failed to send order to courier")
        try:
            await bot.send_message(
                settings.group_chat_id,
                f"⚠️ {courier_name}, botga shaxsiy chatdan /start bosing, "
                "keyin qayta 'Qabul qildim' bosing.",
            )
        except Exception:
            logger.exception("Failed to notify group about private start requirement")
        return

    try:
        await repo.update_accept(order.id, courier_id, accepted_at)
        await repo.add_action(
            order_id=order.id,
            action_type="ACCEPTED",
            actor_id=courier_id,
            actor_name=courier_name,
            timestamp=accepted_at,
        )
    except Exception:
        logger.exception("Failed to update order accept state")
        await callback.answer("Failed to accept order.", show_alert=True)
        return

    try:
        await bot.send_message(
            settings.group_chat_id,
            f"✅ Zakaz #{order.id} {courier_name} tomonidan qabul qilindi.",
        )
        await bot.send_message(
            settings.archive_channel_id,
            f"Order #{order.id} accepted by {courier_name} ({courier_id}) at {accepted_at}",
        )
    except Exception:
        logger.exception("Failed to log accept to archive")

    await _try_delete_or_edit_group_message(
        callback, order, courier_name, settings, repo, bot
    )
    await callback.answer("Accepted.")


async def _try_delete_or_edit_group_message(
    callback: CallbackQuery,
    order,
    courier_name: str,
    settings: Settings,
    repo: OrderRepository,
    bot: Bot,
) -> None:
    if order.group_message_id is None:
        return
    try:
        await bot.delete_message(settings.group_chat_id, order.group_message_id)
        await repo.clear_group_message_id(order.id)
        return
    except TelegramBadRequest:
        logger.info("Group message already deleted for order %s", order.id)
        await repo.clear_group_message_id(order.id)
        return
    except Exception:
        logger.exception("Failed to delete group message, attempting edit")

    try:
        await bot.edit_message_text(
            chat_id=settings.group_chat_id,
            message_id=order.group_message_id,
            text=f"✅ {courier_name} qabul qildi. Yetkazilmoqda...",
        )
        await bot.edit_message_reply_markup(
            chat_id=settings.group_chat_id,
            message_id=order.group_message_id,
            reply_markup=None,
        )
    except Exception:
        logger.exception("Failed to edit group message for order %s", order.id)


async def _handle_finalize(
    callback: CallbackQuery,
    order,
    action: OrderAction,
    settings: Settings,
    repo: OrderRepository,
    bot: Bot,
) -> None:
    if callback.from_user is None:
        return
    if order.status in {"DELIVERED", "CANCELLED"}:
        await callback.answer("Order already finalized.", show_alert=True)
        return
    if order.status != "ACCEPTED" or order.assigned_to is None:
        await callback.answer("Order is not accepted yet.", show_alert=True)
        return
    if order.assigned_to != callback.from_user.id:
        await callback.answer("Only assigned courier can finalize.", show_alert=True)
        return

    status = "DELIVERED" if action == OrderAction.DELIVER else "CANCELLED"
    finalized_at = utc_now_iso()
    actor_id = callback.from_user.id
    actor_name = callback.from_user.full_name

    try:
        await repo.update_finalize(order.id, status, actor_id, finalized_at)
        await repo.add_action(
            order_id=order.id,
            action_type=status,
            actor_id=actor_id,
            actor_name=actor_name,
            timestamp=finalized_at,
        )
    except Exception:
        logger.exception("Failed to finalize order")
        await callback.answer("Failed to finalize order.", show_alert=True)
        return

    try:
        await bot.send_message(
            settings.archive_channel_id,
            f"Order #{order.id} {status.lower()} by {actor_name} ({actor_id}) at {finalized_at}",
        )
    except Exception:
        logger.exception("Failed to log finalize to archive")

    await _try_delete_group_message(settings, order, repo, bot)

    try:
        await callback.message.answer(f"Order #{order.id} marked as {status}.")
    except Exception:
        logger.exception("Failed to send finalize confirmation")

    await callback.answer("Updated.")


async def _try_delete_group_message(
    settings: Settings,
    order,
    repo: OrderRepository,
    bot: Bot,
) -> None:
    if order.group_message_id is None:
        return
    try:
        await bot.delete_message(settings.group_chat_id, order.group_message_id)
        await repo.clear_group_message_id(order.id)
    except TelegramBadRequest:
        await repo.clear_group_message_id(order.id)
    except Exception:
        logger.exception("Failed to delete group message for order %s", order.id)


@router.callback_query()
async def any_callback_debug(callback: CallbackQuery) -> None:
    # Avoid intercepting known order callbacks; those are handled above.
    if callback.data and callback.data.startswith("order:"):
        return
    print("DEBUG callback data:", callback.data)
    await callback.answer("DEBUG callback received", show_alert=False)


