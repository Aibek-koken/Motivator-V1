"""
handlers/memory.py — команда /memory

Потоки:
  /memory                → главное меню
  /memory + фото         → сохранить фото
  /memory + текст        → сохранить заметку
  /memory + ссылка       → сохранить ссылку
  /memory list           → посмотреть сохранённое
  callback "mem_delete"  → удалить
  callback "mem_pin"     → закрепить
  callback "mem_type"    → фильтр по типу
"""

import re
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from services.db import (
    upsert_user,
    add_memory,
    get_memories,
    pin_memory,
    delete_memory,
    add_victory,
)

# ── Состояния ConversationHandler ──────────────────────────
WAITING_CAPTION = 1
WAITING_CONTENT = 2   # для текстовой заметки

URL_RE = re.compile(r"https?://\S+")


# ══════════════════════════════════════════════════════════
# УТИЛИТЫ
# ══════════════════════════════════════════════════════════

def _type_emoji(t: str) -> str:
    return {"photo": "🖼", "text": "📝", "link": "🔗", "note": "💬", "voice": "🎙"}.get(t, "📎")


def _type_label(t: str) -> str:
    return {"photo": "Фото", "text": "Текст", "link": "Ссылка", "note": "Заметка", "voice": "Голос"}.get(t, t)


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖼 Фото",    callback_data="mem_list:photo"),
            InlineKeyboardButton("📝 Текст",   callback_data="mem_list:text"),
        ],
        [
            InlineKeyboardButton("🔗 Ссылки",  callback_data="mem_list:link"),
            InlineKeyboardButton("💬 Заметки", callback_data="mem_list:note"),
        ],
        [
            InlineKeyboardButton("📚 Всё",     callback_data="mem_list:all"),
        ],
    ])


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("← Назад", callback_data="mem_main"),
    ]])


def _item_keyboard(mem_id: int, is_pinned: bool) -> InlineKeyboardMarkup:
    pin_label = "📌 Закреплено" if is_pinned else "📌 Закрепить"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(pin_label,   callback_data=f"mem_pin:{mem_id}:{int(is_pinned)}"),
        InlineKeyboardButton("🗑 Удалить", callback_data=f"mem_delete:{mem_id}"),
    ]])


def _format_memory(m: dict) -> str:
    emoji = _type_emoji(m["type"])
    label = _type_label(m["type"])
    caption = m.get("caption") or ""
    date = str(m.get("created_at", ""))[:10]
    pin = " · 📌" if m.get("is_pinned") else ""

    header = f"{emoji} <b>{label}</b>{pin} <i>· {date}</i>"

    if m["type"] == "photo":
        body = f"<i>{caption}</i>" if caption else "<i>без подписи</i>"
    elif m["type"] == "link":
        body = f'<a href="{m["content"]}">{m["content"][:50]}…</a>'
        if caption:
            body += f"\n<i>{caption}</i>"
    else:
        body = m["content"]
        if caption and caption != m["content"]:
            body += f"\n<i>— {caption}</i>"

    return f"{header}\n{body}"


# ══════════════════════════════════════════════════════════
# ГЛАВНОЕ МЕНЮ /memory
# ══════════════════════════════════════════════════════════

async def memory_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    upsert_user(user.id, user.first_name or "", user.username or "")

    # Если сразу прислали фото — сохраняем
    if update.message.photo:
        return await _handle_photo(update, ctx)

    # Если прислали текст с командой — разбираем
    text = (update.message.text or "").strip()
    cmd_arg = text.replace("/memory", "").strip()

    if cmd_arg.lower() in ("list", "все", "all", "посмотреть"):
        return await _show_list(update, ctx, type_filter="all")

    if URL_RE.match(cmd_arg):
        ctx.user_data["mem_content"] = cmd_arg
        ctx.user_data["mem_type"] = "link"
        await update.message.reply_text(
            "🔗 <b>Ссылка получена.</b>\n\n"
            "Добавь короткую подпись — о чём эта ссылка?\n"
            "<i>Или напиши «—» чтобы сохранить без подписи.</i>",
            parse_mode="HTML",
        )
        return WAITING_CAPTION

    if cmd_arg:
        # Текст прямо в команде — сохраняем как заметку
        await _save_and_confirm(update, ctx, type_="note", content=cmd_arg)
        return ConversationHandler.END

    # Пустая команда — показываем меню
    counts = _get_counts(user.id)
    await update.message.reply_text(
        f"🗂 <b>Память прошлого</b>\n\n"
        f"Здесь хранится всё что ты сохранил:\n"
        f"🖼 фото · 📝 тексты · 🔗 ссылки · 💬 заметки\n\n"
        f"<b>Всего записей:</b> {counts}\n\n"
        f"Выбери категорию — или просто отправь мне:\n"
        f"· <b>Фото</b> — сохраню с подписью\n"
        f"· <b>Ссылку</b> — сохраню с описанием\n"
        f"· <b>Текст</b> — сохраню как заметку",
        parse_mode="HTML",
        reply_markup=_main_keyboard(),
    )
    return ConversationHandler.END


