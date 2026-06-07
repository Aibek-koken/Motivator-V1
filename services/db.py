"""
services/db.py — весь CRUD для Qaiyrat бота.
Работает с 7 таблицами Supabase.
"""

import os
import random
from typing import Optional
from supabase import create_client, Client

_client: Optional[Client] = None


def get_db() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL и SUPABASE_KEY должны быть в .env")
        _client = create_client(url, key)
    return _client


# ══════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════

def upsert_user(telegram_id: int, first_name: str = "", username: str = "") -> dict:
    """Создать или обновить пользователя."""
    db = get_db()
    data = {"telegram_id": telegram_id, "first_name": first_name, "username": username or ""}
    result = db.table("users").upsert(data, on_conflict="telegram_id").execute()
    return result.data[0] if result.data else {}


def get_user(telegram_id: int) -> Optional[dict]:
    db = get_db()
    result = db.table("users").select("*").eq("telegram_id", telegram_id).execute()
    return result.data[0] if result.data else None


def get_all_users() -> list[dict]:
    """Все пользователи — для daily checkin."""
    db = get_db()
    return db.table("users").select("telegram_id, first_name").execute().data or []


def set_psycho_mode(telegram_id: int, active: bool) -> None:
    db = get_db()
    db.table("users").update({"in_psycho_mode": active}).eq("telegram_id", telegram_id).execute()


def set_future_mode(telegram_id: int, active: bool) -> None:
    db = get_db()
    db.table("users").update({"in_future_mode": active}).eq("telegram_id", telegram_id).execute()


# ══════════════════════════════════════════════
# FUTURE PROFILE
# ══════════════════════════════════════════════

def get_future_profile(telegram_id: int) -> Optional[dict]:
    db = get_db()
    result = db.table("future_profile").select("*").eq("telegram_id", telegram_id).execute()
    return result.data[0] if result.data else None


def init_future_profile(telegram_id: int) -> dict:
    """Создать пустой профиль если не существует."""
    db = get_db()
    existing = get_future_profile(telegram_id)
    if existing:
        return existing
    result = db.table("future_profile").insert({"telegram_id": telegram_id}).execute()
    return result.data[0] if result.data else {}


def update_future_profile(telegram_id: int, data: dict) -> None:
    """Обновить поля профиля."""
    db = get_db()
    db.table("future_profile").update(data).eq("telegram_id", telegram_id).execute()


def append_future_dialog(telegram_id: int, role: str, content: str) -> None:
    """Добавить сообщение в историю диалога /future."""
    db = get_db()
    profile = get_future_profile(telegram_id)
    if not profile:
        init_future_profile(telegram_id)
        profile = get_future_profile(telegram_id)

    history = profile.get("dialog_history") or []
    history.append({"role": role, "content": content})

    db.table("future_profile").update({
        "dialog_history": history
    }).eq("telegram_id", telegram_id).execute()


def complete_future_profile(telegram_id: int) -> None:
    db = get_db()
    db.table("future_profile").update({"is_complete": True}).eq("telegram_id", telegram_id).execute()


# ══════════════════════════════════════════════
# MEMORIES
# ══════════════════════════════════════════════

def add_memory(telegram_id: int, type_: str, content: str, caption: str = "") -> dict:
    """
    Добавить воспоминание.
    type_: 'photo' | 'text' | 'link' | 'note' | 'voice'
    """
    db = get_db()
    result = db.table("memories").insert({
        "telegram_id": telegram_id,
        "type": type_,
        "content": content,
        "caption": caption or "",
    }).execute()
    return result.data[0] if result.data else {}


def get_memories(telegram_id: int, type_: str = None, limit: int = 10) -> list[dict]:
    """Получить воспоминания. type_=None — все типы."""
    db = get_db()
    query = db.table("memories").select("*").eq("telegram_id", telegram_id)
    if type_:
        query = query.eq("type", type_)
    result = query.order("is_pinned", desc=True).order("created_at", desc=True).limit(limit).execute()
    return result.data or []


def pin_memory(memory_id: int, pinned: bool = True) -> None:
    db = get_db()
    db.table("memories").update({"is_pinned": pinned}).eq("id", memory_id).execute()


def delete_memory(memory_id: int, telegram_id: int) -> bool:
    """Удалить воспоминание (только своё)."""
    db = get_db()
    result = db.table("memories").delete().eq("id", memory_id).eq("telegram_id", telegram_id).execute()
    return bool(result.data)


# ══════════════════════════════════════════════
# TASKS
# ══════════════════════════════════════════════

def add_task(telegram_id: int, text: str, priority: int = 2) -> dict:
    """Добавить задачу. priority: 1=высокий, 2=средний, 3=низкий."""
    db = get_db()
    result = db.table("tasks").insert({
        "telegram_id": telegram_id,
        "text": text,
        "priority": priority,
    }).execute()
    return result.data[0] if result.data else {}


