from __future__ import annotations

import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from dotenv import load_dotenv
from handlers import register_handlers

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in the environment variables.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    await message.answer(
        "Welcome! Click the button below to open the web app.",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Open Web App", url="https://your-web-app-url.com")
        )
    )

def main():
    register_handlers(dp)
    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    main()