def _get_counts(telegram_id: int) -> int:
    try:
        return len(get_memories(telegram_id, limit=100))
    except Exception:
        return 0


# ══════════════════════════════════════════════════════════
# СОХРАНЕНИЕ ФОТО
# ══════════════════════════════════════════════════════════

async def _handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    file_id = update.message.photo[-1].file_id
    ctx.user_data["mem_content"] = file_id
    ctx.user_data["mem_type"] = "photo"

    # Если фото пришло с подписью — сразу сохраняем
    caption = update.message.caption or ""
    if caption:
        await _save_and_confirm(update, ctx, type_="photo", content=file_id, caption=caption)
        return ConversationHandler.END

    await update.message.reply_text(
        "🖼 <b>Фото получено.</b>\n\n"
        "Добавь подпись — что это за момент?\n"
        "<i>Или напиши «—» чтобы сохранить без подписи.</i>",
        parse_mode="HTML",
    )
    return WAITING_CAPTION


async def handle_photo_in_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Фото пришло внутри ConversationHandler."""
    return await _handle_photo(update, ctx)


# ══════════════════════════════════════════════════════════
# ОЖИДАНИЕ ПОДПИСИ (для фото и ссылок)
# ══════════════════════════════════════════════════════════

async def receive_caption(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    caption = "" if text in ("—", "-", "нет", "no", "skip") else text

    content = ctx.user_data.get("mem_content", "")
    type_ = ctx.user_data.get("mem_type", "text")

    await _save_and_confirm(update, ctx, type_=type_, content=content, caption=caption)
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════
# СОХРАНЕНИЕ ТЕКСТОВОЙ ЗАМЕТКИ (не через /memory)
# ══════════════════════════════════════════════════════════

async def save_text_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Вызывается из основного роутера когда пользователь в режиме /memory."""
    text = (update.message.text or "").strip()
    if not text:
        return
    await _save_and_confirm(update, ctx, type_="note", content=text)


# ══════════════════════════════════════════════════════════
# ОБЩАЯ ФУНКЦИЯ СОХРАНЕНИЯ
# ══════════════════════════════════════════════════════════

async def _save_and_confirm(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    type_: str,
    content: str,
    caption: str = "",
) -> None:
    tid = update.effective_user.id
    mem = add_memory(tid, type_, content, caption)
    mem_id = mem.get("id", 0)

    emoji = _type_emoji(type_)
    label = _type_label(type_)

    # Если это победа/достижение — дополнительно сохраняем в архив
    victory_keywords = ["сдал", "победил", "выиграл", "достиг", "прошёл", "завершил",
                        "получил", "защитил", "запустил", "сделал", "не сдался"]
    combined = f"{content} {caption}".lower()
    is_victory = any(kw in combined for kw in victory_keywords)

    if is_victory:
        add_victory(tid, caption or content, source="manual")

    victory_note = (
        "\n\n✨ <i>Похоже на победу — добавил в твой архив достижений.</i>"
        if is_victory else ""
    )

    # Формируем превью
    if type_ == "photo":
        preview = f"<i>{caption}</i>" if caption else "<i>без подписи</i>"
    elif type_ == "link":
        short = content[:40] + "…" if len(content) > 40 else content
        preview = f'<a href="{content}">{short}</a>'
        if caption:
            preview += f"\n<i>{caption}</i>"
    else:
        preview = content[:120] + ("…" if len(content) > 120 else "")
        if caption and caption != content:
            preview += f"\n<i>— {caption}</i>"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📌 Закрепить", callback_data=f"mem_pin:{mem_id}:0"),
        InlineKeyboardButton("🗑 Отменить",  callback_data=f"mem_delete:{mem_id}"),
    ]])

    msg = (
        f"{emoji} <b>Сохранено в память</b>{victory_note}\n\n"
        f"{preview}"
    )

    if type_ == "photo" and content:
        await update.message.reply_photo(
            photo=content,
            caption=msg,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=keyboard,
                                        disable_web_page_preview=False)


# ══════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА
# ══════════════════════════════════════════════════════════

