-- ============================================================
-- QAIYRAT BOT — Supabase Schema
-- Запусти в Supabase → SQL Editor → Run
-- ============================================================


-- ============================================================
-- 1. ПОЛЬЗОВАТЕЛИ
-- Создаётся при первом /start
-- ============================================================
create table if not exists users (
  id              bigserial primary key,
  telegram_id     bigint unique not null,
  username        text,
  first_name      text,
  language        text default 'ru',        -- 'ru' | 'kz' | 'en'
  in_psycho_mode  boolean default false,    -- флаг активной сессии /psycho
  in_future_mode  boolean default false,    -- флаг активного диалога /future
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

-- Автообновление updated_at
create or replace function touch_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

create trigger users_updated_at
  before update on users
  for each row execute procedure touch_updated_at();


-- ============================================================
-- 2. ПРОФИЛЬ БУДУЩЕГО (/future)
-- Заполняется AI-агентом через диалог
-- ============================================================
create table if not exists future_profile (
  id              bigserial primary key,
  telegram_id     bigint unique not null references users(telegram_id) on delete cascade,

  -- Что вытащил агент
  dream           text,                     -- главная мечта
  dream_why       text,                     -- почему важна
  values          text[],                   -- ценности: ['семья', 'свобода', ...]
  fears           text[],                   -- страхи: ['остаться бедным', ...]
  people          jsonb default '[]',       -- [{"name": "мама", "role": "обеспечить"}]
  energy_sources  text[],                   -- что заряжает: ['горы', 'музыка', ...]
  favorite_tracks jsonb default '[]',       -- [{"title": "...", "artist": "...", "why": "..."}]
  anchor_image    text,                     -- file_id фото или текстовый образ
  anchor_phrase   text,                     -- фраза-якорь от самого пользователя

  -- Сырой диалог (для контекста AI)
  dialog_history  jsonb default '[]',       -- [{role, content}, ...]
  is_complete     boolean default false,    -- завершил ли онбординг /future

  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

create trigger future_updated_at
  before update on future_profile
  for each row execute procedure touch_updated_at();


-- ============================================================
-- 3. ПАМЯТЬ ПРОШЛОГО (/memory)
-- Фото, тексты, заметки, ссылки
-- ============================================================
create table if not exists memories (
  id              bigserial primary key,
  telegram_id     bigint not null references users(telegram_id) on delete cascade,

  type            text not null check (type in ('photo', 'text', 'link', 'note', 'voice')),
  content         text not null,            -- file_id для фото/голоса, URL для ссылок, текст для остального
  caption         text,                     -- подпись пользователя
  tags            text[] default '{}',      -- ['мотивация', 'семья', ...] — добавит AI позже
  is_pinned       boolean default false,    -- закреплённые воспоминания показываются первыми

  created_at      timestamptz default now()
);

-- Для быстрого поиска по пользователю и типу
create index if not exists idx_memories_telegram_id on memories(telegram_id);
create index if not exists idx_memories_type on memories(telegram_id, type);
create index if not exists idx_memories_pinned on memories(telegram_id, is_pinned) where is_pinned = true;


-- ============================================================
-- 4. ЗАДАЧИ (/tasks)
-- С кнопками — поставить галочку, удалить
-- ============================================================
create table if not exists tasks (
  id              bigserial primary key,
  telegram_id     bigint not null references users(telegram_id) on delete cascade,

  text            text not null,
  is_done         boolean default false,
  done_at         timestamptz,              -- когда выполнена
  priority        smallint default 2 check (priority in (1, 2, 3)),
                                            -- 1=высокий 2=средний 3=низкий
  due_date        date,                     -- опциональный дедлайн
  message_id      bigint,                   -- id сообщения в Telegram (для редактирования)

  created_at      timestamptz default now()
);

create index if not exists idx_tasks_telegram_id on tasks(telegram_id);
create index if not exists idx_tasks_active on tasks(telegram_id, is_done) where is_done = false;


-- ============================================================
-- 5. АРХИВ ПОБЕД (Cookie Jar)
-- Пополняется через /memory и ежедневные вопросы
-- ============================================================
create table if not exists victories (
  id              bigserial primary key,
  telegram_id     bigint not null references users(telegram_id) on delete cascade,

  text            text not null,            -- описание победы
  source          text default 'manual'
                  check (source in ('manual', 'daily_checkin', 'psycho_session', 'future_dialog')),
  energy_level    smallint check (energy_level between 1 and 5),
                                            -- насколько заряжает (1-5), заполнит AI позже

  created_at      timestamptz default now()
);

create index if not exists idx_victories_telegram_id on victories(telegram_id);


-- ============================================================
-- 6. ПСИХО-СЕССИИ (/psycho)
-- Лог сессий с мотиватором
-- ============================================================
create table if not exists psycho_sessions (
  id              bigserial primary key,
  telegram_id     bigint not null references users(telegram_id) on delete cascade,

  dialog_history  jsonb default '[]',       -- [{role, content}, ...] текущей сессии
  message_count   int default 0,
  mood_before     smallint check (mood_before between 1 and 5),   -- оценка до (спросим)
  mood_after      smallint check (mood_after between 1 and 5),    -- оценка после
  started_at      timestamptz default now(),
  ended_at        timestamptz                -- null если сессия активна
);

create index if not exists idx_psycho_telegram_id on psycho_sessions(telegram_id);
create index if not exists idx_psycho_active on psycho_sessions(telegram_id, ended_at)
  where ended_at is null;


-- ============================================================
-- 7. DAILY CHECK-IN
-- Ежедневные вечерние вопросы
-- ============================================================
create table if not exists daily_checkins (
  id              bigserial primary key,
  telegram_id     bigint not null references users(telegram_id) on delete cascade,

  question        text not null,
  answer          text,                     -- null если не ответил
  answered_at     timestamptz,
  sent_at         timestamptz default now()
);

create index if not exists idx_checkins_telegram_id on daily_checkins(telegram_id);


-- ============================================================
-- ВСПОМОГАТЕЛЬНЫЕ ПРЕДСТАВЛЕНИЯ (Views)
-- Удобные выборки для бота
-- ============================================================

-- Активные задачи пользователя (не выполненные, сначала по приоритету)
create or replace view active_tasks as
  select * from tasks
  where is_done = false
  order by priority asc, created_at asc;

-- Последние 10 воспоминаний
create or replace view recent_memories as
  select * from memories
  order by is_pinned desc, created_at desc
  limit 10;

-- Случайная победа для SOS-режима (используется в /psycho)
create or replace view random_victory as
  select * from victories
  order by random()
  limit 1;


-- ============================================================
-- ТЕСТОВЫЕ ДАННЫЕ (удали перед продакшном)
-- Раскомментируй чтобы проверить схему
-- ============================================================

-- insert into users (telegram_id, first_name, username)
-- values (123456789, 'Куаныш', 'kuanys');

-- insert into future_profile (telegram_id, dream, dream_why, values, fears)
-- values (123456789,
--   'Купить маме дом и обеспечить семью',
--   'Мама многим жертвовала ради меня — я хочу чтобы она жила в покое',
--   array['семья', 'свобода', 'честность'],
--   array['остаться бедным', 'потерять доверие близких']
-- );

-- insert into memories (telegram_id, type, content, caption)
-- values (123456789, 'text', 'Сдал ЕНТ на 128 — лучший в школе', 'Это был мой пиковый момент');

-- insert into tasks (telegram_id, text, priority)
-- values
--   (123456789, 'Запустить Telegram-бота', 1),
--   (123456789, 'Поговорить с 10 людьми для кастдева', 2),
--   (123456789, 'Написать пост о боли на Reddit', 3);

-- insert into victories (telegram_id, text, source)
-- values (123456789, 'Решал задачи по математике в больнице с разбитым носом — и не сдался', 'manual');