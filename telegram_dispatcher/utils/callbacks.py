from __future__ import annotations

from enum import Enum

from aiogram.filters.callback_data import CallbackData


class OrderAction(str, Enum):
    ACCEPT = "ACCEPT"
    DELIVER = "DELIVER"
    CANCEL = "CANCEL"


class OrderCallback(CallbackData, prefix="order"):
    order_id: int
    action: OrderAction


__all__ = ["OrderAction", "OrderCallback"]





