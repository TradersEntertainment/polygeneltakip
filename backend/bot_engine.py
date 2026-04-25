import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "")

# Create a bot instance
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

async def send_notification(message: str):
    """Sends a formatted message to the target telegram group."""
    try:
        await bot.send_message(chat_id=TARGET_CHAT_ID, text=message, disable_web_page_preview=True)
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")
