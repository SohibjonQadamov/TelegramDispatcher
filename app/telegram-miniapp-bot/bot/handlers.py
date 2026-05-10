from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

router = Router()

@router.message(F.text == "/start")
async def start_command(msg: Message):
    button = InlineKeyboardButton(text="Open Web App", url="https://your-web-app-url.com")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[button]])
    await msg.answer("Welcome! Click the button below to open the web app:", reply_markup=keyboard)