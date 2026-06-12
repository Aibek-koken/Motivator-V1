"""
Simple task management for Qaiyrat MVP.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.menu import main_menu_keyboard
from services.db import (
    add_task,
    complete_task_and_record_win,
    delete_task,
    get_active_tasks,
    get_mvp_context,
    mark_user_active,
)

WAITING_TASK_TEXT = 1


def _task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Готово", callback_data=f"task_done:{task_id}"),
                InlineKeyboardButton("Удалить", callback_data=f"task_delete:{task_id}"),
            ]
        ]
    )


async def tasks_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    mark_user_active(telegram_id)
    data = get_mvp_context(telegram_id)

    if not data.get("goal"):
        await update.message.reply_text("Сначала настрой цель через /start.")
        return ConversationHandler.END

    text = update.message.text.strip() if update.message and update.message.text else ""
    command_arg = text.replace("/tasks", "", 1).strip() if text.startswith("/tasks") else ""

    if command_arg:
        await _save_task(update, command_arg)
        return ConversationHandler.END

    if text == "Следующий шаг":
        tasks = get_active_tasks(telegram_id, limit=1)
        if tasks:
            task = tasks[0]
            await update.message.reply_text(
                "Следующий шаг:\n\n"
                f"{task['text']}\n\n"
                "Сделай это без лишнего анализа. Когда закончишь — нажми «Готово».",
                reply_markup=_task_keyboard(task["id"]),
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "Активных задач нет. Напиши один следующий шаг на 5-15 минут."
        )
        return WAITING_TASK_TEXT

    await _show_tasks(update)
    return ConversationHandler.END


async def receive_task_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Напиши задачу текстом.")
        return WAITING_TASK_TEXT

    await _save_task(update, text)
    return ConversationHandler.END


async def _save_task(update: Update, text: str) -> None:
    telegram_id = update.effective_user.id
    data = get_mvp_context(telegram_id)
    if not data.get("goal"):
        await update.message.reply_text("Сначала настрой цель через /start.")
        return

    task = add_task(telegram_id, text, source="manual")
    await update.message.reply_text(
        "Задача добавлена.\n\n"
        f"{task['text']}",
        reply_markup=_task_keyboard(task["id"]),
    )


async def _show_tasks(update: Update) -> None:
    telegram_id = update.effective_user.id
    tasks = get_active_tasks(telegram_id, limit=20)

    if not tasks:
        await update.message.reply_text(
            "Активных задач нет.\n\n"
            "Добавь одну маленькую задачу так: /tasks написать 3 строки плана",
            reply_markup=main_menu_keyboard(),
        )
        return

    await update.message.reply_text(
        f"Мои задачи: {len(tasks)} активных",
        reply_markup=main_menu_keyboard(),
    )
    for task in tasks:
        await update.message.reply_text(task["text"], reply_markup=_task_keyboard(task["id"]))


async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    telegram_id = update.effective_user.id
    data = query.data

    if data.startswith("task_done:"):
        task_id = int(data.split(":")[1])
        result = complete_task_and_record_win(task_id, telegram_id)
        task = result.get("task")

        if not task:
            await query.answer("Задача уже закрыта или не найдена.", show_alert=True)
            return

        await query.edit_message_reply_markup(reply_markup=None)

        if task.get("source") == "comeback":
            await query.message.reply_text(
                "Вот это и есть возврат. Не настроение решает, а маленькое действие.\n\n"
                f"Победа сохранена: {task['text']}",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await query.message.reply_text(
                f"Готово. Записал как победу: {task['text']}",
                reply_markup=main_menu_keyboard(),
            )
        return

    if data.startswith("task_delete:"):
        task_id = int(data.split(":")[1])
        deleted = delete_task(task_id, telegram_id)
        if not deleted:
            await query.answer("Задача не найдена.", show_alert=True)
            return
        await query.edit_message_text("Задача удалена.")
        return


async def cancel_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Остановил добавление задачи.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_tasks_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("tasks", tasks_entry),
            MessageHandler(filters.Regex("^(Мои задачи|Следующий шаг)$"), tasks_entry),
        ],
        states={
            WAITING_TASK_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_text)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_tasks),
            MessageHandler(filters.Regex("^Главное меню$"), cancel_tasks),
        ],
        name="qaiyrat_tasks",
        allow_reentry=True,
        per_user=True,
        per_chat=True,
    )
