from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: List[int]
    group_chat_id: int
    archive_channel_id: int
    database_path: str = "data/bot.sqlite3"


def _parse_admin_ids(raw: str) -> List[int]:
    if not raw.strip():
        return []
    values = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        values.append(int(item))
    return values


def _parse_int(raw: str, name: str) -> int:
    value = raw.strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def load_settings() -> Settings:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("BOT_TOKEN is required")

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    group_chat_id = _parse_int(os.getenv("GROUP_CHAT_ID", "0"), "GROUP_CHAT_ID")
    archive_channel_id = _parse_int(
        os.getenv("ARCHIVE_CHANNEL_ID", "0"), "ARCHIVE_CHANNEL_ID"
    )

    if not admin_ids:
        raise ValueError("ADMIN_IDS is required")
    if group_chat_id == 0:
        raise ValueError("GROUP_CHAT_ID is required")
    if archive_channel_id == 0:
        raise ValueError("ARCHIVE_CHANNEL_ID is required")

    return Settings(
        bot_token=bot_token,
        admin_ids=admin_ids,
        group_chat_id=group_chat_id,
        archive_channel_id=archive_channel_id,
    )


