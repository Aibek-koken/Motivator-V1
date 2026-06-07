"""
Qaiyrat Bot — точка входа.
Сейчас подключён только /memory.
Остальные модули добавим по очереди.
"""

import logging
import os
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    filters,
)
from handlers.memory import build_memory_handler, memory_callback

logging.basicConfig(
    format="%(asctime)s · %(name)s · %(levelname)s · %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application) -> None:
    """Устанавливаем команды в меню Telegram."""
    await app.bot.set_my_commands([
        BotCommand("memory",  "🗂 Память прошлого — фото, тексты, ссылки"),
        BotCommand("future",  "🌅 Проектирование будущего"),
        BotCommand("psycho",  "🧠 Мотиватор"),
        BotCommand("tasks",   "✅ Задачи"),
        BotCommand("help",    "❓ Помощь"),
    ])


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # /memory — ConversationHandler (фото, текст, ссылки)
    app.add_handler(build_memory_handler())

    # Callback-кнопки памяти (закрепить, удалить, фильтр)
    app.add_handler(CallbackQueryHandler(memory_callback, pattern="^mem_"))

    logger.info("Qaiyrat запущен ✅  /memory готов")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
