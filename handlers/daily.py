"""
handlers/daily.py — ежедневный вечерний чек-ин.
Запускается планировщиком в 20:00 по Алматы.
"""

import logging
from telegram import Bot
from telegram.error import TelegramError
from services.db import get_all_profiles, get_profile
from services.ai import generate_daily_question
from handlers.sos import AWAITING_DAILY

logger = logging.getLogger(__name__)

# Хранилище user_data недоступно вне контекста —
# используем простой in-memory dict для флага ожидания
_awaiting: set[int] = set()


async def send_daily_checkin(bot: Bot) -> None:
    """Отправляет ежедневный вопрос всем пользователям."""
    profiles = get_all_profiles()
    logger.info(f"Ежедневный чек-ин: {len(profiles)} пользователей")

    for entry in profiles:
        telegram_id = entry["telegram_id"]
        try:
            profile = get_profile(telegram_id)
            if not profile or not profile.get("goal"):
                continue

            question = generate_daily_question(profile)

            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    "🌙 <b>Вечерний вопрос</b>\n\n"
                    f"{question}\n\n"
                    "<i>Напиши — даже если это было маленькое. Я сохраню это в твой архив.</i>"
                ),
                parse_mode="HTML",
            )
            _awaiting.add(telegram_id)

        except TelegramError as e:
            logger.warning(f"Не удалось отправить чек-ин {telegram_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка чек-ин {telegram_id}: {e}")


def is_awaiting_daily(telegram_id: int) -> bool:
    return telegram_id in _awaiting


def clear_awaiting(telegram_id: int) -> None:
    _awaiting.discard(telegram_id)
