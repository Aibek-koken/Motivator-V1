"""
Qaiyrat Bot — точка входа.
"""
from handlers.future import build_future_handler, future_callback
import logging
import os
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, BotCommand
from telegram.ext import Application, CallbackQueryHandler
from handlers.memory import build_memory_handler, memory_callback
from handlers.tasks import build_tasks_handler, tasks_callback

logging.basicConfig(
    format="%(asctime)s · %(name)s · %(levelname)s · %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("memory", "🗂 Память прошлого — фото, тексты, ссылки"),
        BotCommand("tasks",  "✅ Задачи"),
        BotCommand("future", "🌅 Проектирование будущего"),
        BotCommand("psycho", "🧠 Мотиватор"),
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

    # /memory
    app.add_handler(build_memory_handler())
    app.add_handler(CallbackQueryHandler(memory_callback, pattern="^mem_"))

    # /tasks
    app.add_handler(build_tasks_handler())
    app.add_handler(CallbackQueryHandler(tasks_callback, pattern="^tsk_"))

        # /future
    app.add_handler(build_future_handler())
    app.add_handler(CallbackQueryHandler(future_callback, pattern="^future_"))

    logger.info("Qaiyrat запущен ✅  /memory + /tasks готовы")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()