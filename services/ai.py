"""
Groq prompts for Qaiyrat.

The MVP uses the LLM for one job: a short comeback response that turns a slip
into one concrete 5-15 minute action.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from groq import Groq

MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

_client: Optional[Groq] = None


SAFETY_MESSAGE = (
    "Сейчас это не задача для коучинга.\n\n"
    "Если есть риск, что ты навредишь себе или кому-то, пожалуйста, прямо сейчас "
    "обратись в экстренные службы, к близкому человеку рядом или на местную "
    "кризисную линию. Qaiyrat не заменяет профессиональную помощь и не должен "
    "вести тебя через кризис в одиночку."
)

CRISIS_PATTERNS = [
    r"суицид",
    r"самоуб",
    r"покончить с собой",
    r"убить себя",
    r"не хочу жить",
    r"причинить себе вред",
    r"self[- ]?harm",
    r"suicide",
    r"kill myself",
    r"abuse",
    r"насили",
    r"избива",
]


def get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY must be set in .env")
        _client = Groq(api_key=api_key)
    return _client


def contains_crisis_language(text: str) -> bool:
    value = (text or "").lower()
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in CRISIS_PATTERNS)


def _compact_list(items: list[dict], field: str = "text", limit: int = 5) -> list[str]:
    return [str(item.get(field, "")).strip() for item in items[:limit] if item.get(field)]


def _fallback_action(user_profile: dict, active_tasks: list[dict]) -> str:
    if active_tasks:
        return active_tasks[0].get("text", "").strip()

    goal = (user_profile.get("goal") or {}).get("title") or "свою цель"
    return f"открой заметки по цели «{goal}» и напиши 3 строки плана следующего шага"


def fallback_comeback_response(
    user_profile: dict,
    active_tasks: list[dict],
    trigger: dict,
) -> dict:
    goal = user_profile.get("goal") or {}
    profile = user_profile.get("profile") or {}
    action = _fallback_action(user_profile, active_tasks)

    goal_title = goal.get("title") or "твоя цель"
    why = goal.get("why") or "ты сам выбрал это как важное"
    blocker = trigger.get("blocker") or profile.get("blocker_pattern") or "срыв ритма"

    message = (
        f"Ты выпал, и сейчас сильнее всего мешает: {blocker}. Это неприятно, но это не финал.\n\n"
        f"Цель всё ещё та же: {goal_title}. Причина тоже не исчезла: {why}.\n\n"
        f"Сейчас не надо возвращаться идеально. Сделай только это: {action}. "
        "Готов взять это на 10 минут?"
    )
    return {"message": message, "next_action": action, "source": "fallback"}


def _extract_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _coerce_ai_payload(raw: str, fallback: dict) -> dict:
    try:
        data = _extract_json_object(raw)
    except Exception:
        return fallback

    message = str(data.get("message") or "").strip()
    action = str(data.get("next_action") or "").strip()

    if not message or not action:
        return fallback

    return {"message": message, "next_action": action, "source": "groq"}


def generate_comeback_response(
    user_profile: dict,
    recent_wins: list[dict],
    active_tasks: list[dict],
    trigger: dict,
    tone: str,
) -> dict:
    """
    Generate a compact comeback response.

    Returns:
        {
          "message": user-facing response ending with a commitment question,
          "next_action": one task text to create if the user agrees,
          "source": "groq" | "fallback",
          "error": optional error string
        }
    """

    fallback = fallback_comeback_response(user_profile, active_tasks, trigger)

    crisis_text = " ".join(str(v) for v in trigger.values())
    if contains_crisis_language(crisis_text):
        return {"message": SAFETY_MESSAGE, "next_action": "", "source": "safety"}

    goal = user_profile.get("goal") or {}
    profile = user_profile.get("profile") or {}
    vision_items = user_profile.get("vision_items") or []

    context = {
        "goal": {
            "title": goal.get("title", ""),
            "deadline": goal.get("deadline", ""),
            "why": goal.get("why", ""),
        },
        "profile": {
            "blocker_pattern": profile.get("blocker_pattern", ""),
            "support_tone": tone or profile.get("support_tone", ""),
        },
        "recent_wins": _compact_list(recent_wins, limit=5),
        "active_tasks": _compact_list(active_tasks, limit=5),
        "vision_items": [
            {"kind": item.get("kind", ""), "content": item.get("content", "")}
            for item in vision_items[:3]
        ],
        "current_trigger": {
            "what_happened": trigger.get("reason", ""),
            "days_slipped": trigger.get("days_slipped", ""),
            "current_blocker": trigger.get("blocker", ""),
        },
    }

    system_prompt = """
Ты — Qaiyrat, AI accountability coach / comeback coach.

Ты НЕ психолог, НЕ терапевт, НЕ врач и НЕ замена профессиональной помощи.
Твоя работа: быстро вернуть человека к одному маленькому действию, когда он
стыдится, ленится, устал, выпал или близок к тому чтобы бросить цель.

Стиль:
- прямой, уважительный, без длинных лекций
- не диагноз, не терапия, не мотивационная цитата
- используй личную цель, deadline, why, победы и текущие задачи
- нормализуй срыв, но не делай из него оправдание
- дай ровно одно действие на 5-15 минут
- закончи вопросом на commitment

Структура сообщения:
1. короткое отражение состояния
2. напоминание цели и why
3. честный reframe
4. один маленький next action
5. вопрос: готов ли взять это на 10-15 минут

Избегай:
- "ты справишься" как шаблон
- fake therapy language
- диагнозов
- чувства вины или стыда
- нескольких вариантов

Верни только валидный JSON без markdown:
{
  "message": "короткий ответ на русском",
  "next_action": "конкретная задача на 5-15 минут"
}
"""

    try:
        response = get_client().chat.completions.create(
            model=MODEL,
            max_tokens=450,
            temperature=0.4,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(context, ensure_ascii=False),
                },
            ],
        )
        raw = response.choices[0].message.content or ""
        return _coerce_ai_payload(raw, fallback)
    except Exception as exc:
        fallback["error"] = f"{exc.__class__.__name__}: {exc}"
        return fallback
