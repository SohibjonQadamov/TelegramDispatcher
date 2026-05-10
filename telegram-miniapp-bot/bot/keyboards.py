from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def main_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup()
    button = InlineKeyboardButton(text="Open Mini App", url="https://your-mini-app-url.com")
    keyboard.add(button)
    return keyboard