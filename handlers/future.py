"""
handlers/future.py — Визуализатор будущего (Vision Board).

Структура меню:
  /future
  ├── ➕ Добавить  → AI спрашивает что хочешь добавить, сохраняет в vision_items
  ├── 🌅 Погружение → показывает всю доску красиво
  └── ✏️ Редактировать → список элементов с кнопками Удалить

Элементы vision board (vision_items):
  - machine      — машина / транспорт
  - home         — дом / жильё
  - body         — тело / здоровье
  - income       — доход / деньги
  - travel       — путешествие / место
  - relationship — отношения
  - skill        — навык / достижение
  - quote        — цитата / принцип
  - other        — другое
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters,
)
from services.db import (
    get_user, get_future_profile, init_future_profile,
    update_future_profile, complete_future_profile,
    get_vision_items, add_vision_item, delete_vision_item,
)
from services.ai import generate_vision_clarification, generate_vision_immersion

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Состояния
# ──────────────────────────────────────────────
MAIN_MENU   = 1
ADD_FLOW    = 2   # AI задаёт уточняющий вопрос
ADD_CONFIRM = 3   # пользователь описывает мечту
EDIT_FLOW   = 4   # редактирование списка

# Категории для визуализатора
CATEGORIES = {
    "machine":      ("🚗", "Машина / транспорт"),
    "home":         ("🏠", "Дом / жильё"),
    "body":         ("💪", "Тело / здоровье"),
    "income":       ("💰", "Доход / финансы"),
    "travel":       ("✈️", "Путешествие / место"),
    "relationship": ("❤️", "Отношения / люди"),
    "skill":        ("🎓", "Навык / достижение"),
    "quote":        ("💬", "Цитата / принцип"),
    "other":        ("⭐", "Другое"),
}


def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить", callback_data="vis_add")],
        [InlineKeyboardButton("🌅 Погружение", callback_data="vis_immerse")],
        [InlineKeyboardButton("✏️ Редактировать", callback_data="vis_edit")],
    ])


# ──────────────────────────────────────────────
# Точка входа
# ──────────────────────────────────────────────
async def future_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    user = get_user(tid)
    if not user:
        await update.message.reply_text("Сначала напиши /start.")
        return ConversationHandler.END

    items = get_vision_items(tid)

    if not items:
        # Первый запуск — объясняем что это
        await update.message.reply_text(
            "🌅 <b>Твой визуализатор будущего</b>\n\n"
            "Здесь ты собираешь то, чем реально горишь:\n"
            "машина, дом, тело, доход, путешествие — или цитата которая тебя держит.\n\n"
            "Добавляй всё что хочешь достичь. Это твоя карта.",
            parse_mode="HTML",
            reply_markup=_main_kb()
        )
    else:
        count = len(items)
        await update.message.reply_text(
            f"🌅 <b>Визуализатор</b> · {count} {'элемент' if count == 1 else 'элементов'}\n\n"
            "Что хочешь сделать?",
            parse_mode="HTML",
            reply_markup=_main_kb()
        )
    return MAIN_MENU


# ──────────────────────────────────────────────
# Добавить элемент
# ──────────────────────────────────────────────
async def vis_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.delete()

    # Показываем категории
    rows = []
    cats = list(CATEGORIES.items())
    for i in range(0, len(cats), 2):
        row = []
        for key, (emoji, label) in cats[i:i+2]:
            row.append(InlineKeyboardButton(f"{emoji} {label}", callback_data=f"vis_cat_{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="vis_back")])

    await query.message.reply_text(
        "Что хочешь добавить?",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return ADD_FLOW


async def vis_category_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category = query.data.replace("vis_cat_", "")
    ctx.user_data["vis_category"] = category

    emoji, label = CATEGORIES.get(category, ("⭐", "Другое"))
    await query.message.delete()

    # AI задаёт конкретный уточняющий вопрос для этой категории
    clarifying_q = _get_clarifying_question(category)

    await query.message.reply_text(
        f"{emoji} <b>{label}</b>\n\n{clarifying_q}",
        parse_mode="HTML"
    )
    return ADD_CONFIRM


def _get_clarifying_question(category: str) -> str:
    questions = {
        "machine": "Какая машина? Напиши марку и почему именно она. Можно добавить цвет, год — чем конкретнее, тем лучше.",
        "home":    "Какой дом или квартира? Где, сколько комнат, как выглядит — опиши как видишь.",
        "body":    "Каким ты хочешь быть? Вес, форма, силовые показатели — что для тебя идеал?",
        "income":  "Какой доход ты хочешь? Сумма в месяц, источник — откуда эти деньги придут?",
        "travel":  "Куда хочешь попасть? Страна, город, место — что там будешь делать?",
        "relationship": "Опиши это. Отношения, семья, дружба — что конкретно хочешь иметь в жизни?",
        "skill":   "Какой навык или достижение? Что именно умеешь или кем становишься?",
        "quote":   "Напиши цитату или принцип, который тебя держит. Можно своими словами.",
        "other":   "Опиши что хочешь добавить — своими словами, без ограничений.",
    }
    return questions.get(category, "Опиши что именно хочешь:")


async def vis_add_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь написал описание своей мечты."""
    tid = update.effective_user.id
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Напиши что-нибудь.")
        return ADD_CONFIRM

    category = ctx.user_data.get("vis_category", "other")
    emoji, label = CATEGORIES.get(category, ("⭐", "Другое"))

    # Сохраняем
    item = add_vision_item(tid, category=category, content=text)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить ещё", callback_data="vis_add")],
        [InlineKeyboardButton("🌅 Посмотреть доску", callback_data="vis_immerse")],
        [InlineKeyboardButton("🏠 В меню", callback_data="vis_back")],
    ])

    await update.message.reply_text(
        f"✅ <b>Добавлено: {emoji} {label}</b>\n\n<i>{text[:120]}{'...' if len(text) > 120 else ''}</i>",
        parse_mode="HTML",
        reply_markup=kb
    )
    return MAIN_MENU


