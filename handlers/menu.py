"""
Main menu, /help, and goal summary for Qaiyrat MVP.
"""

from __future__ import annotations

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.db import get_mvp_context, mark_user_active

MAIN_MENU_BUTTONS = [
    ["Я выпал", "Следующий шаг"],
    ["Добавить победу", "Мои задачи"],
    ["Моя цель"],
]


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(MAIN_MENU_BUTTONS, resize_keyboard=True)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mark_user_active(update.effective_user.id)
    await update.message.reply_text(
        "Главное меню Qaiyrat.",
        reply_markup=main_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mark_user_active(update.effective_user.id)
    await update.message.reply_text(
        "Qaiyrat — AI accountability coach, не психолог и не терапевт.\n\n"
        "Что можно делать:\n"
        "• Я выпал — короткая comeback-сессия и один шаг на 5-15 минут.\n"
        "• Следующий шаг — посмотреть или добавить ближайшую задачу.\n"
        "• Добавить победу — сохранить факт, что ты вернулся к действию.\n"
        "• Мои задачи — активные задачи с кнопками Готово и Удалить.\n"
        "• Моя цель — цель, дедлайн, why и твой паттерн срыва.\n\n"
        "Если речь о самоповреждении, суициде, насилии или острой опасности, "
        "Qaiyrat не ведёт коучинг: обратись в экстренные службы или к человеку рядом.",
        reply_markup=main_menu_keyboard(),
    )


async def show_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    mark_user_active(telegram_id)
    data = get_mvp_context(telegram_id)
    goal = data.get("goal") or {}
    profile = data.get("profile") or {}
    vision = data.get("vision_items") or []

    if not goal:
        await update.message.reply_text(
            "У тебя ещё нет цели. Нажми /start — настроим Qaiyrat за 2 минуты."
        )
        return

    lines = [
        "Моя цель",
        "",
        f"Цель: {goal.get('title') or 'не указана'}",
        f"Дедлайн: {goal.get('deadline') or 'не указан'}",
        f"Почему важно: {goal.get('why') or 'не указано'}",
        "",
        f"Что обычно выбивает: {profile.get('blocker_pattern') or 'не указано'}",
        f"Тон Qaiyrat: {profile.get('support_tone') or 'спокойно'}",
    ]

    if vision:
        labels = {
            "desired_future": "Хочу достичь",
            "if_continue": "Если продолжу",
            "if_quit": "Если брошу",
        }
        lines.append("")
        lines.append("Будущее:")
        for item in vision[:3]:
            label = labels.get(item.get("kind"), item.get("kind", "пункт"))
            lines.append(f"• {label}: {item.get('content', '')}")

    await update.message.reply_text("\n".join(lines), reply_markup=main_menu_keyboard())


async def unknown_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    mark_user_active(telegram_id)
    data = get_mvp_context(telegram_id)

    if not data.get("goal"):
        await update.message.reply_text(
            "Начни с /start. Qaiyrat задаст несколько вопросов и настроит твою цель."
        )
        return

    await update.message.reply_text(
        "Я держу фокус на comeback-сценарии. Выбери кнопку ниже: если выпал — «Я выпал», "
        "если хочешь двигаться дальше — «Следующий шаг».",
        reply_markup=main_menu_keyboard(),
    )
