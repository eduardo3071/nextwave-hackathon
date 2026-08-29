-- ═══════════════════════════════════════════════════════════════════════════
-- AMARRA · migração 005 — MERCADO ABERTO
--
-- A fase 3 é a única que depende do MUNDO FÍSICO: rede telefônica, limite
-- de chamadas simultâneas da conta Twilio, gente que não atende.
--
-- Duas coisas nascem aqui:
--   auctions.dial_plan / legs_planned / legs_budget → orçamento e admissão
--   auctions.soft_deadline_s / hard_deadline_s     → derivados do relógio
--   calls.leg_role                                 → counterparty | agent | human
--   calls.dial_attempt / dial_error                → reconciliação por perna
--
-- Aplicar no SQL Editor do Supabase, depois de 004_mandate.sql.
-- ═══════════════════════════════════════════════════════════════════════════

alter table auctions
  add column if not exists opened_at         timestamptz,
  add column if not exists dial_plan         jsonb default '[]',
  add column if not exists legs_planned      int,
  add column if not exists legs_budget       int,
  add column if not exists soft_deadline_s   int,
  add column if not exists hard_deadline_s   int,
  add column if not exists admission_warnings jsonb default '[]';

alter table calls
  add column if not exists leg_role     text,      -- counterparty | agent | human
  add column if not exists dial_attempt int default 1,
  add column if not exists dial_error   text,
  add column if not exists answered_at  timestamptz;

create index if not exists calls_leg_idx on calls (auction_id, leg_role, status);
