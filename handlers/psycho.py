# handlers/psycho.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from services.db import (
    get_user, set_psycho_mode, start_psycho_session, get_active_psycho_session,
    append_psycho_dialog, end_psycho_session, get_future_profile, get_random_victory,
    update_psycho_mood_before
)
from services.ai import generate_psycho_response

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler (только для сбора начальной оценки настроения)
ASK_MOOD = 1

async def psycho_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Команда /psycho — начать сессию с мотиватором."""
    tid = update.effective_user.id
    user = get_user(tid)
    if not user:
        await update.message.reply_text("Сначала напиши /start.")
        return -1
    
    # Проверяем, есть ли уже активная сессия
    active_session = get_active_psycho_session(tid)
    if active_session:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🧠 Продолжить сессию", callback_data="psycho_resume"),
            InlineKeyboardButton("❌ Завершить сессию", callback_data="psycho_end")
        ]])
        await update.message.reply_text(
            "🧠 <b>У тебя уже есть активная сессия с психологом.</b>\n\n"
            "Хочешь продолжить разговор или завершить?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return -1
    
    # Спрашиваем настроение перед началом
    ctx.user_data["psycho_session_id"] = None
    await update.message.reply_text(
        "🧠 <b>Психолог-мотиватор</b>\n\n"
        "Привет. Я здесь, чтобы помочь тебе вернуть силы и ясность.\n"
        "Но сначала оцени своё состояние от 1 до 5:\n"
        "1 — совсем плохо, 5 — отлично.\n\n"
        "<i>Напиши цифру.</i>",
        parse_mode="HTML"
    )
    return ASK_MOOD

async def psycho_mood_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Получили оценку настроения, создаём сессию и начинаем диалог."""
    tid = update.effective_user.id
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1 or int(text) > 5:
        await update.message.reply_text("Пожалуйста, напиши число от 1 до 5.")
        return ASK_MOOD
    
    mood = int(text)
    # Создаём сессию
    session = start_psycho_session(tid)
    session_id = session["id"]
    update_psycho_mood_before(session_id, mood)
    ctx.user_data["psycho_session_id"] = session_id
    
    # Включаем флаг режима
    set_psycho_mode(tid, True)
    
    # Получаем профиль future для контекста
    profile = get_future_profile(tid) or {}
    victory = get_random_victory(tid)
    
    # Первое сообщение от психолога (AI)
    welcome_msg = generate_psycho_response(profile, [], f"Моё настроение {mood}/5. Начнём.", victory)
    await update.message.reply_text(welcome_msg, parse_mode="HTML")
    
    # Сохраняем в историю
    append_psycho_dialog(session_id, "assistant", welcome_msg)
    return -1  # завершаем ConversationHandler, дальше сообщения обрабатываются глобальным фильтром

async def psycho_handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает любое текстовое сообщение, когда пользователь в режиме психолога.
    Вызывается из bot.py, если in_psycho_mode == True.
    """
    tid = update.effective_user.id
    user_msg = update.message.text.strip()
    if not user_msg:
        return
    
    # Получаем активную сессию
    session = get_active_psycho_session(tid)
    if not session:
        # Флаг включён, но сессии нет — выключаем флаг
        set_psycho_mode(tid, False)
        await update.message.reply_text("Сессия потеряна. Напиши /psycho, чтобы начать заново.")
        return
    
    session_id = session["id"]
    # Сохраняем сообщение пользователя
    append_psycho_dialog(session_id, "user", user_msg)
    
    # Генерируем ответ AI
    profile = get_future_profile(tid) or {}
    victory = get_random_victory(tid)
    history = session.get("dialog_history", [])
    
    # Отправляем "печатает"
    await update.message.chat.send_action(action="typing")
    
    response = generate_psycho_response(profile, history, user_msg, victory)
    # Сохраняем ответ
    append_psycho_dialog(session_id, "assistant", response)
    await update.message.reply_text(response, parse_mode="HTML")

async def psycho_end(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Завершить сессию (команда /psycho_end или кнопка)."""
    tid = update.effective_user.id
    session = get_active_psycho_session(tid)
    if not session:
        await update.message.reply_text("Нет активной сессии.")
        return
    
    # Спрашиваем настроение после
    ctx.user_data["end_session_id"] = session["id"]
    await update.message.reply_text(
        "🧠 <b>Завершение сессии</b>\n\n"
        "Оцени своё состояние сейчас от 1 до 5:",
        parse_mode="HTML"
    )
    # Ожидаем ответ в следующем сообщении (используем следующий хендлер)

async def psycho_end_mood(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Получаем оценку после завершения."""
    tid = update.effective_user.id
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1 or int(text) > 5:
        await update.message.reply_text("Напиши число от 1 до 5.")
        return
    
    mood_after = int(text)
    session_id = ctx.user_data.get("end_session_id")
    if session_id:
        end_psycho_session(session_id, mood_after)
    set_psycho_mode(tid, False)
    await update.message.reply_text(
        "✅ Сессия завершена. Спасибо, что были со мной откровенны.\n"
        "Если снова понадобится поддержка — я здесь. /psycho"
    )
    ctx.user_data.pop("end_session_id", None)

async def psycho_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок от психолога."""
    query = update.callback_query
    await query.answer()
    data = query.data
    tid = update.effective_user.id
    
    if data == "psycho_resume":
        # Продолжить существующую сессию — ничего не делаем, просто убираем сообщение
        await query.message.delete()
        await query.message.reply_text("Продолжаем разговор. Напиши, что у тебя на душе.")
    elif data == "psycho_end":
        # Завершить сессию
        session = get_active_psycho_session(tid)
        if session:
            end_psycho_session(session["id"])
        set_psycho_mode(tid, False)
        await query.edit_message_text("❌ Сессия завершена. Чтобы начать заново, напиши /psycho.")
    else:
        await query.edit_message_text("Неизвестная команда.")

# Сборка ConversationHandler для начала сессии (опрос настроения)
def build_psycho_handler():
    from telegram.ext import ConversationHandler
    return ConversationHandler(
        entry_points=[CommandHandler("psycho", psycho_start)],
        states={
            ASK_MOOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, psycho_mood_received)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: u.message.reply_text("Отменено."))],
        name="psycho_start_conv",
        allow_reentry=True
    )