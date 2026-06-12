"""
Supabase CRUD for the focused Qaiyrat MVP.

The product model is intentionally small:
- one active goal
- one accountability profile
- simple tasks
- short wins
- comeback sessions with compact message history
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client, create_client

_client: Optional[Client] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first(result: Any) -> Optional[dict]:
    return result.data[0] if getattr(result, "data", None) else None


def get_db() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        _client = create_client(url, key)
    return _client


# Users


def upsert_user(telegram_id: int, first_name: str = "", username: str = "") -> dict:
    db = get_db()
    payload = {
        "telegram_id": telegram_id,
        "first_name": first_name or "",
        "username": username or "",
        "last_active_at": _now(),
    }
    result = db.table("users").upsert(payload, on_conflict="telegram_id").execute()
    return _first(result) or {}


def mark_user_active(telegram_id: int) -> None:
    get_db().table("users").update({"last_active_at": _now()}).eq(
        "telegram_id", telegram_id
    ).execute()


def get_user(telegram_id: int) -> Optional[dict]:
    result = get_db().table("users").select("*").eq("telegram_id", telegram_id).execute()
    return _first(result)


def get_all_users() -> list[dict]:
    result = (
        get_db()
        .table("users")
        .select("telegram_id, first_name, onboarding_completed")
        .eq("onboarding_completed", True)
        .execute()
    )
    return result.data or []


def set_onboarding_completed(telegram_id: int, completed: bool = True) -> None:
    get_db().table("users").update(
        {"onboarding_completed": completed, "last_active_at": _now()}
    ).eq("telegram_id", telegram_id).execute()


def _bump_user_counter(telegram_id: int, field: str) -> None:
    user = get_user(telegram_id) or {}
    current = user.get(field) or 0
    get_db().table("users").update({field: current + 1, "last_active_at": _now()}).eq(
        "telegram_id", telegram_id
    ).execute()


# Goals and profiles


def get_active_goal(telegram_id: int) -> Optional[dict]:
    query = (
        get_db()
        .table("goals")
        .select("*")
        .eq("telegram_id", telegram_id)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if query.data:
        return query.data[0]

    fallback = (
        get_db()
        .table("goals")
        .select("*")
        .eq("telegram_id", telegram_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return _first(fallback)


def create_goal(telegram_id: int, title: str, deadline: str, why: str) -> dict:
    db = get_db()
    db.table("goals").update({"is_active": False}).eq("telegram_id", telegram_id).eq(
        "is_active", True
    ).execute()
    result = (
        db.table("goals")
        .insert(
            {
                "telegram_id": telegram_id,
                "title": title.strip(),
                "deadline": deadline.strip(),
                "why": why.strip(),
                "is_active": True,
            }
        )
        .execute()
    )
    return _first(result) or {}

def update_active_goal(telegram_id: int, data: dict) -> None:
    goal = get_active_goal(telegram_id)
    if not goal:
        return
    allowed = {k: v for k, v in data.items() if k in {"title", "deadline", "why"}}
    if allowed:
        get_db().table("goals").update(allowed).eq("id", goal["id"]).execute()


def get_user_profile(telegram_id: int) -> Optional[dict]:
    result = (
        get_db()
        .table("user_profiles")
        .select("*")
        .eq("telegram_id", telegram_id)
        .execute()
    )
    return _first(result)


def upsert_user_profile(
    telegram_id: int,
    blocker_pattern: str,
    support_tone: str,
) -> dict:
    result = (
        get_db()
        .table("user_profiles")
        .upsert(
            {
                "telegram_id": telegram_id,
                "blocker_pattern": blocker_pattern.strip(),
                "support_tone": support_tone.strip(),
            },
            on_conflict="telegram_id",
        )
        .execute()
    )
    return _first(result) or {}


def complete_onboarding(
    telegram_id: int,
    goal_title: str,
    deadline: str,
    why: str,
    blocker_pattern: str,
    support_tone: str,
    first_task: str,
) -> dict:
    goal = create_goal(telegram_id, goal_title, deadline, why)
    profile = upsert_user_profile(telegram_id, blocker_pattern, support_tone)
    set_onboarding_completed(telegram_id, True)

    task = None
    if first_task.strip():
        task = add_task(
            telegram_id=telegram_id,
            text=first_task,
            source="onboarding",
            goal_id=goal.get("id"),
        )

    return {"goal": goal, "profile": profile, "first_task": task}


def get_mvp_context(telegram_id: int) -> dict:
    return {
        "user": get_user(telegram_id) or {},
        "goal": get_active_goal(telegram_id) or {},
        "profile": get_user_profile(telegram_id) or {},
        "vision_items": get_vision_items(telegram_id),
    }


# Tasks


def add_task(
    telegram_id: int,
    text: str,
    source: str = "manual",
    goal_id: Optional[int] = None,
    comeback_session_id: Optional[int] = None,
) -> dict:
    goal = {"id": goal_id} if goal_id else get_active_goal(telegram_id)
    payload = {
        "telegram_id": telegram_id,
        "goal_id": goal.get("id") if goal else None,
        "text": text.strip(),
        "status": "active",
        "source": source,
        "comeback_session_id": comeback_session_id,
    }
    result = get_db().table("tasks").insert(payload).execute()
    return _first(result) or {}


def get_tasks(telegram_id: int, status: str = "active", limit: int = 20) -> list[dict]:
    result = (
        get_db()
        .table("tasks")
        .select("*")
        .eq("telegram_id", telegram_id)
        .eq("status", status)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_active_tasks(telegram_id: int, limit: int = 5) -> list[dict]:
    return get_tasks(telegram_id, status="active", limit=limit)


def complete_task(task_id: int, telegram_id: int) -> Optional[dict]:
    result = (
        get_db()
        .table("tasks")
        .update({"status": "completed", "completed_at": _now()})
        .eq("id", task_id)
        .eq("telegram_id", telegram_id)
        .eq("status", "active")
        .execute()
    )
    task = _first(result)
    if task:
        _bump_user_counter(telegram_id, "completed_task_count")
    return task


def delete_task(task_id: int, telegram_id: int) -> bool:
    result = (
        get_db()
        .table("tasks")
        .update({"status": "deleted", "deleted_at": _now()})
        .eq("id", task_id)
        .eq("telegram_id", telegram_id)
        .eq("status", "active")
        .execute()
    )
    return bool(result.data)


def complete_task_and_record_win(task_id: int, telegram_id: int) -> dict:
    task = complete_task(task_id, telegram_id)
    if not task:
        return {"task": None, "win": None}

    source = "comeback" if task.get("source") == "comeback" else "task"
    win_text = f"Сделал: {task.get('text', '').strip()}"
    win = add_win(
        telegram_id=telegram_id,
        text=win_text,
        source=source,
        goal_id=task.get("goal_id"),
        task_id=task.get("id"),
    )

    if task.get("source") == "comeback":
        complete_comeback_session_by_task(task["id"], telegram_id)

    return {"task": task, "win": win}


# Wins


def add_win(
    telegram_id: int,
    text: str,
    source: str = "manual",
    goal_id: Optional[int] = None,
    task_id: Optional[int] = None,
) -> dict:
    goal = {"id": goal_id} if goal_id else get_active_goal(telegram_id)
    result = (
        get_db()
        .table("wins")
        .insert(
            {
                "telegram_id": telegram_id,
                "goal_id": goal.get("id") if goal else None,
                "task_id": task_id,
                "text": text.strip(),
                "source": source,
            }
        )
        .execute()
    )
    return _first(result) or {}


def get_recent_wins(telegram_id: int, limit: int = 5) -> list[dict]:
    result = (
        get_db()
        .table("wins")
        .select("*")
        .eq("telegram_id", telegram_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_random_win(telegram_id: int) -> Optional[str]:
    wins = get_recent_wins(telegram_id, limit=50)
    return random.choice(wins)["text"] if wins else None


# Comeback sessions


def create_comeback_session(
    telegram_id: int,
    trigger_reason: str,
    days_slipped: str,
    blocker: str,
) -> dict:
    goal = get_active_goal(telegram_id)
    result = (
        get_db()
        .table("comeback_sessions")
        .insert(
            {
                "telegram_id": telegram_id,
                "goal_id": goal.get("id") if goal else None,
                "status": "active",
                "trigger_reason": trigger_reason.strip(),
                "days_slipped": days_slipped.strip(),
                "blocker": blocker.strip(),
            }
        )
        .execute()
    )
    session = _first(result) or {}
    if session:
        _bump_user_counter(telegram_id, "comeback_session_count")
    return session


def get_comeback_session(session_id: int, telegram_id: int) -> Optional[dict]:
    result = (
        get_db()
        .table("comeback_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("telegram_id", telegram_id)
        .execute()
    )
    return _first(result)


def update_comeback_session(session_id: int, telegram_id: int, data: dict) -> None:
    if data:
        get_db().table("comeback_sessions").update(data).eq("id", session_id).eq(
            "telegram_id", telegram_id
        ).execute()


def add_comeback_message(
    session_id: int,
    telegram_id: int,
    role: str,
    content: str,
) -> dict:
    result = (
        get_db()
        .table("comeback_messages")
        .insert(
            {
                "session_id": session_id,
                "telegram_id": telegram_id,
                "role": role,
                "content": content.strip(),
            }
        )
        .execute()
    )
    return _first(result) or {}


def mark_comeback_proposed(
    session_id: int,
    telegram_id: int,
    ai_response: str,
    proposed_action: str,
) -> None:
    update_comeback_session(
        session_id,
        telegram_id,
        {
            "status": "proposed",
            "ai_response": ai_response,
            "proposed_action": proposed_action,
        },
    )


def commit_comeback_session(
    session_id: int,
    telegram_id: int,
    task_id: int,
) -> None:
    update_comeback_session(
        session_id,
        telegram_id,
        {"status": "committed", "task_id": task_id, "committed_at": _now()},
    )


def complete_comeback_session_by_task(task_id: int, telegram_id: int) -> None:
    result = (
        get_db()
        .table("comeback_sessions")
        .select("id")
        .eq("task_id", task_id)
        .eq("telegram_id", telegram_id)
        .limit(1)
        .execute()
    )
    session = _first(result)
    if session:
        update_comeback_session(
            session["id"],
            telegram_id,
            {"status": "completed", "completed_at": _now()},
        )


# Simple future context


def get_vision_items(telegram_id: int) -> list[dict]:
    result = (
        get_db()
        .table("vision_items")
        .select("*")
        .eq("telegram_id", telegram_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


def upsert_vision_item(telegram_id: int, kind: str, content: str) -> dict:
    goal = get_active_goal(telegram_id)
    result = (
        get_db()
        .table("vision_items")
        .upsert(
            {
                "telegram_id": telegram_id,
                "goal_id": goal.get("id") if goal else None,
                "kind": kind,
                "content": content.strip(),
            },
            on_conflict="telegram_id,kind",
        )
        .execute()
    )
    return _first(result) or {}


# Check-ins are intentionally not scheduled in the MVP, but the table exists
# for future reminders and simple analytics.


def save_checkin(telegram_id: int, question: str, answer: str = "") -> dict:
    result = (
        get_db()
        .table("checkins")
        .insert(
            {
                "telegram_id": telegram_id,
                "question": question.strip(),
                "answer": answer.strip() or None,
            }
        )
        .execute()
    )
    return _first(result) or {}
