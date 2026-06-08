"""
handlers/psycho.py — Психолог-мотиватор с умным онбордингом.

Логика:
  - Первый запуск: короткий онбординг (4-5 вопросов) для сбора psycho_profile
  - Если профиль неполный: доспрашиваем только недостающее
  - Если профиль полный: сразу в сессию (только триггер + намерение)
  - Во время сессии: AI использует весь профиль + историю + победы из Cookie Jar
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters,
)
from services.db import (
    get_user, set_psycho_mode,
    start_psycho_session, get_active_psycho_session,
    append_psycho_dialog, end_psycho_session,
    get_future_profile, get_random_victory,
    update_psycho_mood_before,
    get_psycho_profile, upsert_psycho_profile,
)
from services.ai import generate_psycho_response, generate_psycho_onboarding_response

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Состояния ConversationHandler
# ──────────────────────────────────────────────
ONBOARDING   = 1   # онбординг-вопросы (только первый раз)
ASK_TRIGGER  = 2   # что сейчас происходит
ASK_INTENT   = 3   # что хочешь от сессии
IN_SESSION   = 4   # основной чат
END_MOOD     = 5   # оценка настроения после

# ──────────────────────────────────────────────
# Онбординг: 4 ключевых вопроса
# Основаны на: ACT-терапия, CBT-фреймворк, нейробиология стресса (кортизол, префронтальная кора)
# ──────────────────────────────────────────────
ONBOARDING_QUESTIONS = [
    {
        "key": "stress_pattern",
        "text": (
            "Когда тебе плохо или всё навалилось — как ты обычно реагируешь?\n\n"
            "Выбери что ближе всего:"
        ),
        "buttons": [
            ("🏃 Ухожу в себя, замолкаю", "pattern_freeze"),
            ("😤 Злюсь, срываюсь на других", "pattern_fight"),
            ("📱 Залипаю в телефоне / ем / сплю", "pattern_avoid"),
            ("🔄 Думаю по кругу, не могу остановиться", "pattern_ruminate"),
        ],
    },
    {
        "key": "energy_killer",
        "text": (
            "Что чаще всего забирает у тебя энергию?\n\n"
        ),
        "buttons": [
            ("😰 Страх что не справлюсь", "kill_fear"),
            ("😞 Ощущение что топчусь на месте", "kill_stuck"),
            ("🤝 Конфликты с людьми", "kill_people"),
            ("🌪 Хаос — слишком много всего сразу", "kill_chaos"),
        ],
    },
    {
        "key": "support_type",
        "text": (
            "Когда тебе тяжело, что помогает больше всего?\n\n"
        ),
        "buttons": [
            ("💬 Просто выговориться", "support_talk"),
            ("🎯 Получить конкретный план", "support_plan"),
            ("🔍 Понять почему так происходит", "support_insight"),
            ("💪 Жёсткое слово — встряхнуться", "support_push"),
        ],
    },
    {
        "key": "comeback_resource",
        "text": (
            "Был ли у тебя момент когда ты думал что не вытянешь — но вытянул?\n\n"
            "Напиши одним предложением. Это станет твоим ресурсом на трудные моменты.\n\n"
            "<i>Например: «Сдал сессию на больничном» или «Поднял бизнес после первого провала»</i>"
        ),
        "free_text": True,
    },
]


def _get_missing_onboarding_keys(profile: dict) -> list:
    """Возвращает список незаполненных полей онбординга."""
    required = ["stress_pattern", "energy_killer", "support_type", "comeback_resource"]
    return [k for k in required if not profile.get(k)]


def _onboarding_complete(profile: dict) -> bool:
    return len(_get_missing_onboarding_keys(profile)) == 0


def _make_onboarding_keyboard(question: dict) -> InlineKeyboardMarkup:
    buttons = question.get("buttons", [])
    rows = [[InlineKeyboardButton(label, callback_data=f"pob_{cb}")] for label, cb in buttons]
    return InlineKeyboardMarkup(rows)


# ──────────────────────────────────────────────
# Точка входа: /psycho
# ──────────────────────────────────────────────
async def psycho_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    user = get_user(tid)
    if not user:
        await update.message.reply_text("Сначала напиши /start.")
        return ConversationHandler.END

    # Есть активная сессия?
    active = get_active_psycho_session(tid)
    if active:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Продолжить", callback_data="psycho_resume"),
            InlineKeyboardButton("✖️ Завершить", callback_data="psycho_end_btn"),
        ]])
        await update.message.reply_text(
            "🧠 <b>Сессия уже идёт.</b>\n\nПродолжить или завершить?",
            parse_mode="HTML", reply_markup=kb
        )
        return ConversationHandler.END

    # Проверяем онбординг
    psycho_profile = get_psycho_profile(tid)
    missing = _get_missing_onboarding_keys(psycho_profile) if psycho_profile else list(
        q["key"] for q in ONBOARDING_QUESTIONS
    )

    if missing:
        # Нужен онбординг (полный или частичный)
        ctx.user_data["psycho_onboarding_queue"] = missing
        ctx.user_data["psycho_onboarding_data"] = {}
        await _send_next_onboarding(update.message, ctx, first=True)
        return ONBOARDING

    # Профиль готов — спрашиваем триггер
    await _ask_trigger(update.message)
    return ASK_TRIGGER


async def _send_next_onboarding(message, ctx: ContextTypes.DEFAULT_TYPE, first: bool = False):
    """
    message: объект telegram.Message (НЕ Update).
    Вызывать как: await _send_next_onboarding(update.message, ctx)
                  или: await _send_next_onboarding(query.message, ctx)
    """
    queue = ctx.user_data.get("psycho_onboarding_queue", [])
    if not queue:
        await _finish_onboarding(message, ctx)
        return

    key = queue[0]
    question = next((q for q in ONBOARDING_QUESTIONS if q["key"] == key), None)
    if not question:
        queue.pop(0)
        ctx.user_data["psycho_onboarding_queue"] = queue
        await _send_next_onboarding(message, ctx)
        return

    total = len(ONBOARDING_QUESTIONS)
    done = total - len(queue)
    progress = f"<i>Шаг {done + 1} из {total}</i>\n\n"

    if first:
        intro = (
            "🧠 <b>Пару вопросов перед стартом</b>\n\n"
            "Мне нужно понять как ты устроен, чтобы помогать тебе точнее — не по шаблону.\n"
            "Это займёт меньше минуты.\n\n"
        )
    else:
        intro = ""

    text = intro + progress + question["text"]

    if question.get("free_text"):
        await message.reply_text(text, parse_mode="HTML")
    else:
        await message.reply_text(
            text, parse_mode="HTML",
            reply_markup=_make_onboarding_keyboard(question)
        )


async def _finish_onboarding(message, ctx: ContextTypes.DEFAULT_TYPE):
    """
    message: объект telegram.Message.
    Сохраняем данные онбординга и переходим к триггеру.
    """
    tid = message.chat.id
    data = ctx.user_data.get("psycho_onboarding_data", {})
    upsert_psycho_profile(tid, data)

    await message.reply_text(
        "✅ <b>Готово. Теперь я знаю как тебе помогать.</b>\n\n"
        "Переходим к главному — расскажи что сейчас происходит.",
        parse_mode="HTML"
    )
    await _ask_trigger(message)


async def _ask_trigger(message):
    """message: объект telegram.Message."""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("😔 Просто плохо, не знаю почему", callback_data="trigger_bad")],
        [InlineKeyboardButton("🔥 Конкретная проблема / ситуация", callback_data="trigger_problem")],
        [InlineKeyboardButton("📉 Нет мотивации, всё бросить", callback_data="trigger_quit")],
        [InlineKeyboardButton("💬 Просто хочу поговорить", callback_data="trigger_talk")],
    ])
    await message.reply_text(
        "Что сейчас происходит?",
        reply_markup=kb
    )


# ──────────────────────────────────────────────
# Онбординг: обработка кнопок
# ──────────────────────────────────────────────
async def onboarding_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data  # формат: pob_<value>

    if not data.startswith("pob_"):
        return ONBOARDING

    value = data[4:]  # убираем "pob_"
    queue = ctx.user_data.get("psycho_onboarding_queue", [])
    if not queue:
        return ONBOARDING

    key = queue[0]
    ctx.user_data["psycho_onboarding_data"][key] = value
    ctx.user_data["psycho_onboarding_queue"] = queue[1:]

    await query.message.delete()
    # Следующий вопрос или завершение
    remaining = ctx.user_data["psycho_onboarding_queue"]
    if not remaining:
        await _finish_onboarding(query.message, ctx)
        return ASK_TRIGGER
    else:
        await _send_next_onboarding(query.message, ctx)
        return ONBOARDING


async def onboarding_free_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка текстового ответа на онбординг-вопрос (comeback_resource)."""
    queue = ctx.user_data.get("psycho_onboarding_queue", [])
    if not queue:
        return ONBOARDING

    key = queue[0]
    question = next((q for q in ONBOARDING_QUESTIONS if q["key"] == key), None)
    if not question or not question.get("free_text"):
        return ONBOARDING

    ctx.user_data["psycho_onboarding_data"][key] = update.message.text.strip()
    ctx.user_data["psycho_onboarding_queue"] = queue[1:]

    remaining = ctx.user_data["psycho_onboarding_queue"]
    if not remaining:
        await _finish_onboarding(update.message, ctx)
        return ASK_TRIGGER
    else:
        await _send_next_onboarding(update.message, ctx)
        return ONBOARDING