def get_tasks(telegram_id: int, done: bool = False) -> list[dict]:
    """Получить задачи. done=False — только активные."""
    db = get_db()
    result = (
        db.table("tasks")
        .select("*")
        .eq("telegram_id", telegram_id)
        .eq("is_done", done)
        .order("priority", desc=False)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


def complete_task(task_id: int, telegram_id: int) -> Optional[dict]:
    """Отметить задачу выполненной."""
    db = get_db()
    from datetime import datetime, timezone
    result = db.table("tasks").update({
        "is_done": True,
        "done_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", task_id).eq("telegram_id", telegram_id).execute()
    return result.data[0] if result.data else None


def delete_task(task_id: int, telegram_id: int) -> bool:
    db = get_db()
    result = db.table("tasks").delete().eq("id", task_id).eq("telegram_id", telegram_id).execute()
    return bool(result.data)


def update_task_message_id(task_id: int, message_id: int) -> None:
    """Сохранить message_id для последующего редактирования."""
    db = get_db()
    db.table("tasks").update({"message_id": message_id}).eq("id", task_id).execute()


# ══════════════════════════════════════════════
# VICTORIES (Cookie Jar)
# ══════════════════════════════════════════════

def add_victory(telegram_id: int, text: str, source: str = "manual") -> dict:
    db = get_db()
    result = db.table("victories").insert({
        "telegram_id": telegram_id,
        "text": text,
        "source": source,
    }).execute()
    return result.data[0] if result.data else {}


def get_random_victory(telegram_id: int) -> Optional[str]:
    """Случайная победа — для SOS-ответа."""
    db = get_db()
    result = db.table("victories").select("text").eq("telegram_id", telegram_id).execute()
    if not result.data:
        return None
    return random.choice(result.data)["text"]


def get_victories(telegram_id: int, limit: int = 5) -> list[dict]:
    db = get_db()
    result = (
        db.table("victories")
        .select("*")
        .eq("telegram_id", telegram_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ══════════════════════════════════════════════
# PSYCHO SESSIONS
# ══════════════════════════════════════════════

def start_psycho_session(telegram_id: int) -> dict:
    """Начать новую психо-сессию."""
    db = get_db()
    result = db.table("psycho_sessions").insert({
        "telegram_id": telegram_id,
    }).execute()
    return result.data[0] if result.data else {}


def get_active_psycho_session(telegram_id: int) -> Optional[dict]:
    """Получить активную сессию (ended_at is null)."""
    db = get_db()
    result = (
        db.table("psycho_sessions")
        .select("*")
        .eq("telegram_id", telegram_id)
        .is_("ended_at", "null")
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def append_psycho_dialog(session_id: int, role: str, content: str) -> None:
    """Добавить сообщение в историю психо-сессии."""
    db = get_db()
    session = db.table("psycho_sessions").select("dialog_history, message_count").eq("id", session_id).execute()
    if not session.data:
        return
    history = session.data[0].get("dialog_history") or []
    count = session.data[0].get("message_count") or 0
    history.append({"role": role, "content": content})
    db.table("psycho_sessions").update({
        "dialog_history": history,
        "message_count": count + 1,
    }).eq("id", session_id).execute()


def end_psycho_session(session_id: int, mood_after: int = None) -> None:
    """Завершить психо-сессию."""
    db = get_db()
    from datetime import datetime, timezone
    data = {"ended_at": datetime.now(timezone.utc).isoformat()}
    if mood_after:
        data["mood_after"] = mood_after
    db.table("psycho_sessions").update(data).eq("id", session_id).execute()


# ══════════════════════════════════════════════
# DAILY CHECK-IN
# ══════════════════════════════════════════════

def save_checkin(telegram_id: int, question: str) -> dict:
    """Сохранить отправленный вопрос чек-ина."""
    db = get_db()
    result = db.table("daily_checkins").insert({
        "telegram_id": telegram_id,
        "question": question,
    }).execute()
    return result.data[0] if result.data else {}


def answer_checkin(checkin_id: int, answer: str) -> None:
    """Сохранить ответ пользователя на чек-ин."""
    from datetime import datetime, timezone
    db = get_db()
    db.table("daily_checkins").update({
        "answer": answer,
        "answered_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", checkin_id).execute()


# ══════════════════════════════════════════════
# FUTURE MODE GETTER (добавить, если нет)
# ══════════════════════════════════════════════

def get_future_mode(telegram_id: int) -> bool:
    """Вернуть True, если пользователь в режиме /future."""
    user = get_user(telegram_id)
    return user.get("in_future_mode", False) if user else False

# ══════════════════════════════════════════════
# PSYCHO — ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════════

def update_psycho_mood_before(session_id: int, mood: int) -> None:
    """Сохранить настроение до начала сессии (1-5)."""
    db = get_db()
    db.table("psycho_sessions").update({"mood_before": mood}).eq("id", session_id).execute()


def get_psycho_mode(telegram_id: int) -> bool:
    """Вернуть True, если пользователь в активной психо-сессии."""
    user = get_user(telegram_id)
    return user.get("in_psycho_mode", False) if user else False