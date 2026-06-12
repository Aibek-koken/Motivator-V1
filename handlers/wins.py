"""
Manual win capture for Qaiyrat MVP.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from handlers.menu import main_menu_keyboard
from services.db import add_win, get_mvp_context, mark_user_active

WAITING_WIN_TEXT = 1


async def wins_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    mark_user_active(telegram_id)
    data = get_mvp_context(telegram_id)

    if not data.get("goal"):
        await update.message.reply_text("Сначала настрой цель через /start.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Что записать как победу?\n\n"
        "Одним коротким текстом: что произошло или что ты сделал."
    )
    return WAITING_WIN_TEXT


async def receive_win(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Напиши победу текстом.")
        return WAITING_WIN_TEXT

    add_win(telegram_id, text, source="manual")
    await update.message.reply_text(
        "Записал. Эти маленькие возвраты потом помогают Qaiyrat говорить с тобой не по шаблону.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def cancel_wins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Остановил добавление победы.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_wins_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("win", wins_start),
            MessageHandler(filters.Regex("^Добавить победу$"), wins_start),
        ],
        states={
            WAITING_WIN_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_win),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_wins),
            MessageHandler(filters.Regex("^Главное меню$"), cancel_wins),
        ],
        name="qaiyrat_wins",
        allow_reentry=True,
        per_user=True,
        per_chat=True,
    )
