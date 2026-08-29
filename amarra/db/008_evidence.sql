-- ═══════════════════════════════════════════════════════════════════════════
-- AMARRA · migração 008 — EVIDÊNCIA ANCORADA
--
-- Pilar 02 no banco. Cada compromisso ganha:
--   anchor_state          → pending | anchored | not_found | low_confidence
--   anchor_confidence     → confiança da âncora
--   anchor_method         → exact | fuzzy | numeric (qual passada casou)
--   audio_url             → URL pública para o painel tocar o trecho
--
-- calls ganha transcrição indexada por palavra (o índice em que a fase 7 busca)
-- recap_deliveries registra cada envio de recap (R3a).
--
-- Aplicar no SQL Editor do Supabase, depois de 007_commit.sql.
-- ═══════════════════════════════════════════════════════════════════════════

alter table commitments
  add column if not exists anchor_state text not null default 'pending',
  -- pending | anchored | not_found | low_confidence
  add column if not exists anchor_confidence numeric,
  add column if not exists anchor_method text,          -- exact | fuzzy | numeric
  add column if not exists audio_url text;

alter table calls
  add column if not exists audio_public_url text,
  add column if not exists transcript jsonb,            -- índice de palavras
  add column if not exists transcript_words int;

create table if not exists recap_deliveries (
  id           bigserial primary key,
  operation_id uuid not null references operations(id) on delete cascade,
  call_id      uuid references calls(id) on delete set null,
  channel      text not null,              -- email | sms | whatsapp
  target       text not null,
  subject      text,
  body         text not null,
  provider_id  text,
  status       text not null default 'sent',
  error        text,
  created_at   timestamptz default now()
);

alter publication supabase_realtime add table recap_deliveries;
alter table recap_deliveries enable row level security;
create policy anon_read on recap_deliveries for select to anon using (true);
