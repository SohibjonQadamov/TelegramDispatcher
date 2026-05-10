from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message

from ..config import Settings
from ..keyboards import build_group_order_keyboard
from ..permissions import is_admin
from ..repository import OrderRepository
from ..utils import utc_now_iso


logger = logging.getLogger(__name__)
router = Router()
_pending_admin_orders: set[int] = set()


@router.message(F.chat.type == "private", Command("diag"))
async def diag_command(
    message: Message,
    settings: Settings,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return
    if not is_admin(message.from_user.id, settings):
        await message.answer("Siz admin emassiz.")
        return

    group_value = settings.group_chat_id
    await message.answer(f"GROUP_CHAT_ID={group_value} (type={type(group_value).__name__})")

    try:
        test_msg = await bot.send_message(
            settings.group_chat_id,
            "✅ TEST message to group",
        )
    except Exception as exc:
        logger.exception("Diag: failed to send test message to group")
        await message.answer(f"❌ Failed: {exc.__class__.__name__}: {exc}")
        return

    await message.answer(f"✅ Sent to group. message_id={test_msg.message_id}")


@router.message(F.chat.type == "private", F.text)
async def create_order_from_admin(
    message: Message,
    settings: Settings,
    repo: OrderRepository,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return
    if message.text.startswith("/"):
        return
    if not is_admin(message.from_user.id, settings):
        await message.answer("Siz admin emassiz.")
        return
    logger.debug("DEBUG: admin message received")
    logger.debug("admin_id=%s", message.from_user.id)
    logger.debug("admin_text=%s", message.text)

    raw_text = message.text.strip()
    if raw_text == "📦 Buyurtma":
        _pending_admin_orders.add(message.from_user.id)
        await message.answer(
            "Zakazni bitta xabarda yuboring:\n"
            "Nomi/Dokon:\n"
            "Telefon:\n"
            "Manzil:\n"
            "Izoh (ixtiyoriy)"
        )
        return
    if message.from_user.id in _pending_admin_orders:
        _pending_admin_orders.discard(message.from_user.id)
    if not raw_text:
        await message.answer("Order text cannot be empty.")
        return

    created_at = utc_now_iso()
    try:
        order_id = await repo.create_order(raw_text, message.from_user.id, created_at)
        await repo.add_action(
            order_id=order_id,
            action_type="CREATED",
            actor_id=message.from_user.id,
            actor_name=message.from_user.full_name,
            timestamp=created_at,
        )
    except Exception:
        logger.exception("Failed to create order")
        await message.answer("Failed to create order. Please try again.")
        return

    try:
        group_message = await bot.send_message(
            settings.group_chat_id,
            f"🆕 Zakaz #{order_id}\n\n{raw_text}",
            reply_markup=build_group_order_keyboard(order_id),
        )
        await repo.set_group_message_id(order_id, group_message.message_id)
    except Exception as exc:
        logger.exception("Failed to send order to group")
        await message.answer(
            "❌ Buyurtma saqlandi, lekin guruhga yuborilmadi: "
            f"{type(exc).__name__}: {exc}"
        )
        return

    await message.answer(
        "✅ Buyurtma saqlandi va guruhga yuborildi. "
        f"group_message_id={group_message.message_id}"
    )


