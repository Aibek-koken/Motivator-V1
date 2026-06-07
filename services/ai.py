"""
services/ai.py — генерация ответов через Groq API.
Три типа ответов: SOS, ежедневный вопрос, команда /anchor.
"""

import os
from groq import Groq
from typing import Optional

_client = None


def get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY не задан в .env")
        _client = Groq(api_key=api_key)
    return _client


MODEL = "llama-3.3-70b-versatile"  # Лучший бесплатный Groq-моделей


# ──────────────────────────────────────────────
# SOS-ответ
# ──────────────────────────────────────────────

SOS_SYSTEM = """Ты — личный наставник пользователя. Твоя задача: когда человек говорит что хочет всё бросить или ему плохо — вернуть его к его настоящей цели.

Строго следуй этой формуле из 4 частей:
1. ПРИНЯТЬ — 1-2 предложения. Мягко признай что ему сейчас тяжело. Без "ты молодец". Можно сказать что такое бывает у всех кто идёт к чему-то большому.
2. НОРМАЛИЗОВАТЬ — 1 предложение. Трудность — это не признак провала, это часть пути.
3. ЯКОРЬ — используй конкретные слова пользователя из его профиля. Напомни ему его цель его же словами. Напомни его победу. Будь конкретным — не "ты сильный", а "ты однажды [конкретный факт из профиля]".
4. ДЕЙСТВИЕ — одно простое физическое действие на ближайшие 5 минут. Не "работай", а "умой лицо и напиши мне одно слово — что будешь делать".

ЗАПРЕЩЕНО использовать: "ты молодец", "верь в себя", "всё получится", "вселенная", "позитивный настрой", "не сдавайся" (без конкретики).

Пиши коротко. Максимум 5-6 предложений. Тон: тёплый но честный, как старший друг. Говори на "ты"."""


def generate_sos_response(profile: dict, victory: Optional[str]) -> str:
    client = get_client()

    user_context = f"""Профиль пользователя:
- Цель: {profile.get('goal', 'не указана')}
- Почему это важно: {profile.get('why', 'не указано')}
- Его победа из прошлого: {victory or profile.get('victory', 'не указана')}
- Имя (если есть): {profile.get('name', '')}

Пользователь написал что ему плохо или хочет бросить. Ответь по формуле."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=400,
        messages=[
            {"role": "system", "content": SOS_SYSTEM},
            {"role": "user",   "content": user_context},
        ],
    )
    return response.choices[0].message.content


# ──────────────────────────────────────────────
# Ежедневный вопрос
# ──────────────────────────────────────────────

DAILY_SYSTEM = """Ты — наставник который раз в несколько дней задаёт один вопрос чтобы пополнить архив побед пользователя.

Вопрос должен:
- Быть коротким (1 предложение)
- Помогать пользователю вспомнить маленькую победу или момент силы сегодня
- Не давить и не требовать — это не отчёт, это приглашение

Примеры хороших вопросов:
- "Было сегодня что-то — даже маленькое — что ты сделал несмотря на то что не хотелось?"
- "Вспомни один момент сегодня когда ты мог сдаться но не сдался. Что это было?"
- "Что сегодня ты сделал ради своей цели — даже если это был маленький шаг?"

Пиши разные вопросы каждый раз. Тон: дружеский, без давления."""


def generate_daily_question(profile: dict) -> str:
    client = get_client()

    context = f"Цель пользователя: {profile.get('goal', 'большая цель')}. Придумай один вопрос для вечернего чек-ина."

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=150,
        messages=[
            {"role": "system", "content": DAILY_SYSTEM},
            {"role": "user",   "content": context},
        ],
    )
    return response.choices[0].message.content


# ──────────────────────────────────────────────
# Ответ на /anchor
# ──────────────────────────────────────────────

ANCHOR_SYSTEM = """Ты — наставник. Пользователь попросил напомнить ему его якорь — его главную цель и почему она важна.

Ответь коротко (3-4 предложения):
1. Напомни его цель его же словами
2. Напомни почему это важно — снова его словами
3. Если есть победа из архива — упомяни её как доказательство что он может
4. Один короткий призыв — продолжай