# ──────────────────────────────────────────────
# Триггер и намерение — быстрый ввод перед сессией
# ──────────────────────────────────────────────
async def trigger_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data  # trigger_bad / trigger_problem / trigger_quit / trigger_talk

    trigger_labels = {
        "trigger_bad": "просто плохо, без причины",
        "trigger_problem": "конкретная проблема",
        "trigger_quit": "нет мотивации, хочу всё бросить",
        "trigger_talk": "просто поговорить",
    }
    ctx.user_data["psycho_trigger"] = trigger_labels.get(data, data)
    await query.message.delete()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Выговориться", callback_data="intent_talk")],
        [InlineKeyboardButton("🎯 Получить план", callback_data="intent_plan")],
        [InlineKeyboardButton("💪 Встряхнуться", callback_data="intent_push")],
    ])
    await query.message.reply_text(
        "Чего ты хочешь от этой сессии?",
        reply_markup=kb
    )
    return ASK_INTENT


async def intent_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    intent_labels = {
        "intent_talk": "выговориться",
        "intent_plan": "получить конкретный план",
        "intent_push": "встряхнуться, получить жёсткое слово",
    }
    ctx.user_data["psycho_intent"] = intent_labels.get(data, data)
    await query.message.delete()

    tid = update.effective_user.id
    await _start_session(query.message, ctx, tid)
    return IN_SESSION


