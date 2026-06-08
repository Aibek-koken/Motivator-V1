"""
services/ai.py — генерация ответов через Groq API.

Функции:
  generate_psycho_onboarding_response — первое сообщение в сессии
  generate_psycho_response            — основной диалог психолога
  generate_vision_clarification       — уточняющий вопрос при добавлении мечты
  generate_vision_immersion           — текст погружения в доску будущего
  generate_sos_response               — SOS-формула
  generate_daily_question             — вечерний вопрос
  generate_anchor_response            — напоминание якоря
"""

import os
import random
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


MODEL = "llama-3.3-70b-versatile"


# ══════════════════════════════════════════════════════════════════
# ЦИТАТЫ — встроены в промпт, не отдельный вызов
# Логика: AI сам решает когда цитата уместна (не каждый раз)
# ══════════════════════════════════════════════════════════════════

QUOTES_CONTEXT = """
У тебя есть банк цитат и притч от реальных людей. Используй их редко и точно — только когда цитата
действительно попадает в момент. Не надо вставлять в каждое сообщение. Цитата должна звучать
как случайно подходящая мысль, а не как запрограммированная вставка.

Примеры (используй схожие по духу, не копируй дословно):
— «Когда ты думаешь что сдался — ты на 40% своих возможностей.» (Дэвид Гоггинс)
— «Боль временна. Сдаться — навсегда.» (Лэнс Армстронг)
— «Стать лучшей версией себя — это не подарок. Это борьба.» (Эрик Томас)
— «Ты не устал. Ты просто потерял смысл.» (Виктор Франкл)
— Притча о мастере и учителе: ученик жаловался что устал. Мастер налил воду в переполненный стакан.
  «Ты переполнен жалобами. Сначала вылей.»
— «Каждое утро две газели просыпаются в Африке. Одна знает: надо бежать быстрее льва.
   Лев знает: надо бежать быстрее газели. Неважно кто ты — когда встаёт солнце, надо бежать.»
— «Железо не лжёт. Мир вокруг может лгать — штанга никогда.» (Генри Роллинс)
— «Тяжело в учении — легко в бою.» (Суворов)
— «Человек может вынести почти всё — если знает зачем.» (Ницше / Франкл)
"""


# ══════════════════════════════════════════════════════════════════
# ПСИХОЛОГ — ПЕРВОЕ СООБЩЕНИЕ СЕССИИ
# ══════════════════════════════════════════════════════════════════

PSYCHO_ONBOARDING_SYSTEM = """Ты — психолог-мотиватор. Твой стиль: прямой, без лишних слов, с уважением к человеку.

Ты получаешь:
- Психологический профиль: паттерн стресса, что убивает энергию, как лучше помочь, ресурсную победу
- Профиль будущего: мечта, ценности, якорь (если заполнен)
- Триггер сессии: что сейчас происходит
- Намерение: что человек хочет от сессии
- Победу из архива (Cookie Jar)

Твоя задача — написать ПЕРВОЕ сообщение сессии (3-4 предложения):
1. Признай то что происходит — без сочувствия через силу
2. Задай один открытый вопрос который поведёт дальше
3. Адаптируй стиль под намерение: если хочет план — конкретика; если выговориться — пространство; если встряхнуться — прямо

ЗАПРЕЩЕНО: «ты молодец», «всё будет хорошо», «верь в себя», эмодзи в каждом предложении.
""" + QUOTES_CONTEXT


def generate_psycho_onboarding_response(
    psycho_profile: dict,
    future_profile: dict,
    trigger: str,
    intent: str,
    victory: Optional[str],
) -> str:
    client = get_client()

    stress_labels = {
        "pattern_freeze": "замолкает и уходит в себя",
        "pattern_fight":  "злится, может сорваться",
        "pattern_avoid":  "уходит в отвлечение (телефон, еда, сон)",
        "pattern_ruminate": "думает по кругу, не может остановиться",
    }
    kill_labels = {
        "kill_fear":   "страх не справиться",
        "kill_stuck":  "ощущение топтания на месте",
        "kill_people": "конфликты с людьми",
        "kill_chaos":  "слишком много всего сразу",
    }
    support_labels = {
        "support_talk":    "просто выговориться",
        "support_plan":    "получить конкретный план",
        "support_insight": "понять почему так происходит",
        "support_push":    "жёсткое слово чтобы встряхнуться",
    }

    stress = stress_labels.get(psycho_profile.get("stress_pattern", ""), "реагирует по-разному")
    killer = kill_labels.get(psycho_profile.get("energy_killer", ""), "разные вещи")
    support = support_labels.get(psycho_profile.get("support_type", ""), "разная поддержка")
    comeback = psycho_profile.get("comeback_resource", "")

    dream = future_profile.get("dream", "")
    anchor = future_profile.get("anchor_phrase", "")

    context = f"""Психологический профиль:
- Под стрессом: {stress}
- Что убивает энергию: {killer}
- Как лучше помочь: {support}
- Ресурсная победа: {comeback or "не указана"}

Профиль будущего:
- Мечта: {dream or "не заполнена"}
- Якорь: {anchor or "не заполнен"}
- Победа из архива: {victory or "нет"}

Сессия:
- Триггер: {trigger}
- Намерение: {intent}

Напиши первое сообщение сессии. Помни про стиль поддержки этого человека: {support}."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=400,
        messages=[
            {"role": "system", "content": PSYCHO_ONBOARDING_SYSTEM},
            {"role": "user", "content": context},
        ],
    )
    return response.choices[0].message.content


# ══════════════════════════════════════════════════════════════════
# ПСИХОЛОГ — ОСНОВНОЙ ДИАЛОГ
# ══════════════════════════════════════════════════════════════════

PSYCHO_SYSTEM = """Ты — психолог-мотиватор. Прямой, честный, эмпатичный — без театра.