async def _show_list(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    type_filter: str = "all",
) -> int:
    tid = update.effective_user.id
    type_ = None if type_filter == "all" else type_filter
    items = get_memories(tid, type_=type_, limit=8)

    emoji = _type_emoji(type_filter) if type_filter != "all" else "📚"
    label = _type_label(type_filter) if type_filter != "all" else "Все записи"

    if not items:
        text = (
            f"{emoji} <b>{label}</b>\n\n"
            "Пока здесь пусто.\n\n"
            "Отправь мне фото, ссылку или текст — и я сохраню."
        )
        markup = _back_keyboard()
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        return ConversationHandler.END

    header = f"{emoji} <b>{label}</b> · {len(items)} записей\n\n"

    # Отправляем по одному элементу с кнопками
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            header + "⬇️ Листай ниже", parse_mode="HTML", reply_markup=_back_keyboard()
        )
        chat_id = update.callback_query.message.chat_id
        send = update.callback_query.message.reply_text
    else:
        await update.message.reply_text(header + "⬇️ Листай ниже", parse_mode="HTML")
        send = update.message.reply_text
        chat_id = update.message.chat_id

    for m in items:
        keyboard = _item_keyboard(m["id"], m.get("is_pinned", False))
        if m["type"] == "photo":
            await update.effective_message.get_bot().send_photo(
                chat_id=chat_id,
                photo=m["content"],
                caption=_format_memory(m),
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            await update.effective_message.get_bot().send_message(
                chat_id=chat_id,
                text=_format_memory(m),
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )

    return ConversationHandler.END


# ══════════════════════════════════════════════════════════
# CALLBACK — кнопки под записями
# ══════════════════════════════════════════════════════════

async def memory_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tid = update.effective_user.id
    data = query.data  # "mem_pin:123:0" | "mem_delete:123" | "mem_list:photo" | "mem_main"

    # ── Главное меню ───────────────────────────────────────
    if data == "mem_main":
        counts = _get_counts(tid)
        await query.edit_message_text(
            f"🗂 <b>Память прошлого</b>\n\n"
            f"<b>Всего записей:</b> {counts}\n\n"
            "Выбери категорию:",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    # ── Список по типу ─────────────────────────────────────
    if data.startswith("mem_list:"):
        type_filter = data.split(":")[1]
        await _show_list(update, ctx, type_filter=type_filter)
        return

    # ── Закрепить / открепить ──────────────────────────────
    if data.startswith("mem_pin:"):
        _, mem_id, current = data.split(":")
        mem_id = int(mem_id)
        currently_pinned = current == "1"
        pin_memory(mem_id, not currently_pinned)

        new_label = "📌 Закреплено" if not currently_pinned else "📌 Закрепить"
        other_label = "🗑 Удалить"
        new_cb = f"mem_pin:{mem_id}:{int(not currently_pinned)}"

        new_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(new_label, callback_data=new_cb),
            InlineKeyboardButton(other_label, callback_data=f"mem_delete:{mem_id}"),
        ]])

        status = "📌 Закреплено" if not currently_pinned else "Откреплено"
        try:
            await query.answer(status, show_alert=False)
            await query.edit_message_reply_markup(reply_markup=new_kb)
        except Exception:
            pass
        return

    # ── Удалить ────────────────────────────────────────────
    if data.startswith("mem_delete:"):
        mem_id = int(data.split(":")[1])
        deleted = delete_memory(mem_id, tid)
        if deleted:
            try:
                await query.delete_message()
            except Exception:
                await query.edit_message_text(
                    "🗑 <i>Запись удалена.</i>",
                    parse_mode="HTML",
                )
        else:
            await query.answer("Не удалось удалить", show_alert=True)
        return


# ══════════════════════════════════════════════════════════
# ОБРАБОТКА ССЫЛОК (без команды /memory)
# ══════════════════════════════════════════════════════════

async def handle_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь прислал ссылку в любом месте диалога."""
    text = (update.message.text or "").strip()
    ctx.user_data["mem_content"] = text
    ctx.user_data["mem_type"] = "link"

    await update.message.reply_text(
        "🔗 <b>Вижу ссылку.</b>\n\n"
        "Сохранить в память? Добавь короткое описание:\n"
        "<i>Или напиши «—» чтобы сохранить без описания.</i>",
        parse_mode="HTML",
    )
    return WAITING_CAPTION


# ══════════════════════════════════════════════════════════
# СБОРКА ConversationHandler
# ══════════════════════════════════════════════════════════

def build_memory_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("memory", memory_start),
            MessageHandler(filters.PHOTO & ~filters.COMMAND, memory_start),
            MessageHandler(filters.Regex(URL_RE) & ~filters.COMMAND, handle_link),
        ],
        states={
            WAITING_CAPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_caption),
            ],
        },
        fallbacks=[
            CommandHandler("memory", memory_start),
        ],
        allow_reentry=True,
        name="memory_conv",
    )
