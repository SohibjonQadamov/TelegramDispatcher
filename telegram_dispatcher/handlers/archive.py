from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from ..database import count_status_between, fetch_orders_between
from ..keyboards import archive_menu_kb, main_menu_kb


router = Router()


def _format_archive(orders: list[dict], counts: dict[str, int]) -> str:
    total_new = counts.get("NEW", 0)
    total_accepted = counts.get("ACCEPTED", 0)
    total_delivered = counts.get("DELIVERED", 0)
    total_cancelled = counts.get("CANCELLED", 0)

    lines = [
        f"NEW: {total_new}",
        f"ACCEPTED: {total_accepted}",
        f"DELIVERED: {total_delivered}",
        f"CANCELLED: {total_cancelled}",
        "",
        "Oxirgi zakazlar:",
    ]
    if not orders:
        lines.append("Zakazlar yo‘q.")
        return "\n".join(lines)

    for item in orders:
        created_by = item.get("created_by_name") or "-"
        created_by_id = item.get("user_id") or "-"
        accepted_by = item.get("accepted_by_name") or "-"
        accepted_by_id = item.get("accepted_by_id") or "-"
        status = item.get("status") or "-"
        lines.extend(
            [
                f"#{item.get('id')} | {item.get('created_at')}",
                f"Created: {created_by} ({created_by_id})",
                f"Accepted: {accepted_by} ({accepted_by_id})",
                f"Status: {status}",
                "",
            ]
        )
    return "\n".join(lines).strip()


@router.message(F.text == "🗂 Arxiv")
async def archive_menu(message: Message) -> None:
    await message.answer("Arxiv bo‘limi:", reply_markup=archive_menu_kb())


@router.callback_query(F.data == "archive:back")
async def archive_back(callback: CallbackQuery) -> None:
    await callback.message.answer("Asosiy menyu:", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "archive:today")
async def archive_today(callback: CallbackQuery) -> None:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

    counts = await count_status_between(start, end)
    orders = await fetch_orders_between(start, end, limit=10)
    await callback.message.answer(_format_archive(orders, counts))
    await callback.answer()


@router.callback_query(F.data == "archive:month")
async def archive_month(callback: CallbackQuery) -> None:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    end = next_month.replace(hour=0, minute=0, second=0, microsecond=0)

    counts = await count_status_between(start.isoformat(), end.isoformat())
    orders = await fetch_orders_between(start.isoformat(), end.isoformat(), limit=10)
    await callback.message.answer(_format_archive(orders, counts))
    await callback.answer()


__all__ = ["router"]





