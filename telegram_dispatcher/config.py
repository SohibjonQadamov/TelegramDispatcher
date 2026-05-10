from __future__ import annotations

import os


def get_bot_token() -> str:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Set it in your environment.")
    return token


__all__ = ["get_bot_token"]









