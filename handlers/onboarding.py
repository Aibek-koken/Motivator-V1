"""
handlers/onboarding.py — 4-шаговый онбординг.

Шаг 1 (GOAL):    Чего ты хочешь?
Шаг 2 (WHY):     Почему это важно?
Шаг 3 (VICTORY): Вспомни момент когда ты не сдался.
Шаг 4 (IMAGE):   Фото или описание образа.
"""

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from services.db import save_profile, get_profile

# Состояния диалога
GOAL, WHY, VICTORY, IMAGE = range(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    telegram_id = user.id

    # Если уже онбордился — не гоним заново
    profile = get_profile(telegram_id)
    if profile and profile.get("goal"):
        await update.message.reply_text(
            f"С возвращением, {user.first_name} 👋\n\n"
            "Напиши мне как ты сейчас — я здесь.\n"
            "Или набери /anchor чтобы я напомнил тебе твою цель."
        )
        return ConversationHandler.END

    # Сохраняем имя
    save_profile(telegram_id, {"name": user.first_name or ""})

    await update.message.reply_text(
        f"Привет, {user.first_name} 👋\n\n"
        "Я AnchorAI — твой личный якорь.\n"
        "Когда тебе будет плохо или захочется всё бросить — я верну тебя к тому, ради чего ты начал.\n\n"
        "Но для этого мне нужно узнать тебя. Это займёт 2 минуты.\n\n"
        "Начнём?\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>Шаг 1 из 4</b>\n\n"
        "<b>Чего ты хочешь?</b>\n\n"
        "Не «стать успешным». Конкретно — что именно ты хочешь?\n"
        "Например: купить маме дом, открыть свой бизнес, поступить в топ-университет.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    return GOAL


async def onboarding_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    goal = update.message.text.strip()

    if len(goal) < 5:
        await update.message.reply_text(
            "Напиши чуть подробнее — мне важно понять что именно для тебя важно 🙏"
        )
        return GOAL

    # Временно сохраняем в context до завершения онбординга
    context.user_data["goal"] = goal

    await update.message.reply_text(
        "Понял. Записал.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💭 <b>Шаг 2 из 4</b>\n\n"
        "<b>Почему это важно для тебя?</b>\n\n"
        "Не «потому что хочу денег». Настоящая причина — что стоит за этим?\n"
        "Ради кого? Ради чего?",
        parse_mode="HTML",
    )
    return WHY


async def onboarding_why(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    why = update.message.text.strip()

    if len(why) < 10:
        await update.message.reply_text(
            "Попробуй глубже — почему это важно именно для тебя? Что будет если не достигнешь?"
        )
        return WHY

    context.user_data["why"] = why

    await update.message.reply_text(
        "Это важно. Я запомню это.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💪 <b>Шаг 3 из 4</b>\n\n"
        "<b>Вспомни момент когда ты почти сдался — но не сдался.</b>\n\n"
        "Что произошло? Что тебе помогло продолжить?\n"
        "Это может быть что угодно — большое или маленькое.",
        parse_mode="HTML",
    )
    return VICTORY


async def onboarding_victory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    victory = update.message.text.strip()

    if len(victory) < 10:
        await update.message.reply_text(
            "Расскажи чуть больше — что именно случилось и как ты прошёл через это?"
        )
        return VICTORY

    context.user_data["victory"] = victory

    await update.message.reply_text(
        "Это твоя первая победа в архиве. Я буду возвращать тебя к ней когда нужно.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🖼 <b>Шаг 4 из 4 (необязательно)</b>\n\n"
        "<b>Есть образ или фото которое тебя заряжает?</b>\n\n"
        "Это может быть фото мечты, места, человека — всё что у тебя ассоциируется с целью.\n\n"
        "Отправь фото или опиши образ текстом.\n"
        "Или напиши <b>пропустить</b> если нет.",
        parse_mode="HTML",
    )
    return IMAGE


async def onboarding_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id

    # Фото или текст
    if update.message.photo:
        # Берём file_id самого большого фото
        image_ref = update.message.photo[-1].file_id
        context.user_data["image"] = image_ref
        context.user_data["image_type"] = "photo"
    else:
        text = update.message.text.strip().lower()
        if text in ("пропустить", "skip", "-", "нет"):
            context.user_data["image"] = None
        else:
            context.user_data["image"] = update.message.text.strip()
            context.user_data["image_type"] = "text"

    # Сохраняем весь профиль
    save_profile(telegram_id, {
        "goal":       context.user_data.get("goal"),
        "why":        context.user_data.get("why"),
        "victory":    context.user_data.get("victory"),
        "image":      context.user_data.get("image"),
        "image_type": context.user_data.get("image_type", "none"),
    })

    return await onboarding_complete(update, context)


async def onboarding_complete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user

    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Готово, {user.first_name}.</b>\n\n"
        "Я запомнил твою цель, твоё «почему» и твою победу.\n\n"
        "Теперь когда тебе будет тяжело — просто напиши мне как ты себя чувствуешь. "
        "Напиши «плохо», «не могу», «хочу бросить» — я буду здесь.\n\n"
        "Или набери /anchor — и я напомню тебе зачем ты это делаешь.\n\n"
        "<i>Каждый вечер я буду задавать тебе один вопрос — чтобы мы пополняли твой архив побед.</i>",
        parse_mode="HTML",
    )
    return ConversationHandler.END
