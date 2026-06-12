"""
Qaiyrat Telegram bot entrypoint.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
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
logging.getLogger("httpx").setLevel(logging.WARNING)


def _is_schema_error(error: object) -> bool:
    text = str(error)
    return any(
        marker in text
        for marker in (
            "schema cache",
            "does not exist",
            "Could not find the",
            "PGRST204",
            "PGRST205",
        )
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled update error", exc_info=context.error)

    if not isinstance(update, Update) or not update.effective_message:
        return

    if _is_schema_error(context.error):
        await update.effective_message.reply_text(
            "Бот запущен, но база Supabase ещё не обновлена под Qaiyrat MVP.\n\n"
            "Нужно открыть Supabase SQL Editor и выполнить текущий `schema.sql`, "
            "после этого перезапустить bot.py. Сейчас в базе не хватает новых таблиц/колонок."
        )
        return

    await update.effective_message.reply_text(
        "Внутренняя ошибка. Я записал её в лог, нужно проверить терминал."
    )


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
    app.add_error_handler(error_handler)

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
