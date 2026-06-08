"""
services/db.py — весь CRUD для Qaiyrat бота.
Добавлены таблицы: psycho_profile, vision_items.
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
    db = get_db()
    data = {"telegram_id": telegram_id, "first_name": first_name, "username": username or ""}
    result = db.table("users").upsert(data, on_conflict="telegram_id").execute()
    return result.data[0] if result.data else {}


def get_user(telegram_id: int) -> Optional[dict]:
    db = get_db()
    result = db.table("users").select("*").eq("telegram_id", telegram_id).execute()
    return result.data[0] if result.data else None


def get_all_users() -> list[dict]:
    db = get_db()
    return db.table("users").select("telegram_id, first_name").execute().data or []


def set_psycho_mode(telegram_id: int, active: bool) -> None:
    db = get_db()
    db.table("users").update({"in_psycho_mode": active}).eq("telegram_id", telegram_id).execute()


def set_future_mode(telegram_id: int, active: bool) -> None:
    db = get_db()
    db.table("users").update({"in_future_mode": active}).eq("telegram_id", telegram_id).execute()


def get_psycho_mode(telegram_id: int) -> bool:
    user = get_user(telegram_id)
    return user.get("in_psycho_mode", False) if user else False


def get_future_mode(telegram_id: int) -> bool:
    user = get_user(telegram_id)
    return user.get("in_future_mode", False) if user else False


# ══════════════════════════════════════════════
# PSYCHO PROFILE (онбординг психолога)
# ══════════════════════════════════════════════

def get_psycho_profile(telegram_id: int) -> Optional[dict]:
    """Получить психологический профиль пользователя."""
    db = get_db()
    result = db.table("psycho_profile").select("*").eq("telegram_id", telegram_id).execute()
    return result.data[0] if result.data else None


def upsert_psycho_profile(telegram_id: int, data: dict) -> dict:
    """Создать или обновить психологический профиль."""
    db = get_db()
    payload = {"telegram_id": telegram_id, **data}
    result = db.table("psycho_profile").upsert(payload, on_conflict="telegram_id").execute()
    return result.data[0] if result.data else {}


def update_psycho_profile(telegram_id: int, data: dict) -> None:
    """Обновить отдельные поля психологического профиля."""
    db = get_db()
    existing = get_psycho_profile(telegram_id)
    if existing:
        db.table("psycho_profile").update(data).eq("telegram_id", telegram_id).execute()
    else:
        upsert_psycho_profile(telegram_id, data)


# ══════════════════════════════════════════════
# FUTURE PROFILE (/future — старый онбординг)
# ══════════════════════════════════════════════

def get_future_profile(telegram_id: int) -> Optional[dict]:
    db = get_db()
    result = db.table("future_profile").select("*").eq("telegram_id", telegram_id).execute()
    return result.data[0] if result.data else None


def init_future_profile(telegram_id: int) -> dict:
    db = get_db()
    existing = get_future_profile(telegram_id)
    if existing:
        return existing
    result = db.table("future_profile").insert({"telegram_id": telegram_id}).execute()
    return result.data[0] if result.data else {}


def update_future_profile(telegram_id: int, data: dict) -> None:
    db = get_db()
    db.table("future_profile").update(data).eq("telegram_id", telegram_id).execute()


def append_future_dialog(telegram_id: int, role: str, content: str) -> None:
    db = get_db()
    profile = get_future_profile(telegram_id)
    if not profile:
        init_future_profile(telegram_id)
        profile = get_future_profile(telegram_id)
    history = profile.get("dialog_history") or []
    history.append({"role": role, "content": content})
    db.table("future_profile").update({"dialog_history": history}).eq("telegram_id", telegram_id).execute()


def complete_future_profile(telegram_id: int) -> None:
    db = get_db()
    db.table("future_profile").update({"is_complete": True}).eq("telegram_id", telegram_id).execute()


# ══════════════════════════════════════════════
# VISION ITEMS (визуализатор будущего)
# ══════════════════════════════════════════════

def get_vision_items(telegram_id: int) -> list[dict]:
    """Получить все элементы доски будущего."""
    db = get_db()
    result = (
        db.table("vision_items")
        .select("*")
        .eq("telegram_id", telegram_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


def add_vision_item(telegram_id: int, category: str, content: str) -> dict:
    """Добавить элемент на доску будущего."""
    db = get_db()
    result = db.table("vision_items").insert({
        "telegram_id": telegram_id,
        "category": category,
        "content": content,
    }).execute()
    return result.data[0] if result.data else {}


def delete_vision_item(item_id: int, telegram_id: int) -> bool:
    """Удалить элемент (только свой)."""
    db = get_db()
    result = db.table("vision_items").delete().eq("id", item_id).eq("telegram_id", telegram_id).execute()
    return bool(result.data)


def update_vision_item(item_id: int, telegram_id: int, content: str) -> None:
    """Обновить текст элемента."""
    db = get_db()
    db.table("vision_items").update({"content": content}).eq("id", item_id).eq("telegram_id", telegram_id).execute()


# ══════════════════════════════════════════════
# MEMORIES
# ══════════════════════════════════════════════

def add_memory(telegram_id: int, type_: str, content: str, caption: str = "") -> dict:
    db = get_db()
    result = db.table("memories").insert({
        "telegram_id": telegram_id,
        "type": type_,
        "content": content,
        "caption": caption or "",
    }).execute()
    return result.data[0] if result.data else {}


def get_memories(telegram_id: int, type_: str = None, limit: int = 10) -> list[dict]:
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
    db = get_db()
    result = db.table("memories").delete().eq("id", memory_id).eq("telegram_id", telegram_id).execute()
    return bool(result.data)


# ══════════════════════════════════════════════
# TASKS
# ══════════════════════════════════════════════

def add_task(telegram_id: int, text: str, priority: int = 2) -> dict:
    db = get_db()
    result = db.table("tasks").insert({
        "telegram_id": telegram_id,
        "text": text,
        "priority": priority,
    }).execute()
    return result.data[0] if result.data else {}


def get_tasks(telegram_id: int, done: bool = False) -> list[dict]:
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
    db = get_db()
    result = db.table("psycho_sessions").insert({"telegram_id": telegram_id}).execute()
    return result.data[0] if result.data else {}


def get_active_psycho_session(telegram_id: int) -> Optional[dict]:
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
    db = get_db()
    from datetime import datetime, timezone
    data = {"ended_at": datetime.now(timezone.utc).isoformat()}
    if mood_after:
        data["mood_after"] = mood_after
    db.table("psycho_sessions").update(data).eq("id", session_id).execute()


def update_psycho_mood_before(session_id: int, mood: int) -> None:
    db = get_db()
    db.table("psycho_sessions").update({"mood_before": mood}).eq("id", session_id).execute()


# ══════════════════════════════════════════════
# DAILY CHECK-IN
# ══════════════════════════════════════════════

def save_checkin(telegram_id: int, question: str) -> dict:
    db = get_db()
    result = db.table("daily_checkins").insert({
        "telegram_id": telegram_id,
        "question": question,
    }).execute()
    return result.data[0] if result.data else {}


def answer_checkin(checkin_id: int, answer: str) -> None:
    from datetime import datetime, timezone
    db = get_db()
    db.table("daily_checkins").update({
        "answer": answer,
        "answered_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", checkin_id).execute()