-- ============================================================
-- Qaiyrat MVP — Supabase schema
-- Telegram accountability coach for one goal and comeback sessions.
-- Run this in Supabase SQL Editor for a clean project.
-- ============================================================

create or replace function touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;


-- ============================================================
-- Users
-- ============================================================

create table if not exists users (
  id bigserial primary key,
  telegram_id bigint unique not null,
  username text,
  first_name text,
  language text default 'ru',
  onboarding_completed boolean not null default false,
  last_active_at timestamptz,
  comeback_session_count integer not null default 0,
  completed_task_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table users add column if not exists onboarding_completed boolean not null default false;
alter table users add column if not exists last_active_at timestamptz;
alter table users add column if not exists comeback_session_count integer not null default 0;
alter table users add column if not exists completed_task_count integer not null default 0;

drop trigger if exists users_touch_updated_at on users;
create trigger users_touch_updated_at
before update on users
for each row execute procedure touch_updated_at();


-- ============================================================
-- One active goal
-- ============================================================

create table if not exists goals (
  id bigserial primary key,
  telegram_id bigint not null references users(telegram_id) on delete cascade,
  title text not null,
  deadline text,
  why text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists idx_goals_one_active
on goals(telegram_id)
where is_active = true;

create index if not exists idx_goals_telegram_id on goals(telegram_id);

drop trigger if exists goals_touch_updated_at on goals;
create trigger goals_touch_updated_at
before update on goals
for each row execute procedure touch_updated_at();


-- ============================================================
-- Accountability profile
-- ============================================================

create table if not exists user_profiles (
  id bigserial primary key,
  telegram_id bigint unique not null references users(telegram_id) on delete cascade,
  blocker_pattern text,
  support_tone text not null default 'спокойно'
    check (support_tone in ('мягко', 'жёстко', 'по-братски', 'спокойно')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists user_profiles_touch_updated_at on user_profiles;
create trigger user_profiles_touch_updated_at
before update on user_profiles
for each row execute procedure touch_updated_at();


-- ============================================================
-- Tasks
-- Simple active/completed/deleted list. No priorities in the MVP.
-- ============================================================

create table if not exists tasks (
  id bigserial primary key,
  telegram_id bigint not null references users(telegram_id) on delete cascade,
  goal_id bigint references goals(id) on delete set null,
  comeback_session_id bigint,
  text text not null,
  status text not null default 'active'
    check (status in ('active', 'completed', 'deleted')),
  source text not null default 'manual'
    check (source in ('manual', 'onboarding', 'comeback')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  deleted_at timestamptz
);

-- Migration helpers for projects that already had the older tasks table.
alter table tasks add column if not exists goal_id bigint;
alter table tasks add column if not exists comeback_session_id bigint;
alter table tasks add column if not exists status text not null default 'active';
alter table tasks add column if not exists source text not null default 'manual';
alter table tasks add column if not exists updated_at timestamptz not null default now();
alter table tasks add column if not exists completed_at timestamptz;
alter table tasks add column if not exists deleted_at timestamptz;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_name = 'tasks' and column_name = 'is_done'
  ) then
    update tasks
    set
      status = case when is_done then 'completed' else 'active' end,
      completed_at = case
        when is_done then coalesce(completed_at, done_at, now())
        else completed_at
      end
    where status = 'active';
  end if;
end;
$$;

create index if not exists idx_tasks_active on tasks(telegram_id, created_at)
where status = 'active';
create index if not exists idx_tasks_goal on tasks(goal_id);
create index if not exists idx_tasks_comeback_session on tasks(comeback_session_id);

drop trigger if exists tasks_touch_updated_at on tasks;
create trigger tasks_touch_updated_at
before update on tasks
for each row execute procedure touch_updated_at();


-- ============================================================
-- Wins
-- A win is a short fact used in future comeback prompts.
-- ============================================================

create table if not exists wins (
  id bigserial primary key,
  telegram_id bigint not null references users(telegram_id) on delete cascade,
  goal_id bigint references goals(id) on delete set null,
  task_id bigint references tasks(id) on delete set null,
  text text not null,
  source text not null default 'manual'
    check (source in ('manual', 'task', 'comeback', 'onboarding', 'checkin')),
  happened_on date not null default current_date,
  created_at timestamptz not null default now()
);

create index if not exists idx_wins_telegram_id on wins(telegram_id, created_at desc);
create index if not exists idx_wins_goal on wins(goal_id);


-- ============================================================
-- Comeback sessions and compact messages
-- ============================================================

create table if not exists comeback_sessions (
  id bigserial primary key,
  telegram_id bigint not null references users(telegram_id) on delete cascade,
  goal_id bigint references goals(id) on delete set null,
  status text not null default 'active'
    check (status in ('active', 'proposed', 'committed', 'completed', 'cancelled', 'safety')),
  trigger_reason text,
  days_slipped text,
  blocker text,
  ai_response text,
  proposed_action text,
  task_id bigint references tasks(id) on delete set null,
  started_at timestamptz not null default now(),
  committed_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_comeback_sessions_user
on comeback_sessions(telegram_id, created_at desc);
create index if not exists idx_comeback_sessions_task on comeback_sessions(task_id);

drop trigger if exists comeback_sessions_touch_updated_at on comeback_sessions;
create trigger comeback_sessions_touch_updated_at
before update on comeback_sessions
for each row execute procedure touch_updated_at();


create table if not exists comeback_messages (
  id bigserial primary key,
  session_id bigint not null references comeback_sessions(id) on delete cascade,
  telegram_id bigint not null references users(telegram_id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_comeback_messages_session
on comeback_messages(session_id, created_at);


-- Add the optional FK after both tables exist.
do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'tasks_comeback_session_id_fkey'
  ) then
    alter table tasks
      add constraint tasks_comeback_session_id_fkey
      foreign key (comeback_session_id)
      references comeback_sessions(id)
      on delete set null;
  end if;
end;
$$;


-- ============================================================
-- Check-ins
-- Present for future reminders/analytics. Not scheduled in this MVP.
-- ============================================================

create table if not exists checkins (
  id bigserial primary key,
  telegram_id bigint not null references users(telegram_id) on delete cascade,
  question text not null,
  answer text,
  answered_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_checkins_telegram_id on checkins(telegram_id, created_at desc);


-- ============================================================
-- Minimal future context
-- Keep only three items for comeback prompts.
-- ============================================================

create table if not exists vision_items (
  id bigserial primary key,
  telegram_id bigint not null references users(telegram_id) on delete cascade,
  goal_id bigint references goals(id) on delete set null,
  kind text not null check (kind in ('desired_future', 'if_continue', 'if_quit')),
  content text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (telegram_id, kind)
);

create index if not exists idx_vision_items_telegram_id on vision_items(telegram_id);

drop trigger if exists vision_items_touch_updated_at on vision_items;
create trigger vision_items_touch_updated_at
before update on vision_items
for each row execute procedure touch_updated_at();


-- ============================================================
-- Useful views
-- ============================================================

create or replace view active_tasks as
select *
from tasks
where status = 'active'
order by created_at asc;

create or replace view recent_wins as
select *
from wins
order by created_at desc;
