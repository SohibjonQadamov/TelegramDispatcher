from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class OrderAction(StrEnum):
    ACCEPT = "ACCEPT"
    DELIVER = "DELIVER"
    CANCEL = "CANCEL"


class OrderCallback(CallbackData, prefix="order"):
    order_id: int
    action: OrderAction


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_order_message(order_id: int, raw_text: str) -> str:
    return f"Zakaz #{order_id}\n{raw_text}"


