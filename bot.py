"""
AnchorAI — Telegram Bot
Возвращает пользователя к его цели в момент потери мотивации.
"""

import logging
import os
from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)
from handlers.onboarding import (
    start,
    onboarding_goal,
    onboarding_why,
    onboarding_victory,
    onboarding_image,
    onboarding_complete,
    GOAL, WHY, VICTORY, IMAGE,
)
from handlers.sos import sos_handler, anchor_handler
from handlers.daily import send_daily_checkin
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

    app = Application.builder().token(token).build()

    # Онбординг — ConversationHandler (4 шага)
    onboarding_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GOAL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_goal)],
            WHY:     [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_why)],
            VICTORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_victory)],
            IMAGE:   [
                MessageHandler(filters.PHOTO, onboarding_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_image),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(onboarding_conv)
    app.add_handler(CommandHandler("anchor", anchor_handler))
    app.add_handler(CommandHandler("help", anchor_handler))

    # SOS — ловим ключевые слова в любом сообщении
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        sos_handler,
    ))

    # Планировщик ежедневных вопросов
    scheduler = AsyncIOScheduler(timezone="Asia/Almaty")
    scheduler.add_job(
        send_daily_checkin,
        trigger="cron",
        hour=20,
        minute=0,
        args=[app.bot],
    )
    scheduler.start()

    logger.info("AnchorAI запущен ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
