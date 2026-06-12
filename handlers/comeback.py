"""
"Я выпал" comeback flow.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ChatAction
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.menu import main_menu_keyboard
from services.ai import SAFETY_MESSAGE, contains_crisis_language, generate_comeback_response
from services.db import (
    add_comeback_message,
    add_task,
    commit_comeback_session,
    create_comeback_session,
    get_active_tasks,
    get_comeback_session,
    get_mvp_context,
    get_recent_wins,
    mark_comeback_proposed,
    mark_user_active,
    update_comeback_session,
)

ASK_REASON, ASK_DAYS, ASK_BLOCKER, WAIT_COMMIT = range(4)

BLOCKER_KEYBOARD = ReplyKeyboardMarkup(
    [["лень", "страх", "усталость"], ["непонимание", "стыд", "хаос"], ["другое"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


COMMIT_KEYBOARD = ReplyKeyboardMarkup(
    [["Беру на 10 минут", "Не сейчас"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


def _done_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Готово", callback_data=f"task_done:{task_id}")]]
    )


async def comeback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    mark_user_active(telegram_id)
    data = get_mvp_context(telegram_id)

    if not data.get("goal"):
        await update.message.reply_text(
            "Сначала настрой цель через /start. Без цели Qaiyrat не будет угадывать."
        )
        return ConversationHandler.END

    context.user_data["comeback"] = {}
    await update.message.reply_text(
        "Окей. Коротко разберём и вернём тебя к одному действию.\n\n"
        "Что произошло? Почему выпал?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_REASON


async def comeback_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if contains_crisis_language(text):
        await _stop_for_safety(update, context)
        return ConversationHandler.END

    context.user_data.setdefault("comeback", {})["reason"] = text
    await update.message.reply_text("Сколько дней не двигался?")
    return ASK_DAYS


async def comeback_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if contains_crisis_language(text):
        await _stop_for_safety(update, context)
        return ConversationHandler.END

    context.user_data.setdefault("comeback", {})["days_slipped"] = text
    await update.message.reply_text(
        "Что сейчас сильнее всего мешает?",
        reply_markup=BLOCKER_KEYBOARD,
    )
    return ASK_BLOCKER


async def comeback_blocker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    blocker = update.message.text.strip()
    state = context.user_data.setdefault("comeback", {})
    state["blocker"] = blocker

    joined = " ".join(state.values())
    if contains_crisis_language(joined):
        await _stop_for_safety(update, context)
        return ConversationHandler.END

    thinking = await update.message.reply_text(
        "Собираю короткий comeback-план...",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.chat.send_action(action=ChatAction.TYPING)

    user_profile = get_mvp_context(telegram_id)
    recent_wins = get_recent_wins(telegram_id, limit=5)
    active_tasks = get_active_tasks(telegram_id, limit=5)
    tone = (user_profile.get("profile") or {}).get("support_tone", "спокойно")

    session = create_comeback_session(
        telegram_id=telegram_id,
        trigger_reason=state.get("reason", ""),
        days_slipped=state.get("days_slipped", ""),
        blocker=blocker,
    )
    session_id = session["id"]

    add_comeback_message(
        session_id,
        telegram_id,
        "user",
        (
            f"Что произошло: {state.get('reason', '')}\n"
            f"Дней без движения: {state.get('days_slipped', '')}\n"
            f"Блокер: {blocker}"
        ),
    )

    result = generate_comeback_response(
        user_profile=user_profile,
        recent_wins=recent_wins,
        active_tasks=active_tasks,
        trigger=state,
        tone=tone,
    )

    if result.get("source") == "safety":
        update_comeback_session(session_id, telegram_id, {"status": "safety"})
        await thinking.edit_text(SAFETY_MESSAGE)
        context.user_data.pop("comeback", None)
        await update.message.reply_text("Главное меню.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    message = result["message"]
    next_action = result["next_action"]
    mark_comeback_proposed(session_id, telegram_id, message, next_action)
    add_comeback_message(session_id, telegram_id, "assistant", message)

    state["session_id"] = session_id
    state["next_action"] = next_action

    await thinking.edit_text("План готов.")
    await update.message.reply_text(message, reply_markup=COMMIT_KEYBOARD)
    return WAIT_COMMIT


async def commit_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    state = context.user_data.get("comeback", {})
    session_id = state.get("session_id")
    if not session_id:
        await update.message.reply_text("Сессия потерялась. Нажми «Я выпал» ещё раз.")
        return ConversationHandler.END

    if text in {"да", "готов", "беру", "ок", "окей", "yes", "беру на 10 минут"}:
        telegram_id = update.effective_user.id
        action = state.get("next_action") or "сделать один маленький шаг"
        session = get_comeback_session(session_id, telegram_id) or {}
        task = add_task(
            telegram_id=telegram_id,
            text=action,
            source="comeback",
            goal_id=session.get("goal_id"),
            comeback_session_id=session_id,
        )
        commit_comeback_session(session_id, telegram_id, task["id"])
        add_comeback_message(session_id, telegram_id, "user", text)
        await update.message.reply_text("Принял. Создаю задачу.", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(
            "Задача создана.\n\n"
            f"{action}\n\n"
            "Сделай её и нажми «Готово».",
            reply_markup=_done_keyboard(task["id"]),
        )
        await update.message.reply_text("Главное меню.", reply_markup=main_menu_keyboard())
        context.user_data.pop("comeback", None)
        return ConversationHandler.END

    if text in {"не сейчас", "нет", "no"}:
        telegram_id = update.effective_user.id
        update_comeback_session(session_id, telegram_id, {"status": "cancelled"})
        add_comeback_message(session_id, telegram_id, "user", text)
        await update.message.reply_text(
            "Принял. Когда будешь готов вернуться к действию, нажми «Я выпал».",
            reply_markup=main_menu_keyboard(),
        )
        context.user_data.pop("comeback", None)
        return ConversationHandler.END

    await update.message.reply_text(
        "Ответь кнопкой: «Беру на 10 минут» или «Не сейчас».",
        reply_markup=COMMIT_KEYBOARD,
    )
    return WAIT_COMMIT


async def _stop_for_safety(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("comeback", None)
    await update.message.reply_text(SAFETY_MESSAGE, reply_markup=main_menu_keyboard())


async def cancel_comeback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("comeback", None)
    await update.message.reply_text("Остановил comeback-сессию.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_comeback_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Я выпал$"), comeback_start)],
        states={
            ASK_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, comeback_reason)],
            ASK_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, comeback_days)],
            ASK_BLOCKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, comeback_blocker)],
            WAIT_COMMIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, commit_text),
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^Главное меню$"), cancel_comeback)],
        name="qaiyrat_comeback",
        allow_reentry=True,
        per_user=True,
        per_chat=True,
    )
