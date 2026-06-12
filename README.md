# Qaiyrat — Telegram Accountability Coach

Qaiyrat is a focused Telegram MVP for ambitious students and junior IT people who are close to dropping a near-term goal.

It is not a psychologist or therapist. The bot acts as an AI accountability coach: when the user feels they are slipping, it helps them return to one small action in 3-5 minutes.

## Core Flow

1. User completes `/start` onboarding in under 2 minutes.
2. User presses `Я выпал`.
3. Qaiyrat asks what happened, how many days they stopped, and what blocks them now.
4. Groq generates one short comeback response with one 5-15 minute action.
5. If the user commits, Qaiyrat creates a task.
6. When the user marks it `Готово`, the task is completed and saved as a win.

## Commands And Buttons

- `/start` — create or reopen the Qaiyrat profile.
- `/help` — explain the bot and safety boundary.
- `/menu` — show the main menu.
- `/tasks` — list tasks. Use `/tasks текст задачи` to add one directly.
- `Я выпал` — start a comeback session.
- `Следующий шаг` — show the next active task or add one if the list is empty.
- `Добавить победу` — save a short win.
- `Мои задачи` — list active tasks.
- `Моя цель` — show the goal, deadline, why, blocker pattern, and tone.

## Stack

- Python 3.11+
- python-telegram-bot
- Supabase
- PostgreSQL through Supabase
- Groq API
- Long polling

## Setup

### 1. Create Credentials

Telegram:

- Open `@BotFather`
- Create a bot with `/newbot`
- Copy the Telegram token

Groq:

- Create an API key in the Groq console
- Copy the key into `GROQ_API_KEY`

Supabase:

- Create a Supabase project
- Open SQL Editor
- Run the full contents of `schema.sql`
- Copy Project URL and anon/service key into `.env`

### 2. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Fill:

```bash
TELEGRAM_BOT_TOKEN=
GROQ_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
```

Optional:

```bash
GROQ_MODEL=llama-3.3-70b-versatile
```

### 4. Run

```bash
python3 bot.py
```

## Project Structure

```text
bot.py                    # entrypoint and handler registration
schema.sql                # Supabase schema for the MVP
handlers/
  onboarding.py           # short /start onboarding
  comeback.py             # "Я выпал" comeback session
  tasks.py                # simple tasks
  wins.py                 # manual win capture
  menu.py                 # /help, /menu, goal summary
services/
  ai.py                   # Groq comeback prompt and fallback
  db.py                   # Supabase CRUD
```

Legacy memory, future-board, psycho, daily, and SOS handlers were removed from the active MVP surface.

## Safety Boundary

If the user mentions self-harm, suicide, abuse, or severe crisis, Qaiyrat stops coaching and shows a safety message that encourages contacting emergency services, a trusted person, or a local crisis line.

## Tests

```bash
python3 -m unittest discover -s tests
PYTHONPYCACHEPREFIX=/tmp/qaiyrat_pycache python3 -m compileall bot.py handlers services tests
```
