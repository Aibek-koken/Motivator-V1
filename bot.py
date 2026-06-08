"""
Qaiyrat Bot — точка входа.
"""
import logging
import os
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

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

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # ─── /memory ──────────────────────────────────────────
    app.add_handler(build_memory_handler())
    app.add_handler(CallbackQueryHandler(memory_callback, pattern="^mem_"))

    # ─── /tasks ───────────────────────────────────────────
    app.add_handler(build_tasks_handler())
    app.add_handler(CallbackQueryHandler(tasks_callback, pattern="^tsk_"))

    # ─── /future (визуализатор) ───────────────────────────
    # ConversationHandler перехватывает все vis_* колбэки внутри себя.
    # Внешний future_callback нужен только для vis_* вне диалога (редко).
    app.add_handler(build_future_handler())
    app.add_handler(CallbackQueryHandler(future_callback, pattern="^vis_"))

    # ─── /psycho ──────────────────────────────────────────
    # ConversationHandler управляет всем флоу: онбординг → триггер → намерение → сессия → завершение
    # Внутри него: pob_*, trigger_*, intent_*, mood_after_* колбэки.
    # Внешние psycho_* колбэки (resume/end_btn) — для кнопок вне диалога.
    app.add_handler(build_psycho_handler())
    app.add_handler(CallbackQueryHandler(psycho_callback, pattern="^psycho_"))

    # ─── Резервный перехватчик для психо-сессии ───────────
    # Срабатывает ТОЛЬКО если in_psycho_mode=True, но ConversationHandler не активен
    # (например после перезапуска бота). Приоритет: group=1 (ниже ConversationHandler).
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, psycho_handle_message),
        group=1,
    )

    logger.info("✅ Qaiyrat запущен — /memory /tasks /future /psycho")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()