ПРАВИЛА:
1. Используй профиль человека: его паттерн стресса, что его убивает, как ему лучше помогать.
   Если он хочет план — дай конкретику. Если выговориться — дай пространство.
   Если встряхнуться — говори прямо, без смягчений.
2. Используй его мечту, якорь, победы из архива — когда они реально в тему, не по шаблону.
3. Задавай вопросы которые двигают вперёд: «Что ты можешь сделать прямо сейчас?»,
   «Когда последний раз ты чувствовал что идёшь в правильном направлении?»
4. Если говорит что хочет бросить — якорная техника: возврат к мечте + конкретная победа.
5. Максимум 4-5 предложений за раз. Короткие абзацы.

НЕЛЬЗЯ: «ты молодец», «всё будет хорошо», «я понимаю тебя» (без конкретики), обещания.
""" + QUOTES_CONTEXT


def generate_psycho_response(
    psycho_profile: dict,
    future_profile: dict,
    history: list,
    user_message: str,
    victory: Optional[str],
    intent: str = "",
) -> str:
    client = get_client()

    stress_labels = {
        "pattern_freeze": "замолкает и уходит в себя",
        "pattern_fight":  "злится, может сорваться",
        "pattern_avoid":  "уходит в отвлечение",
        "pattern_ruminate": "думает по кругу",
    }
    support_labels = {
        "support_talk":    "просто выговориться — дай пространство, не торопи",
        "support_plan":    "хочет план — давай конкретику, шаги",
        "support_insight": "хочет понять себя — задавай глубокие вопросы",
        "support_push":    "хочет встряхнуться — говори прямо, без смягчений",
    }

    stress = stress_labels.get(psycho_profile.get("stress_pattern", ""), "")
    support = support_labels.get(psycho_profile.get("support_type", ""), intent)
    comeback = psycho_profile.get("comeback_resource", "")

    profile_ctx = f"""Профиль человека:
- Под стрессом: {stress}
- Как помогать: {support}
- Его личная победа-ресурс: {comeback or "—"}
- Мечта: {future_profile.get("dream", "—")}
- Якорь: {future_profile.get("anchor_phrase", "—")}
- Победа из архива: {victory or "—"}
- Намерение этой сессии: {intent or "—"}"""

    messages = [
        {"role": "system", "content": PSYCHO_SYSTEM + "\n\n" + profile_ctx}
    ]
    # История (последние 12 сообщений)
    for msg in history[-12:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=450,
        messages=messages,
    )
    return response.choices[0].message.content


# ══════════════════════════════════════════════════════════════════
# ВИЗУАЛИЗАТОР БУДУЩЕГО — ПОГРУЖЕНИЕ
# ══════════════════════════════════════════════════════════════════

VISION_IMMERSION_SYSTEM = """Ты пишешь короткий мотивирующий текст-погружение для человека который смотрит на свою доску будущего.

Стиль: живой, конкретный, без пафоса. Не пересказывай то что он написал — это он и так видит.
Твоя задача — создать ощущение реальности этого будущего. Говори в настоящем времени или будущем
как о чём-то очень конкретном.

Максимум 4-5 предложений. Заканчивай одним действием или вопросом.
Не используй: «визуализируй», «мечтай», «представь себе», «вселенная».
""" + QUOTES_CONTEXT


def generate_vision_immersion(items: list, future_profile: dict) -> str:
    """Генерирует текст погружения на основе элементов доски."""
    if not items:
        return ""

    client = get_client()

    items_text = "\n".join([
        f"- [{item.get('category', 'other')}] {item.get('content', '')}"
        for item in items
    ])

    dream = future_profile.get("dream", "")
    anchor = future_profile.get("anchor_phrase", "")

    context = f"""Элементы доски будущего:
{items_text}

