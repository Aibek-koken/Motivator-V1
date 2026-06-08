"""
handlers/onboarding.py — 4-шаговый онбординг Qaiyrat.
"""

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from services.db import upsert_user, get_future_profile, update_future_profile, add_victory

# Состояния диалога
GOAL, WHY, VICTORY, IMAGE = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    # Создаем или обновляем пользователя в БД
    upsert_user(user.id, user.first_name or "", user.username or "")
    
    # Проверяем, есть ли уже заполненная цель
    profile = get_future_profile(user.id)
    if profile and profile.get("dream"):
        await update.message.reply_text(
            f"С возвращением, {user.first_name} 👋\n\n"
            "Твой стержень Qaiyrat уже с тобой. Напиши, что у тебя на душе, "
            "или используй /psycho для сессии поддержки."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"Привет, {user.first_name}. Я — Qaiyrat (Қайрат).\n\n"
        "В переводе это значит «сила воли». Я здесь не для того, чтобы спамить цитатами, "
        "а чтобы быть твоим «якорем», когда станет тяжело. \n\n"
        "Давай определим твой фундамент. Это займет 2 минуты.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>Шаг 1 из 4: Твоя цель</b>\n\n"
        "Чего ты хочешь на самом деле? Не абстрактно «стать успешным», а конкретно.\n"
        "<i>Например: Запустить свой продукт, пробежать марафон, построить дом родителям.</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    return GOAL

async def onboarding_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["onboarding_goal"] = update.message.text.strip()
    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━━━\n"
        "💭 <b>Шаг 2 из 4: Твоё «Зачем»</b>\n\n"
        "Почему это важно? Что изменится, когда ты этого достигнешь? \n"
        "Будь честен, я — единственный, кому можно не врать.",
        parse_mode="HTML",
    )
    return WHY

async def onboarding_why(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["onboarding_why"] = update.message.text.strip()
    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━━━\n"
        "💪 <b>Шаг 3 из 4: Доказательство силы</b>\n\n"
        "Вспомни момент в прошлом, когда ты НЕ сдался, хотя было очень трудно. \n"
        "Что это было? Это твоя первая запись в «Архиве Побед».",
        parse_mode="HTML",
    )
    return VICTORY

async def onboarding_victory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["onboarding_victory"] = update.message.text.strip()
    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━━━\n"
        "🖼 <b>Шаг 4 из 4: Образ (необязательно)</b>\n\n"
        "Пришли фото, которое тебя заряжает, или просто напиши «пропустить».",
        parse_mode="HTML",
    )
    return IMAGE

async def onboarding_complete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    
    # Сохраняем данные в профиль будущего
    profile_data = {
        "dream": context.user_data.get("onboarding_goal"),
        "dream_why": context.user_data.get("onboarding_why"),
        "is_complete": True
    }
    update_future_profile(tid, profile_data)
    
    # Сохраняем первую победу в Cookie Jar (Victories)
    victory_text = context.user_data.get("onboarding_victory")
    if victory_text:
        add_victory(tid, victory_text, source="onboarding")

    await update.message.reply_text(
        "✅ <b>Фундамент заложен.</b>\n\n"
        "Теперь я знаю твою цель и твою силу. \n\n"
        "• Если станет плохо — просто напиши мне. \n"
        "• Если нужен разбор ситуации — /psycho. \n"
        "• Если хочешь увидеть свой путь — /future.\n\n"
        "Начинаем работу. Қайрат бол.",
        parse_mode="HTML"
    )
    return ConversationHandler.END

def build_onboarding_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_goal)],
            WHY: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_why)],
            VICTORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_victory)],
            IMAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, onboarding_complete)],
        },
        fallbacks=[CommandHandler("start", start)],
        name="onboarding_conv",
        allow_reentry=True
    )