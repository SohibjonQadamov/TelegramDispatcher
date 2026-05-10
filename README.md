# Telegram Dispatcher Bot

Production-ready Telegram bot for delivery dispatch workflow, built with
Python 3.11+ and `aiogram` v3.

## Features
- Admin order creation from private chat
- Group order distribution with inline buttons
- Courier acceptance and finalization
- Archive channel logging
- Daily stats and order history
- SQLite storage with repository layer (easy to swap to Postgres)

## Setup
1. Create a virtual environment and install dependencies:
   - `python -m venv .venv`
   - `.venv\Scripts\activate`
   - `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in values.
3. Start the bot:
   - `python main.py`

## Environment variables
- `BOT_TOKEN` - Bot token from BotFather
- `ADMIN_IDS` - Comma-separated Telegram user IDs
- `GROUP_CHAT_ID` - Target group chat ID for orders (negative for groups)
- `ARCHIVE_CHANNEL_ID` - Channel ID for logs (negative for channels)

## Telegram setup
1. Add the bot to the target group and archive channel.
2. Grant the bot admin permissions in the group (so it can delete/edit messages).
3. Ask couriers to `/start` the bot in private chat before accepting orders.

## Commands (admin only)
- `/stats_today` - Show stats for today (UTC)
- `/stats_date YYYY-MM-DD` - Show stats for a specific date (UTC)
- `/order <id>` - Show order details and action history

## Notes
- Database is created automatically at `data/bot.sqlite3`.
- All timestamps are stored in UTC ISO format.









