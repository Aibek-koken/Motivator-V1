"""
handlers/tasks.py — команда /tasks

Потоки:
  /tasks              → список активных задач с кнопками
  /tasks текст        → сразу добавить задачу
  callback "tsk_done" → отметить выполненной
  callback "tsk_del"  → удалить
  callback "tsk_add"  → кнопка "добавить" из списка
  callback "tsk_done_list" → показать выполненные
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
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
    add_task,
    get_tasks,
    complete_task,
    delete_task,
    add_victory,
)

WAITING_TASK_TEXT = 10   # состояние — ждём текст новой задачи

PRIORITY_EMOJI = {1: "🔴", 2: "🟡", 3: "⚪️"}
PRIORITY_LABEL = {1: "высокий", 2: "средний", 3: "низкий"}


# ══════════════════════════════════════════════════════════
# УТИЛИТЫ
# ══════════════════════════════════════════════════════════

def _task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Выполнено", callback_data=f"tsk_done:{task_id}"),
        InlineKeyboardButton("🗑 Удалить",   callback_data=f"tsk_del:{task_id}"),
    ]])


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить задачу",    callback_data="tsk_add")],
        [InlineKeyboardButton("📋 Выполненные",        callback_data="tsk_done_list")],
    ])


def _format_task(t: dict) -> str:
    priority_em = PRIORITY_EMOJI.get(t.get("priority", 2), "🟡")
    date = str(t.get("created_at", ""))[:10]
    text = t["text"]
    return f"{priority_em} {text}\n<i>добавлена {date}</i>"


def _detect_priority(text: str) -> int:
    """Пытаемся угадать приоритет по ключевым словам."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["срочно", "сегодня", "важно", "asap", "deadline"]):
        return 1
    if any(w in text_lower for w in ["потом", "когда-нибудь", "не срочно", "позже"]):
        return 3
    return 2


# ══════════════════════════════════════════════════════════
# /tasks — главный вход
# ══════════════════════════════════════════════════════════

async def tasks_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    upsert_user(user.id, user.first_name or "", user.username or "")

    # Если написали /tasks + текст — сразу добавляем
    text = (update.message.text or "").strip()
    arg = text.replace("/tasks", "").strip()
    if arg:
        return await _save_task(update, ctx, arg)

    return await _show_tasks(update, ctx)


async def _show_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    tasks = get_tasks(tid, done=False)

    if not tasks:
        msg = (
            "✅ <b>Задачи</b>\n\n"
            "Список пуст — отличный момент чтобы добавить первую.\n\n"
            "Напиши задачу прямо сейчас или нажми кнопку:"
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(
                msg, parse_mode="HTML", reply_markup=_main_keyboard()
            )
        else:
            await update.message.reply_text(
                msg, parse_mode="HTML", reply_markup=_main_keyboard()
            )
        return ConversationHandler.END

    total = len(tasks)
    high = sum(1 for t in tasks if t.get("priority") == 1)

    header = (
        f"✅ <b>Задачи</b> · {total} активных"
        + (f" · {high} срочных 🔴" if high else "")
        + "\n\n"
    )

    # Шлём каждую задачу отдельным сообщением с кнопками
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            header + "⬇️ Листай ниже",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        chat_id = update.callback_query.message.chat_id
        bot = update.callback_query.message.get_bot()
    else:
        await update.message.reply_text(
            header + "⬇️ Листай ниже",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        chat_id = update.message.chat_id
        bot = update.message.get_bot()

    for t in tasks:
        await bot.send_message(
            chat_id=chat_id,
            text=_format_task(t),
            parse_mode="HTML",
            reply_markup=_task_keyboard(t["id"]),
        )

    return ConversationHandler.END


# ══════════════════════════════════════════════════════════
# ДОБАВЛЕНИЕ ЗАДАЧИ
# ══════════════════════════════════════════════════════════

async def _save_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    tid = update.effective_user.id
    priority = _detect_priority(text)
    task = add_task(tid, text, priority)

    p_em = PRIORITY_EMOJI[priority]
    p_lb = PRIORITY_LABEL[priority]

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Выполнено", callback_data=f"tsk_done:{task['id']}"),
        InlineKeyboardButton("🗑 Удалить",   callback_data=f"tsk_del:{task['id']}"),
    ],[
        InlineKeyboardButton("➕ Ещё задачу", callback_data="tsk_add"),
        InlineKeyboardButton("📋 Все задачи", callback_data="tsk_show"),
    ]])

    msg = (
        f"➕ <b>Задача добавлена</b>\n\n"
        f"{p_em} {text}\n"
        f"<i>Приоритет: {p_lb}</i>"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            msg, parse_mode="HTML", reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            msg, parse_mode="HTML", reply_markup=keyboard
        )

    return ConversationHandler.END