Тон: тёплый, как напоминание от человека который в тебя верит."""


def generate_anchor_response(profile: dict, victory: Optional[str]) -> str:
    client = get_client()

    context = f"""Профиль:
- Цель: {profile.get('goal', 'не указана')}
- Почему важно: {profile.get('why', 'не указано')}
- Победа из архива: {victory or profile.get('victory', 'не указана')}

Пользователь попросил свой якорь."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=250,
        messages=[
            {"role": "system", "content": ANCHOR_SYSTEM},
            {"role": "user",   "content": context},
        ],
    )
    return response.choices[0].message.content
# ──────────────────────────────────────────────
# /future — проектирование будущего (заглушка)
# ──────────────────────────────────────────────

FUTURE_QUESTIONS = [
    {
        "step": 1,
        "field": "dream",
        "question": "🌅 <b>О чём ты мечтаешь?</b>\n\nЕсли бы у тебя было достаточно денег, времени и не было страха — что бы ты хотел создать, изменить или пережить в своей жизни?",
        "next_step": 2
    },
    {
        "step": 2,
        "field": "dream_why",
        "question": "💭 <b>Почему это так важно для тебя?</b>\n\nЧто стоит за этой мечтой? Какие чувства или смыслы она даёт?",
        "next_step": 3
    },
    {
        "step": 3,
        "field": "values",
        "question": "⭐ <b>Какие ценности для тебя главные?</b>\n\nНапример: свобода, семья, честность, развитие, здоровье, признание. Напиши несколько через запятую.",
        "next_step": 4,
        "parse_list": True
    },
    {
        "step": 4,
        "field": "fears",
        "question": "😟 <b>Чего ты боишься?</b>\n\nЧто может помешать тебе на пути к мечте? Какие страхи тебя останавливают?",
        "next_step": 5,
        "parse_list": True
    },
    {
        "step": 5,
        "field": "people",
        "question": "👥 <b>Кто тебя поддерживает или для кого это важно?</b>\n\nНазови людей, которые верят в тебя, или тех, на кого ты хочешь повлиять. Например: «мама — хочу её обеспечить», «друг Азамат — верит в мой стартап».",
        "next_step": 6,
        "parse_people": True
    },
    {
        "step": 6,
        "field": "energy_sources",
        "question": "⚡ <b>Что тебя заряжает энергией?</b>\n\nЭто могут быть места, музыка, книги, занятия, фильмы. Напиши несколько вещей, которые дают тебе силы.",
        "next_step": 7,
        "parse_list": True
    },
    {
        "step": 7,
        "field": "favorite_tracks",
        "question": "🎵 <b>Назови одну песню или трек, который даёт тебе крылья.</b>\n\nНапиши название и исполнителя. Почему именно она?",
        "next_step": 8,
        "parse_track": True
    },
    {
        "step": 8,
        "field": "anchor_phrase",
        "question": "⚓ <b>Придумай личную фразу-якорь.</b>\n\nКороткую фразу, которая вернёт тебя к твоей цели в трудный момент. Например: «Я делаю это ради мамы» или «Однажды я уже справился — смогу и сейчас».",
        "next_step": None,
        "is_last": True
    }
]

def get_next_future_question(step: int, last_answer: str = None) -> dict:
    """
    Возвращает следующий вопрос или сигнал завершения.
    step: номер только что отвеченного шага (или 0 для первого).
    """
    if step == 0:
        q = FUTURE_QUESTIONS[0]
        return {
            "question": q["question"],
            "field": q["field"],
            "next_step": q["step"],
            "is_last": False,
            "step": q["step"]
        }
    # Ищем текущий шаг
    for i, q in enumerate(FUTURE_QUESTIONS):
        if q["step"] == step:
            if q.get("is_last"):
                return {"is_complete": True}
            next_q = FUTURE_QUESTIONS[i+1] if i+1 < len(FUTURE_QUESTIONS) else None
            if next_q:
                return {
                    "question": next_q["question"],
                    "field": next_q["field"],
                    "next_step": next_q["step"],
                    "is_last": next_q.get("is_last", False),
                    "step": next_q["step"]
                }
            else:
                return {"is_complete": True}
    # Не найден — начинаем сначала
    return get_next_future_question(0)

