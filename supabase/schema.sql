-- Gundam Card Game — Supabase schema
-- Run this in the Supabase SQL editor (or via `supabase db execute`)
-- to create the `cards` table used by the proxy/scraper backend.

-- Enable pgcrypto for gen_random_uuid() (used only if you ever want
-- to insert rows without a serial number of your own).
create extension if not exists "pgcrypto";

create table if not exists public.cards (
    -- Primary key is the card's serial / card number (e.g. "ST01-001").
    -- Using text keeps it human-readable and makes upserts trivial.
    id              text primary key,

    card_name       text        not null,
    card_number     text        not null,
    type            text,                   -- Unit, Command, Pilot, Base, Resource...
    color           text,                   -- Blue, Green, Red, White...
    text_data       jsonb       not null default '{}'::jsonb, -- rules text, stats, keywords, etc.

    image_url       text,                   -- our storage URL (Supabase Storage / CDN / local path)
    raw_bandai_url  text,                   -- the source page we scraped

    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),

    constraint cards_card_number_unique unique (card_number)
);

-- Helpful indexes for the common filters in a deckbuilder UI.
create index if not exists cards_type_idx   on public.cards (type);
create index if not exists cards_color_idx  on public.cards (color);
create index if not exists cards_name_trgm  on public.cards using gin (card_name gin_trgm_ops);

-- Required for the trigram index above (safe no-op if already enabled).
create extension if not exists pg_trgm;

-- Keep updated_at honest.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

drop trigger if exists cards_set_updated_at on public.cards;
create trigger cards_set_updated_at
    before update on public.cards
    for each row
    execute function public.set_updated_at();

-- Row-Level Security: the backend uses the SERVICE ROLE key, which bypasses
-- RLS, so we can safely lock the table down to "read-only for everyone else".
alter table public.cards enable row level security;

drop policy if exists "Cards are readable by anyone" on public.cards;
create policy "Cards are readable by anyone"
    on public.cards
    for select
    using (true);

-- No insert/update/delete policies are defined on purpose — writes must go
-- through the backend (service role). Do NOT expose the service role key
-- to the browser.

-- ---------------------------------------------------------------------------
-- Storage bucket for re-hosted card images.
--
-- Bandai's CDN 403s cross-origin image requests, so the backend downloads
-- each image server-side and uploads it into this bucket. The bucket is
-- PUBLIC so the frontend can render <img src="…"> straight from the
-- Supabase CDN. Writes still require the service role (the backend).
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('card-images', 'card-images', true)
on conflict (id) do update set public = excluded.public;

