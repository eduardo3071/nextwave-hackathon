-- ═══════════════════════════════════════════════════════════════════════════
-- AMARRA · migração 007 — COMPROMETIDO
--
-- A contraparte concordou em voz alta e confirmou. É a primeira metade do
-- "verified twice" do enunciado — a segunda é a âncora de áudio da fase 7.
--
-- Duas mudanças estruturais:
--   commitments.t_start_ms / t_end_ms perdem NOT NULL — ancorar é da fase 7
--   commitments ganha read_back_token, affirmation_quote, confirmed_at
--   read_backs é uma tabela nova de auditoria: cada tentativa vira linha
--
-- Aplicar no SQL Editor do Supabase, depois de 006_reserve.sql.
-- ═══════════════════════════════════════════════════════════════════════════

alter table commitments
  add column if not exists read_back_token     text,
  add column if not exists read_back_at        timestamptz,
  add column if not exists confirmed_at        timestamptz,
  add column if not exists affirmation_quote   text,
  add column if not exists affirmation_t_start_ms int,
  add column if not exists affirmation_t_end_ms   int,
  add column if not exists negotiation_round   int;

-- a âncora de áudio chega na fase 7; até lá o compromisso vive sem ela
alter table commitments alter column t_start_ms drop not null;
alter table commitments alter column t_end_ms   drop not null;
alter table commitments drop constraint if exists anchored;
alter table commitments add constraint anchored_when_present check (
  (t_start_ms is null and t_end_ms is null)
  or (t_start_ms >= 0 and t_end_ms >= t_start_ms)
);

create table if not exists read_backs (
  id            bigserial primary key,
  call_id       uuid not null references calls(id) on delete cascade,
  operation_id  uuid not null references operations(id) on delete cascade,
  token         text not null,
  slots         jsonb not null,
  spoken_text   text not null,
  response_text text,
  outcome       text,     -- confirmed | rejected | ambiguous | timeout | superseded
  attempt       int not null default 1,
  t_spoken_ms   int,
  t_response_ms int,
  created_at    timestamptz default now()
);

create index if not exists read_backs_call_idx on read_backs (call_id, id);
alter publication supabase_realtime add table read_backs;
alter table read_backs enable row level security;
create policy anon_read on read_backs for select to anon using (true);