async def _start_session(message, ctx: ContextTypes.DEFAULT_TYPE, tid: int):
    """
    message: объект telegram.Message.
    Создаём сессию в БД, генерируем первое сообщение AI.
    """
    session = start_psycho_session(tid)
    session_id = session["id"]
    ctx.user_data["psycho_session_id"] = session_id
    set_psycho_mode(tid, True)
    ctx.user_data["in_conv_handler"] = True

    trigger = ctx.user_data.get("psycho_trigger", "")
    intent = ctx.user_data.get("psycho_intent", "")
    psycho_profile = get_psycho_profile(tid) or {}
    future_profile = get_future_profile(tid) or {}
    victory = get_random_victory(tid)

    first_msg = generate_psycho_onboarding_response(
        psycho_profile=psycho_profile,
        future_profile=future_profile,
        trigger=trigger,
        intent=intent,
        victory=victory,
    )

    await message.reply_text(first_msg, parse_mode="HTML")
    append_psycho_dialog(session_id, "assistant", first_msg)

    await message.reply_text(
        "<i>Чтобы завершить сессию — /psycho_end</i>",
        parse_mode="HTML"
    )


# ──────────────────────────────────────────────
# Основной диалог в сессии
# ──────────────────────────────────────────────
async def session_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает сообщения во время активной психо-сессии."""
    tid = update.effective_user.id
    user_msg = update.message.text.strip()
    if not user_msg:
        return IN_SESSION

    session = get_active_psycho_session(tid)
    if not session:
        set_psycho_mode(tid, False)
        await update.message.reply_text(
            "Сессия не найдена. Начни заново: /psycho"
        )
        return ConversationHandler.END

    session_id = session["id"]
    append_psycho_dialog(session_id, "user", user_msg)

    psycho_profile = get_psycho_profile(tid) or {}
    future_profile = get_future_profile(tid) or {}
    victory = get_random_victory(tid)
    history = session.get("dialog_history", [])

    await update.message.chat.send_action(action="typing")

    response = generate_psycho_response(
        psycho_profile=psycho_profile,
        future_profile=future_profile,
        history=history,
        user_message=user_msg,
        victory=victory,
        intent=ctx.user_data.get("psycho_intent", ""),
    )
    append_psycho_dialog(session_id, "assistant", response)
    await update.message.reply_text(response, parse_mode="HTML")
    return IN_SESSION


# ──────────────────────────────────────────────
# Завершение сессии
# ──────────────────────────────────────────────
async def psycho_end_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    session = get_active_psycho_session(tid)
    if not session:
        await update.message.reply_text("Нет активной сессии.")
        return ConversationHandler.END

    ctx.user_data["end_session_id"] = session["id"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 😞", callback_data="mood_after_1"),
         InlineKeyboardButton("2 😕", callback_data="mood_after_2"),
         InlineKeyboardButton("3 😐", callback_data="mood_after_3"),
         InlineKeyboardButton("4 🙂", callback_data="mood_after_4"),
         InlineKeyboardButton("5 😊", callback_data="mood_after_5")],
    ])
    await update.message.reply_text(
        "Оцени как ты сейчас — от 1 до 5:",
        reply_markup=kb
    )
    return END_MOOD

async def end_mood_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tid = update.effective_user.id

    mood_after = int(query.data.split("_")[-1])
    session_id = ctx.user_data.get("end_session_id")
    if session_id:
        end_psycho_session(session_id, mood_after)
    set_psycho_mode(tid, False)

    delta = ""
    session = get_active_psycho_session(tid)  # уже закрыта, но mood_before может быть в ctx
    # Просто закрываем красиво
    await query.edit_message_text(
        f"Принял. Сессия завершена.\n\n"
        f"Возвращайся когда нужно — /psycho"
    )
    ctx.user_data.pop("end_session_id", None)
    ctx.user_data.pop("psycho_session_id", None)
    ctx.user_data.pop("in_conv_handler", None) 
    
    return ConversationHandler.END


# ──────────────────────────────────────────────
# Кнопки: продолжить / завершить активную сессию
# ──────────────────────────────────────────────
async def psycho_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tid = update.effective_user.id

    if query.data == "psycho_resume":
        await query.message.delete()
        
        # Юзер продолжает сессию — включаем блокировку резервного хэндлера
        ctx.user_data["in_conv_handler"] = True
        
        # После delete нельзя reply — используем send_message в тот же чат
        await query.message.chat.send_message(
            "Продолжаем. Напиши что у тебя сейчас."
        )
    elif query.data == "psycho_end_btn":
        session = get_active_psycho_session(tid)
        if session:
            end_psycho_session(session["id"])
        set_psycho_mode(tid, False)
        
        # Сессия завершена — полностью удаляем флаг блокировки
        ctx.user_data.pop("in_conv_handler", None)
        
        await query.edit_message_text("Сессия завершена. /psycho — когда понадобится.")
# ──────────────────────────────────────────────
# Глобальный перехватчик: если in_psycho_mode, но вне ConversationHandler
# (используется в bot.py как fallback)
# ──────────────────────────────────────────────
async def psycho_handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Резервный обработчик — срабатывает если пользователь пишет
    вне ConversationHandler (например, после перезапуска бота), 
    но флаг in_psycho_mode = True.
    """
    # Если работает основной ConversationHandler, прерываем выполнение, 
    # чтобы не было дублирования сообщений!
    if ctx.user_data.get("in_conv_handler"):
        return

    from services.db import get_psycho_mode
    tid = update.effective_user.id
    if not get_psycho_mode(tid):
        return

    user_msg = update.message.text.strip()
    session = get_active_psycho_session(tid)
    if not session:
        set_psycho_mode(tid, False)
        await update.message.reply_text("Сессия потеряна. Начни заново: /psycho")
        return

    session_id = session["id"]
    append_psycho_dialog(session_id, "user", user_msg)

    psycho_profile = get_psycho_profile(tid) or {}
    future_profile = get_future_profile(tid) or {}
    victory = get_random_victory(tid)
    history = session.get("dialog_history", [])

    await update.message.chat.send_action(action="typing")
    response = generate_psycho_response(
        psycho_profile=psycho_profile,
        future_profile=future_profile,
        history=history,
        user_message=user_msg,
        victory=victory,
        intent="",
    )
    append_psycho_dialog(session_id, "assistant", response)
    await update.message.reply_text(response, parse_mode="HTML")

# ──────────────────────────────────────────────
# Сборка ConversationHandler
# ──────────────────────────────────────────────
def build_psycho_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("psycho", psycho_start)],
        states={
            ONBOARDING: [
                CallbackQueryHandler(onboarding_button, pattern="^pob_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_free_text),
            ],
            ASK_TRIGGER: [
                CallbackQueryHandler(trigger_selected, pattern="^trigger_"),
            ],
            ASK_INTENT: [
                CallbackQueryHandler(intent_selected, pattern="^intent_"),
            ],
            IN_SESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, session_message),
                CommandHandler("psycho_end", psycho_end_command),
            ],
            END_MOOD: [
                CallbackQueryHandler(end_mood_button, pattern="^mood_after_"),
            ],
        },
        fallbacks=[
            CommandHandler("psycho_end", psycho_end_command),
            CommandHandler("cancel", lambda u, c: (
                set_psycho_mode(u.effective_user.id, False),
                u.message.reply_text("Сессия прервана. /psycho — когда будешь готов.")
            )),
        ],
        name="psycho_conv",
        allow_reentry=True,
        per_user=True,
        per_chat=True,
    )