async def ask_task_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Нажали кнопку 'Добавить' — просим написать текст."""
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "✏️ <b>Напиши задачу</b>\n\n"
        "Просто текстом — я добавлю её в список.\n"
        "<i>Если напишешь «срочно» — поставлю высокий приоритет 🔴</i>",
        parse_mode="HTML",
    )
    return WAITING_TASK_TEXT


async def receive_task_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Получили текст задачи после нажатия кнопки."""
    text = (update.message.text or "").strip()
    if not text:
        return WAITING_TASK_TEXT
    return await _save_task(update, ctx, text)


# ══════════════════════════════════════════════════════════
# ВЫПОЛНЕННЫЕ ЗАДАЧИ
# ══════════════════════════════════════════════════════════

async def show_done_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    tid = update.effective_user.id
    done = get_tasks(tid, done=True)

    if not done:
        await update.callback_query.message.reply_text(
            "📋 <b>Выполненные задачи</b>\n\n"
            "Пока пусто — выполни первую задачу из списка 💪",
            parse_mode="HTML",
        )
        return

    lines = [f"📋 <b>Выполненные</b> · {len(done)}\n"]
    for t in done[:20]:
        done_date = str(t.get("done_at", ""))[:10]
        lines.append(f"✅ {t['text']} <i>· {done_date}</i>")

    await update.callback_query.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════
# CALLBACKS — кнопки ✅ и 🗑
# ══════════════════════════════════════════════════════════

async def tasks_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tid = update.effective_user.id
    data = query.data

    # ── Показать список ────────────────────────────────────
    if data == "tsk_show":
        await _show_tasks(update, ctx)
        return

    # ── Выполненные ────────────────────────────────────────
    if data == "tsk_done_list":
        await show_done_tasks(update, ctx)
        return

    # ── Добавить (кнопка) — передаём в ConversationHandler ─
    # (обрабатывается через entry_points)
    if data == "tsk_add":
        await ask_task_text(update, ctx)
        return

    # ── Отметить выполненной ──────────────────────────────
    if data.startswith("tsk_done:"):
        task_id = int(data.split(":")[1])
        task = complete_task(task_id, tid)

        if not task:
            await query.answer("Задача не найдена", show_alert=True)
            return

        # Проверяем — это была важная задача?
        task_text = task.get("text", "")
        if task.get("priority") == 1:
            add_victory(tid, f"Выполнил важную задачу: {task_text}", source="manual")

        try:
            # Зачёркиваем текст — редактируем сообщение
            await query.edit_message_text(
                f"✅ <s>{task_text}</s>\n<i>Выполнено 🎉</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🗑 Удалить", callback_data=f"tsk_del:{task_id}")
                ]])
            )
        except Exception:
            pass
        return

    # ── Удалить ────────────────────────────────────────────
    if data.startswith("tsk_del:"):
        task_id = int(data.split(":")[1])
        delete_task(task_id, tid)
        try:
            await query.delete_message()
        except Exception:
            await query.edit_message_text("<i>Удалено</i>", parse_mode="HTML")
        return


# ══════════════════════════════════════════════════════════
# СБОРКА ConversationHandler
# ══════════════════════════════════════════════════════════

def build_tasks_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("tasks", tasks_start),
            CallbackQueryHandler(ask_task_text, pattern="^tsk_add$"),
        ],
        states={
            WAITING_TASK_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_text),
            ],
        },
        fallbacks=[
            CommandHandler("tasks", tasks_start),
        ],
        allow_reentry=True,
        name="tasks_conv",
    )