Дополнительно:
- Мечта: {dream or "не заполнена"}
- Якорь: {anchor or "не заполнен"}

Напиши короткий текст погружения."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=300,
        messages=[
            {"role": "system", "content": VISION_IMMERSION_SYSTEM},
            {"role": "user", "content": context},
        ],
    )
    return response.choices[0].message.content


# ══════════════════════════════════════════════════════════════════
# SOS-ОТВЕТ
# ══════════════════════════════════════════════════════════════════

SOS_SYSTEM = """Ты — личный наставник. Когда человек говорит что хочет всё бросить — вернуть его к цели.

Формула из 4 частей:
1. ПРИНЯТЬ — 1-2 предложения. Признай что тяжело. Без «ты молодец».
2. НОРМАЛИЗОВАТЬ — 1 предложение. Трудность — часть пути, не провал.
3. ЯКОРЬ — используй конкретные слова из профиля. Напомни цель и победу его словами.
4. ДЕЙСТВИЕ — одно физическое действие на 5 минут. Не «работай» — а «умой лицо и напиши одно слово».

ЗАПРЕЩЕНО: «ты молодец», «верь в себя», «всё получится», «вселенная».
Максимум 5-6 предложений. Говори на «ты».""" + QUOTES_CONTEXT


def generate_sos_response(profile: dict, victory: Optional[str]) -> str:
    client = get_client()
    context = f"""Профиль пользователя:
- Цель: {profile.get('goal', profile.get('dream', 'не указана'))}
- Почему важно: {profile.get('why', profile.get('dream_why', 'не указано'))}
- Его победа: {victory or profile.get('victory', 'не указана')}

Пользователю плохо / хочет бросить. Ответь по формуле."""

    response = client.chat.completions.create(
        model=MODEL, max_tokens=400,
        messages=[
            {"role": "system", "content": SOS_SYSTEM},
            {"role": "user", "content": context},
        ],
    )
    return response.choices[0].message.content


# ══════════════════════════════════════════════════════════════════
# ЕЖЕДНЕВНЫЙ ВОПРОС
# ══════════════════════════════════════════════════════════════════

DAILY_SYSTEM = """Ты — наставник который раз в день задаёт один вопрос чтобы пополнить архив побед.

Вопрос должен:
- Быть коротким (1 предложение)
- Помочь вспомнить маленькую победу или момент силы
- Не давить

Примеры: «Было сегодня что-то — даже маленькое — что ты сделал несмотря на то что не хотелось?»
Пиши разные каждый раз. Тон: дружеский, без давления."""


def generate_daily_question(profile: dict) -> str:
    client = get_client()
    context = f"Цель пользователя: {profile.get('dream', profile.get('goal', 'большая цель'))}. Придумай один вопрос."
    response = client.chat.completions.create(
        model=MODEL, max_tokens=150,
        messages=[
            {"role": "system", "content": DAILY_SYSTEM},
            {"role": "user", "content": context},
        ],
    )
    return response.choices[0].message.content


# ══════════════════════════════════════════════════════════════════
# ЯКОРЬ (/anchor)
# ══════════════════════════════════════════════════════════════════

ANCHOR_SYSTEM = """Ты — наставник. Пользователь просит напомнить якорь — его цель и почему она важна.

Ответь коротко (3-4 предложения):
1. Напомни цель его словами
2. Почему это важно — снова его словами
3. Если есть победа — упомяни как доказательство
4. Один призыв — продолжай

Тон: тёплый, как напоминание от человека который в тебя верит.""" + QUOTES_CONTEXT


def generate_anchor_response(profile: dict, victory: Optional[str]) -> str:
    client = get_client()
    context = f"""Профиль:
- Цель: {profile.get('goal', profile.get('dream', 'не указана'))}
- Почему важно: {profile.get('why', profile.get('dream_why', 'не указано'))}
- Победа: {victory or profile.get('victory', 'не указана')}
Пользователь попросил якорь."""

    response = client.chat.completions.create(
        model=MODEL, max_tokens=250,
        messages=[
            {"role": "system", "content": ANCHOR_SYSTEM},
            {"role": "user", "content": context},
        ],
    )
    return response.choices[0].message.content


# ══════════════════════════════════════════════════════════════════
# ЗАГЛУШКИ (оставлены для совместимости со старым кодом)
# ══════════════════════════════════════════════════════════════════

def generate_vision_clarification(category: str, future_profile: dict) -> str:
    """Не используется — вопросы теперь статические в handlers/future.py."""
    return ""


# Старый /future — оставлен для совместимости если где-то импортируется
FUTURE_QUESTIONS = []


def get_next_future_question(step: int, last_answer: str = None) -> dict:
    return {"is_complete": True}


def parse_future_answer(field: str, answer: str) -> dict:
    return {field: answer}