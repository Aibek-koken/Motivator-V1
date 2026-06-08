"""
Qaiyrat Bot — точка входа.
"""
import logging
import os
from dotenv import load_dotenv
from handlers.onboarding import build_onboarding_handler

load_dotenv()

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
# Правильный импорт для настройки таймаутов сетевых запросов
from telegram.request import HTTPXRequest

from handlers.memory import build_memory_handler, memory_callback
from handlers.tasks import build_tasks_handler, tasks_callback
from handlers.future import build_future_handler, future_callback
from handlers.psycho import (
    build_psycho_handler,
    psycho_callback,
    psycho_handle_message,
)

logging.basicConfig(
    format="%(asctime)s · %(name)s · %(levelname)s · %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("memory", "🗂 Память прошлого — фото, тексты, ссылки"),
        BotCommand("tasks",  "✅ Задачи"),
        BotCommand("future", "🌅 Визуализатор будущего"),
        BotCommand("psycho", "🧠 Психолог-мотиватор"),
        BotCommand("help",   "❓ Помощь"),
    ])


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

    # Создаем конфигурацию сети с увеличенным временем ожидания (до 30 секунд)
    request_config = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)

    app = (
        Application.builder()
        .token(token)
        .request(request_config)  # Применяем конфигурацию
        .post_init(post_init)
        .build()
    )

    # ─── /start (Onboarding) ─────────────────────────────
    app.add_handler(build_onboarding_handler())

    # ─── /memory ──────────────────────────────────────────
    app.add_handler(build_memory_handler())
    app.add_handler(CallbackQueryHandler(memory_callback, pattern="^mem_"))

    # ─── /tasks ───────────────────────────────────────────
    app.add_handler(build_tasks_handler())
    app.add_handler(CallbackQueryHandler(tasks_callback, pattern="^tsk_"))

    # ─── /future (визуализатор) ───────────────────────────
    app.add_handler(build_future_handler())
    app.add_handler(CallbackQueryHandler(future_callback, pattern="^vis_"))

    # ─── /psycho ──────────────────────────────────────────
    app.add_handler(build_psycho_handler())  # Опечатка исправлена здесь
    app.add_handler(CallbackQueryHandler(psycho_callback, pattern="^psycho_"))

    # ─── Резервный перехватчик для психо-сессии ───────────
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, psycho_handle_message),
        group=1,
    )

    logger.info("✅ Qaiyrat запущен — /memory /tasks /future /psycho")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()