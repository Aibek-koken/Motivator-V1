"""
services/db.py — работа с Supabase.
Хранит профиль пользователя и его архив побед.
"""

import os
from supabase import create_client, Client
from typing import Optional

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL и SUPABASE_KEY должны быть заданы в .env")
        _client = create_client(url, key)
    return _client


# ──────────────────────────────────────────────
# Профиль пользователя
# ──────────────────────────────────────────────

def save_profile(telegram_id: int, data: dict) -> None:
    """Сохранить или обновить профиль пользователя."""
    client = get_client()
    existing = (
        client.table("profiles")
        .select("id")
        .eq("telegram_id", telegram_id)
        .execute()
    )
    if existing.data:
        client.table("profiles").update(data).eq("telegram_id", telegram_id).execute()
    else:
        client.table("profiles").insert({"telegram_id": telegram_id, **data}).execute()


def get_profile(telegram_id: int) -> Optional[dict]:
    """Получить профиль пользователя."""
    client = get_client()
    result = (
        client.table("profiles")
        .select("*")
        .eq("telegram_id", telegram_id)
        .execute()
    )
    return result.data[0] if result.data else None


def get_all_profiles() -> list[dict]:
    """Все профили — для ежедневной рассылки."""
    client = get_client()
    result = client.table("profiles").select("telegram_id").execute()
    return result.data or []


# ──────────────────────────────────────────────
# Архив побед (Cookie Jar)
# ──────────────────────────────────────────────

def add_victory(telegram_id: int, text: str) -> None:
    """Добавить победу в архив."""
    client = get_client()
    client.table("victories").insert({
        "telegram_id": telegram_id,
        "text": text,
    }).execute()


def get_random_victory(telegram_id: int) -> Optional[str]:
    """Достать случайную победу из архива."""
    client = get_client()
    result = (
        client.table("victories")
        .select("text")
        .eq("telegram_id", telegram_id)
        .execute()
    )
    if not result.data:
        return None
    import random
    return random.choice(result.data)["text"]
