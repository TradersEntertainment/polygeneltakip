import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "")

# Create a bot instance
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

async def send_notification(message: str, chat_id: str = None):
    """Sends a formatted message to the target telegram group."""
    target = chat_id if chat_id else TARGET_CHAT_ID
    try:
        await bot.send_message(chat_id=target, text=message, disable_web_page_preview=True)
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")
