from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL")

if not BOT_TOKEN or not WEB_APP_URL:
    raise ValueError("Please set the BOT_TOKEN and WEB_APP_URL environment variables.")