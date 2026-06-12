"""
Qaiyrat Telegram bot entrypoint.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from handlers.comeback import build_comeback_handler
from handlers.menu import help_command, menu_command, show_goal, unknown_text_handler
from handlers.onboarding import build_onboarding_handler
from handlers.tasks import build_tasks_handler, task_callback
from handlers.wins import build_wins_handler

load_dotenv()

logging.basicConfig(
    format="%(asctime)s · %(name)s · %(levelname)s · %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Настроить Qaiyrat"),
            BotCommand("help", "Как работает Qaiyrat"),
            BotCommand("menu", "Главное меню"),
            BotCommand("tasks", "Мои задачи"),
        ]
    )


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN must be set in .env")

    request_config = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = (
        Application.builder()
        .token(token)
        .request(request_config)
        .post_init(post_init)
        .build()
    )

    app.add_handler(build_onboarding_handler())
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", menu_command))

    app.add_handler(build_comeback_handler())
    app.add_handler(build_tasks_handler())
    app.add_handler(build_wins_handler())

    app.add_handler(CallbackQueryHandler(task_callback, pattern="^task_(done|delete):"))
    app.add_handler(MessageHandler(filters.Regex("^Моя цель$"), show_goal))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text_handler))

    logger.info("Qaiyrat started: /start /help /menu /tasks")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
