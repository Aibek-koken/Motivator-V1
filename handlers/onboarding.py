"""
Short /start onboarding for Qaiyrat MVP.
"""

from __future__ import annotations

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.menu import main_menu_keyboard
from services.db import complete_onboarding, get_active_goal, get_user, upsert_user

GOAL, DEADLINE, WHY, BLOCKER, TONE, FIRST_TASK = range(6)

TONE_BUTTONS = [["мягко", "жёстко"], ["по-братски", "спокойно"]]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    upsert_user(user.id, user.first_name or "", user.username or "")

    stored_user = get_user(user.id) or {}
    goal = get_active_goal(user.id)

    if stored_user.get("onboarding_completed") and goal:
        await update.message.reply_text(
            f"С возвращением, {user.first_name or 'друг'}.\n\n"
            "Qaiyrat держит фокус на одной вещи: вернуть тебя к действию, "
            "когда ты выпал.\n\n"
            "Выбери кнопку ниже.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "Я — Qaiyrat, AI accountability coach.\n\n"
        "Я не психолог и не терапевт. Моя задача проще: когда ты выпадаешь, "
        "вернуть тебя к одному маленькому действию за 3-5 минут.\n\n"
        "Начнём с минимума. Какая у тебя главная цель на ближайшее время?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return GOAL


async def onboarding_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Напиши цель текстом. Одной фразы достаточно.")
        return GOAL

    context.user_data["goal_title"] = text
    await update.message.reply_text(
        "Какой дедлайн?\n\n"
        "Можно написать как удобно: «через 2 недели», «до 1 августа», «к концу семестра»."
    )
    return DEADLINE


async def onboarding_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Напиши дедлайн текстом. Можно примерно.")
        return DEADLINE

    context.user_data["deadline"] = text
    await update.message.reply_text(
        "Почему эта цель реально важна?\n\n"
        "Не красиво. Честно. Что изменится, если ты не сольёшься?"
    )
    return WHY


async def onboarding_why(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Напиши why хотя бы одним предложением.")
        return WHY

    context.user_data["why"] = text
    await update.message.reply_text(
        "Что обычно заставляет тебя пропадать или бросать?\n\n"
        "Например: усталость, стыд, хаос, страх, непонимание, телефон, прокрастинация."
    )
    return BLOCKER


async def onboarding_blocker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Напиши, что обычно тебя выбивает.")
        return BLOCKER

    context.user_data["blocker_pattern"] = text
    await update.message.reply_text(
        "Каким тоном тебя возвращать к делу?",
        reply_markup=ReplyKeyboardMarkup(TONE_BUTTONS, resize_keyboard=True, one_time_keyboard=True),
    )
    return TONE


async def onboarding_tone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tone = update.message.text.strip().lower()
    if tone not in {"мягко", "жёстко", "по-братски", "спокойно"}:
        await update.message.reply_text(
            "Выбери один из вариантов: мягко, жёстко, по-братски или спокойно.",
            reply_markup=ReplyKeyboardMarkup(TONE_BUTTONS, resize_keyboard=True, one_time_keyboard=True),
        )
        return TONE

    context.user_data["support_tone"] = tone
    await update.message.reply_text(
        "Последний вопрос.\n\n"
        "Какой первый маленький шаг ты можешь сделать? Задача должна быть на 5-15 минут.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return FIRST_TASK


async def onboarding_complete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    first_task = update.message.text.strip()
    if not first_task:
        await update.message.reply_text(
            "Нужен один первый шаг. Маленький: открыть файл, написать план, отправить одно сообщение."
        )
        return FIRST_TASK

    complete_onboarding(
        telegram_id=telegram_id,
        goal_title=context.user_data.get("goal_title", ""),
        deadline=context.user_data.get("deadline", ""),
        why=context.user_data.get("why", ""),
        blocker_pattern=context.user_data.get("blocker_pattern", ""),
        support_tone=context.user_data.get("support_tone", "спокойно"),
        first_task=first_task,
    )

    context.user_data.clear()
    await update.message.reply_text(
        "Готово. Qaiyrat настроен.\n\n"
        "Если выпал на 2-3 дня или чувствуешь, что сейчас сольёшься, нажми «Я выпал». "
        "Я помогу выбрать один следующий шаг.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def cancel_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Остановил. Чтобы начать заново, нажми /start.")
    return ConversationHandler.END


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_goal)],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_deadline)],
            WHY: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_why)],
            BLOCKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_blocker)],
            TONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_tone)],
            FIRST_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_complete)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_onboarding),
            CommandHandler("start", start),
        ],
        name="qaiyrat_onboarding",
        allow_reentry=True,
    )
