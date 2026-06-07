# handlers/future.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from services.db import (
    get_user, set_future_mode, get_future_profile, init_future_profile,
    update_future_profile, append_future_dialog, complete_future_profile, get_future_mode
)
from services.ai import get_next_future_question, parse_future_answer, FUTURE_QUESTIONS

logger = logging.getLogger(__name__)

ASKING = 1

async def future_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    tid = user.id

    profile = get_future_profile(tid)
    if profile and profile.get("is_complete"):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Посмотреть мой профиль", callback_data="future_view")],
            [InlineKeyboardButton("🔄 Пройти заново", callback_data="future_restart")],
            [InlineKeyboardButton("❌ Отмена", callback_data="future_cancel")]
        ])
        await update.message.reply_text(
            "🧠 <b>Твой профиль будущего уже создан.</b>\n\n"
            "Ты можешь посмотреть что сохранил, или пройти опрос заново, чтобы обновить цели и ценности.",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return ConversationHandler.END

    if not profile:
        init_future_profile(tid)

    set_future_mode(tid, True)
    ctx.user_data["future_step"] = 1
    next_q = get_next_future_question(0)
    await update.message.reply_text(
        "🌅 <b>Проектирование будущего</b>\n\n"
        "Я задам несколько вопросов, чтобы мы вместе сформулировали твою мечту, ценности и якоря.\n"
        "Отвечай честно — это только для тебя.\n\n"
        f"{next_q['question']}",
        parse_mode="HTML"
    )
    return ASKING

async def handle_future_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    answer = update.message.text.strip()
    if not answer:
        await update.message.reply_text("Напиши что-нибудь, я слушаю.")
        return ASKING

    step = ctx.user_data.get("future_step", 1)

    # Найти текущий вопрос
    current_q = None
    for q in FUTURE_QUESTIONS:
        if q["step"] == step:
            current_q = q
            break
    if not current_q:
        await finish_future(update, ctx)
        return ConversationHandler.END

    append_future_dialog(tid, "user", answer)

    parsed = parse_future_answer(current_q["field"], answer)
    update_future_profile(tid, parsed)

    next_q = get_next_future_question(step)
    if next_q.get("is_complete"):
        complete_future_profile(tid)
        set_future_mode(tid, False)
        await finish_future(update, ctx)
        return ConversationHandler.END

    ctx.user_data["future_step"] = next_q["step"]
    await update.message.reply_text(f"✅ <b>Понял.</b>\n\n{next_q['question']}", parse_mode="HTML")
    return ASKING

async def finish_future(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    profile = get_future_profile(tid)
    if not profile:
        await update.message.reply_text("Ошибка: профиль не найден.")
        return

    dream = profile.get("dream", "—")
    why = profile.get("dream_why", "—")
    values = ", ".join(profile.get("values", []))
    fears = ", ".join(profile.get("fears", []))
    people = profile.get("people", [])
    people_text = "\n".join([f"• {p['name']} — {p['role']}" for p in people]) if people else "—"
    energy = ", ".join(profile.get("energy_sources", []))
    tracks = profile.get("favorite_tracks", [])
    track_text = "\n".join([f"🎵 {t.get('title')} — {t.get('artist')}" for t in tracks]) if tracks else "—"
    anchor = profile.get("anchor_phrase", "—")

    summary = (
        "🌅 <b>Твой профиль будущего готов</b>\n\n"
        f"<b>Мечта:</b>\n{dream}\n\n"
        f"<b>Почему это важно:</b>\n{why}\n\n"
        f"<b>Ценности:</b> {values}\n\n"
        f"<b>Страхи:</b> {fears}\n\n"
        f"<b>Люди:</b>\n{people_text}\n\n"
        f"<b>Источники энергии:</b> {energy}\n\n"
        f"<b>Любимые треки:</b>\n{track_text}\n\n"
        f"<b>Фраза-якорь:</b> «{anchor}»\n\n"
        "Ты всегда можешь обновить профиль командой /future и выбрать «Пройти заново»."
    )
    await update.message.reply_text(summary, parse_mode="HTML")
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Понял", callback_data="future_close")]])
    await update.message.reply_text("Сохранил всё. Теперь у тебя есть карта будущего. ✨", reply_markup=keyboard)

async def future_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    set_future_mode(tid, False)
    await update.message.reply_text("❌ Диалог о будущем прерван. Чтобы начать заново, напиши /future.")
    return ConversationHandler.END

async def future_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    tid = update.effective_user.id

    if data == "future_view":
        profile = get_future_profile(tid)
        if not profile:
            await query.edit_message_text("Профиль не найден. Начни с /future.")
            return
        dream = profile.get("dream", "—")
        why = profile.get("dream_why", "—")
        values = ", ".join(profile.get("values", []))
        fears = ", ".join(profile.get("fears", []))
        people = profile.get("people", [])
        people_text = "\n".join([f"• {p['name']} — {p['role']}" for p in people]) if people else "—"
        energy = ", ".join(profile.get("energy_sources", []))
        tracks = profile.get("favorite_tracks", [])
        track_text = "\n".join([f"🎵 {t.get('title')} — {t.get('artist')}" for t in tracks]) if tracks else "—"
        anchor = profile.get("anchor_phrase", "—")
        summary = (
            "🌅 <b>Твой профиль будущего</b>\n\n"
            f"<b>Мечта:</b>\n{dream}\n\n"
            f"<b>Почему важно:</b>\n{why}\n\n"
            f"<b>Ценности:</b> {values}\n\n"
            f"<b>Страхи:</b> {fears}\n\n"
            f"<b>Люди:</b>\n{people_text}\n\n"
            f"<b>Энергия:</b> {energy}\n\n"
            f"<b>Треки:</b>\n{track_text}\n\n"
            f"<b>Якорь:</b> «{anchor}»"
        )
        await query.edit_message_text(summary, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="future_back")]]))
    elif data == "future_restart":
        # Сброс профиля: очищаем все поля, но оставляем запись
        empty_profile = {
            "dream": None, "dream_why": None, "values": [], "fears": [],
            "people": [], "energy_sources": [], "favorite_tracks": [],
            "anchor_phrase": None, "dialog_history": [], "is_complete": False
        }
        update_future_profile(tid, empty_profile)
        set_future_mode(tid, True)
        ctx.user_data["future_step"] = 1
        first_q = get_next_future_question(0)
        await query.edit_message_text(
            "🔄 <b>Начинаем заново</b>\n\n" + first_q["question"],
            parse_mode="HTML"
        )
        # Переключаем состояние разговора (но conversation handler не активен, нужно перезапустить)
        # Проще: удалить сообщение и запустить команду заново
        await query.message.delete()
        # Имитируем команду /future
        fake_update = update
        fake_update.message = query.message
        await future_start(fake_update, ctx)
    elif data == "future_cancel":
        await query.edit_message_text("❌ Отменено. Используй /future когда захочешь.")
    elif data == "future_close":
        await query.delete_message()
    elif data == "future_back":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Посмотреть профиль", callback_data="future_view")],
            [InlineKeyboardButton("🔄 Пройти заново", callback_data="future_restart")],
            [InlineKeyboardButton("❌ Закрыть", callback_data="future_cancel")]
        ])
        await query.edit_message_text(
            "🧠 <b>Профиль будущего</b>\n\nЧто хочешь сделать?",
            parse_mode="HTML",
            reply_markup=keyboard
        )

def build_future_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("future", future_start)],
        states={
            ASKING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_future_answer),
                CommandHandler("cancel", future_cancel),
            ]
        },
        fallbacks=[CommandHandler("cancel", future_cancel)],
        allow_reentry=True,
        name="future_conv"
    )