def parse_future_answer(field: str, answer: str) -> dict:
    """Преобразует ответ в формат для обновления future_profile."""
    answer = answer.strip()
    if field in ("values", "fears", "energy_sources"):
        items = [i.strip() for i in answer.split(",") if i.strip()]
        return {field: items}
    elif field == "people":
        people_list = []
        for line in answer.split("\n"):
            if " — " in line:
                name, role = line.split(" — ", 1)
            elif " - " in line:
                name, role = line.split(" - ", 1)
            elif "," in line:
                name, role = line.split(",", 1)
            else:
                name, role = line, "поддержка"
            people_list.append({"name": name.strip(), "role": role.strip()})
        return {"people": people_list}
    elif field == "favorite_tracks":
        track = {}
        if " - " in answer:
            title, artist = answer.split(" - ", 1)
        elif "," in answer:
            title, artist = answer.split(",", 1)
        else:
            title, artist = answer, "неизвестен"
        track["title"] = title.strip()
        track["artist"] = artist.strip()
        track["why"] = ""
        return {"favorite_tracks": [track]}
    else:
        return {field: answer}
    

    # ──────────────────────────────────────────────
# Психолог-мотиватор (/psycho)
# ──────────────────────────────────────────────

PSYCHO_SYSTEM = """Ты — психолог-мотиватор с глубокими знаниями психологии и нейробиологии. Твоя задача — помочь пользователю выйти из слабого, разбитого состояния, вернуть ему энергию и веру в себя.

ПРАВИЛА:
1. Используй контекст из профиля пользователя (его мечту, ценности, страхи, любимые треки, фразу-якорь). Обращайся к ним, чтобы напомнить, зачем ему всё это.
2. Будь эмпатичным, но не сюсюкай. Иногда нужна твёрдость и прямота. Сочетай поддержку с вызовом.
3. Задавай вопросы, которые заставляют задуматься: «Что ты можешь сделать прямо сейчас, чтобы почувствовать себя лучше?», «Какая маленькая победа была у тебя сегодня?».
4. Если пользователь говорит, что хочет всё бросить — примени технику якоря (верни к его мечте и прошлым победам).
5. Пиши короткими абзацами. Максимум 4-5 предложений за раз. Говори на «ты».
6. Не используй шаблонные фразы: «ты молодец», «всё будет хорошо», «верь в себя» (без конкретики).

Твой тон — как у заботливого, но требовательного наставника, который видит потенциал человека и не даёт ему сдаваться."""

def generate_psycho_response(profile: dict, history: list, user_message: str, victory: str = None) -> str:
    """
    Генерирует ответ психолога на основе профиля пользователя, истории диалога и последнего сообщения.
    profile: словарь future_profile (dream, dream_why, values, fears, anchor_phrase, favorite_tracks и т.д.)
    history: список предыдущих сообщений {role: user/assistant, content}
    user_message: текущее сообщение пользователя
    victory: случайная победа из архива (если есть)
    """
    client = get_client()
    
    # Формируем контекст из профиля
    profile_context = f"""
    Мечта: {profile.get('dream', 'не указана')}
    Почему важно: {profile.get('dream_why', 'не указано')}
    Ценности: {', '.join(profile.get('values', []))}
    Страхи: {', '.join(profile.get('fears', []))}
    Фраза-якорь: {profile.get('anchor_phrase', '—')}
    Любимые треки: {', '.join([t.get('title', '') for t in profile.get('favorite_tracks', [])])}
    Победа из архива: {victory if victory else '—'}
    """
    
    # Формируем историю для Groq (последние 10 сообщений)
    messages = [{"role": "system", "content": PSYCHO_SYSTEM + "\n\nКонтекст пользователя:\n" + profile_context}]
    # Добавляем историю сессии (без системных)
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    # Добавляем текущее сообщение
    messages.append({"role": "user", "content": user_message})
    
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=500,
        messages=messages,
    )
    return response.choices[0].message.content