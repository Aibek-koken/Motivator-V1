-- AnchorAI — SQL схема для Supabase
-- Запусти это в Supabase → SQL Editor

-- Профиль пользователя
create table if not exists profiles (
  id          bigserial primary key,
  telegram_id bigint unique not null,
  name        text,
  goal        text,          -- Чего хочет
  why         text,          -- Почему важно
  victory     text,          -- Первая победа из онбординга
  image       text,          -- file_id фото или текстовое описание
  image_type  text default 'none', -- 'photo' | 'text' | 'none'
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

-- Архив побед (Cookie Jar по Гоггинсу)
create table if not exists victories (
  id          bigserial primary key,
  telegram_id bigint not null references profiles(telegram_id) on delete cascade,
  text        text not null,
  created_at  timestamptz default now()
);

-- Индексы для быстрого поиска
create index if not exists idx_profiles_telegram_id on profiles(telegram_id);
create index if not exists idx_victories_telegram_id on victories(telegram_id);

-- Row Level Security (опционально, если нужна защита)
-- alter table profiles enable row level security;
-- alter table victories enable row level security;
