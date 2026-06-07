"""
handlers/sos.py — главный обработчик.

1. Ловит кризисные слова → SOS-ответ по формуле
2. Ловит ответы на ежедневный вопрос → сохраняет в архив побед
3. /anchor — возвращает якорь из архива
"""

import re
from telegram import Update
from telegram.ext import ContextTypes
from services.db import get_profile, get_random_victory, add_victory
from services.ai import generate_sos_response, generate_anchor_response

# ──────────────────────────────────────────────
# Ключевые слова для SOS
# ──────────────────────────────────────────────

SOS_PATTERNS = [
    r"\bплохо\b",
    r"\bне могу\b",
    r"\bхочу бросить\b",
    r"\bбросить всё\b",
    r"\bбросаю\b",
    r"\bнет сил\b",
    r"\bвсё бесит\b",
    r"\bвыгорание\b",
    r"\bвыгорел\b",
    r"\bустал\b",
    r"\bне вижу смысла\b",
    r"\bзачем всё это\b",
    r"\bопускаются руки\b",
    r"\bне получается\b",
    r"\bпровал\b",
    r"\bхочу всё бросить\b",
    r"\bхватит\b",
    r"\bнадоело\b",
    r"\bне хочу\b",
    r"\bне могу больше\b",
    r"\bне вывожу\b",
    # Казахские/транслит слова
    r"\bjok\b",
    r"\bболмайды\b",
    r"\bжоқ\b",
    r"\bшаршадым\b",
]

SOS_REGEX = re.compile("|".join(SOS_PATTERNS), re.IGNORECASE)

# Флаг что бот ждёт ответ на ежедневный вопрос
AWAITING_DAILY = "awaiting_daily_answer"


async def sos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все входящие сообщения. SOS или ответ на ежедневный вопрос."""
    telegram_id = update.effective_user.id
    text = update.message.text or ""

    # Проверяем — ждём ли ответ на ежедневный вопрос
    if context.user_data.get(AWAITING_DAILY):
        context.user_data[AWAITING_DAILY] = False
        if len(text.strip()) > 5:
            add_victory(telegram_id, text.strip())
            await update.message.reply_text(
                "Записал в твой архив побед 🗂\n\n"
                "Когда тебе будет тяжело — я достану это и напомню что ты уже умеешь не сдаваться."
            )
        else:
            await update.message.reply_text(
                "Окей, всё нормально. Завтра спрошу снова 👍"
            )
        return

    # Проверяем SOS-триггеры
    if SOS_REGEX.search(text):
        profile = get_profile(telegram_id)

        if not profile or not profile.get("goal"):
            # Пользователь не прошёл онбординг
            await update.message.reply_text(
                "Слышу тебя. Мне важно помочь.\n\n"
                "Но сначала давай познакомимся — набери /start и я пройду с тобой онбординг. "
                "Это 2 минуты, и тогда я смогу помочь тебе по-настоящему.",
            )
            return

        # Показываем что бот думает
        thinking_msg = await update.message.reply_text("...")

        try:
            victory = get_random_victory(telegram_id)
            response = generate_sos_response(profile, victory)
            await thinking_msg.edit_text(response)
        except Exception as e:
            await thinking_msg.edit_text(
                "Слышу тебя. Такие моменты бывают у всех кто идёт к чему-то большому.\n\n"
                "Сделай одно: умой лицо холодной водой. Потом напиши мне одно слово — что сделаешь дальше."
            )
        return

    # Обычное сообщение — мягко направляем
    profile = get_profile(telegram_id)
    if not profile or not profile.get("goal"):
        await update.message.reply_text(
            "Привет! Набери /start чтобы начать — я расскажу как работаю."
        )
        return

    # Если написали что-то нейтральное — подтверждаем что слышим
    await update.message.reply_text(
        "Слышу тебя 👂\n\n"
        "Если тебе тяжело — напиши как ты себя чувствуешь. "
        "Или набери /anchor — и я напомню тебе зачем ты это делаешь."
    )


async def anchor_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/anchor — достать якорь из архива."""
    telegram_id = update.effective_user.id
    profile = get_profile(telegram_id)

    if not profile or not profile.get("goal"):
        await update.message.reply_text(
            "Сначала давай познакомимся — набери /start."
        )
        return

    thinking_msg = await update.message.reply_text("Достаю твой якорь...")

    try:
        victory = get_random_victory(telegram_id)
        response = generate_anchor_response(profile, victory)
        await thinking_msg.edit_text(f"⚓ {response}")
    except Exception:
        goal = profile.get("goal", "твоя цель")
        why = profile.get("why", "")
        await thinking_msg.edit_text(
            f"⚓ Твоя цель: {goal}\n\n"
            f"{why}\n\n"
            "Это не изменилось. Продолжай."
        )
