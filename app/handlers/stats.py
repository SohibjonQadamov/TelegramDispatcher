from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import Settings
from ..permissions import is_admin
from ..repository import OrderRepository


logger = logging.getLogger(__name__)
router = Router()


def _format_stats(
    date_str: str, counts: dict[str, int], couriers: list
) -> str:
    created = counts.get("CREATED", 0)
    accepted = counts.get("ACCEPTED", 0)
    delivered = counts.get("DELIVERED", 0)
    cancelled = counts.get("CANCELLED", 0)

    lines = [
        f"Stats for {date_str}:",
        f"Created: {created}",
        f"Accepted: {accepted}",
        f"Delivered: {delivered}",
        f"Cancelled: {cancelled}",
        "",
        "Top couriers:",
    ]
    if not couriers:
        lines.append("No deliveries yet.")
    else:
        for item in couriers:
            lines.append(
                f"- {item.actor_name} ({item.actor_id}): {item.delivered_count}"
            )
    return "\n".join(lines)


@router.message(F.chat.type == "private", Command("stats_today"))
async def stats_today(
    message: Message, settings: Settings, repo: OrderRepository
) -> None:
    if message.from_user is None or not is_admin(message.from_user.id, settings):
        return
    date_str = datetime.now(timezone.utc).date().isoformat()
    try:
        counts, couriers = await repo.get_stats(date_str)
    except Exception:
        logger.exception("Failed to get stats")
        await message.answer("Failed to get stats.")
        return
    await message.answer(_format_stats(date_str, counts, couriers))


@router.message(F.chat.type == "private", Command("stats_date"))
async def stats_date(
    message: Message, settings: Settings, repo: OrderRepository
) -> None:
    if message.from_user is None or not is_admin(message.from_user.id, settings):
        return
    if not message.text:
        return
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Usage: /stats_date YYYY-MM-DD")
        return
    date_str = parts[1]
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("Invalid date format. Use YYYY-MM-DD.")
        return
    try:
        counts, couriers = await repo.get_stats(date_str)
    except Exception:
        logger.exception("Failed to get stats")
        await message.answer("Failed to get stats.")
        return
    await message.answer(_format_stats(date_str, counts, couriers))


@router.message(F.chat.type == "private", Command("order"))
async def order_details(
    message: Message, settings: Settings, repo: OrderRepository
) -> None:
    if message.from_user is None or not is_admin(message.from_user.id, settings):
        return
    if not message.text:
        return
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Usage: /order <id>")
        return
    try:
        order_id = int(parts[1])
    except ValueError:
        await message.answer("Order id must be a number.")
        return

    try:
        order = await repo.get_order(order_id)
        if order is None:
            await message.answer("Order not found.")
            return
        actions = await repo.list_actions(order_id)
    except Exception:
        logger.exception("Failed to load order")
        await message.answer("Failed to load order.")
        return

    lines = [
        f"Order #{order.id}",
        f"Status: {order.status}",
        f"Created by: {order.created_by}",
        f"Created at: {order.created_at}",
        f"Assigned to: {order.assigned_to or '-'}",
        f"Accepted at: {order.accepted_at or '-'}",
        f"Finalized by: {order.finalized_by or '-'}",
        f"Finalized at: {order.finalized_at or '-'}",
        "",
        "Raw text:",
        order.raw_text,
        "",
        "History:",
    ]
    if not actions:
        lines.append("No actions.")
    else:
        for action in actions:
            lines.append(
                f"- {action.timestamp}: {action.action_type} by "
                f"{action.actor_name} ({action.actor_id})"
            )
    await message.answer("\n".join(lines))