# ──────────────────────────────────────────────
# Погружение — красивый показ всей доски
# ──────────────────────────────────────────────
async def vis_immerse(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tid = update.effective_user.id

    items = get_vision_items(tid)
    if not items:
        await query.edit_message_text(
            "Доска пустая. Сначала добавь хоть что-то — /future",
        )
        return MAIN_MENU

    await query.message.delete()

    # Группируем по категориям
    grouped = {}
    for item in items:
        cat = item.get("category", "other")
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(item)

    # Генерируем AI-погружение
    future_profile = get_future_profile(tid) or {}
    immersion_text = generate_vision_immersion(items, future_profile)

    # Сначала структурированная доска
    board_lines = ["🌅 <b>Твоя доска будущего</b>\n"]
    for cat, cat_items in grouped.items():
        emoji, label = CATEGORIES.get(cat, ("⭐", "Другое"))
        board_lines.append(f"\n{emoji} <b>{label}</b>")
        for it in cat_items:
            content = it.get("content", "")
            board_lines.append(f"  • {content[:100]}{'...' if len(content) > 100 else ''}")

    board_text = "\n".join(board_lines)
    await query.message.reply_text(board_text, parse_mode="HTML")

    # Потом AI-текст (погружение)
    if immersion_text:
        await query.message.reply_text(immersion_text, parse_mode="HTML")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить ещё", callback_data="vis_add")],
        [InlineKeyboardButton("✏️ Редактировать", callback_data="vis_edit")],
    ])
    await query.message.reply_text("Что дальше?", reply_markup=kb)
    return MAIN_MENU


# ──────────────────────────────────────────────
# Редактирование — список с кнопкой Удалить
# ──────────────────────────────────────────────
async def vis_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tid = update.effective_user.id

    items = get_vision_items(tid)
    if not items:
        await query.edit_message_text("Доска пустая. Нечего редактировать.")
        return MAIN_MENU

    await query.message.delete()

    # Показываем каждый элемент с кнопкой Удалить
    await query.message.reply_text(
        "✏️ <b>Редактирование</b>\n\nВот все элементы. Нажми 🗑 чтобы удалить.",
        parse_mode="HTML"
    )

    for item in items:
        cat = item.get("category", "other")
        emoji, label = CATEGORIES.get(cat, ("⭐", "Другое"))
        content = item.get("content", "")
        item_id = item.get("id")

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"🗑 Удалить", callback_data=f"vis_del_{item_id}")
        ]])
        await query.message.reply_text(
            f"{emoji} <b>{label}</b>\n{content[:200]}",
            parse_mode="HTML",
            reply_markup=kb
        )

    kb_back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="vis_back")]])
    await query.message.reply_text("─────", reply_markup=kb_back)
    return EDIT_FLOW


async def vis_delete_item(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tid = update.effective_user.id

    item_id = int(query.data.replace("vis_del_", ""))
    delete_vision_item(item_id, tid)

    await query.edit_message_text("🗑 Удалено.")
    return EDIT_FLOW


# ──────────────────────────────────────────────
# Навигация назад
# ──────────────────────────────────────────────
async def vis_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tid = update.effective_user.id

    items = get_vision_items(tid)
    count = len(items)

    await query.edit_message_text(
        f"🌅 <b>Визуализатор</b>" + (f" · {count} элементов" if count else "") + "\n\nЧто хочешь сделать?",
        parse_mode="HTML",
        reply_markup=_main_kb()
    )
    return MAIN_MENU


# ──────────────────────────────────────────────
# Публичный callback для bot.py (кнопки вне ConversationHandler)
# ──────────────────────────────────────────────
async def future_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает vis_* колбэки вне ConversationHandler (если вдруг)."""
    query = update.callback_query
    await query.answer()
    # Просто направляем в меню
    await query.edit_message_text(
        "Используй /future чтобы открыть визуализатор.",
    )


# ──────────────────────────────────────────────
# Сборка
# ──────────────────────────────────────────────
def build_future_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("future", future_start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(vis_add, pattern="^vis_add$"),
                CallbackQueryHandler(vis_immerse, pattern="^vis_immerse$"),
                CallbackQueryHandler(vis_edit, pattern="^vis_edit$"),
                CallbackQueryHandler(vis_back, pattern="^vis_back$"),
            ],
            ADD_FLOW: [
                CallbackQueryHandler(vis_category_selected, pattern="^vis_cat_"),
                CallbackQueryHandler(vis_back, pattern="^vis_back$"),
            ],
            ADD_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, vis_add_text),
            ],
            EDIT_FLOW: [
                CallbackQueryHandler(vis_delete_item, pattern="^vis_del_"),
                CallbackQueryHandler(vis_back, pattern="^vis_back$"),
                # Кнопка "добавить ещё" из edit экрана
                CallbackQueryHandler(vis_add, pattern="^vis_add$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: u.message.reply_text("Отменено. /future — открыть заново.")),
        ],
        name="future_conv",
        allow_reentry=True,
        per_user=True,
        per_chat=True,
    )