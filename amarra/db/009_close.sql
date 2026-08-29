-- ═══════════════════════════════════════════════════════════════════════════
-- AMARRA · migração 009 — ENCERRAMENTO E DOSSIÊ
--
-- Terminal. A guarda de `closed` já existia (recap enviado); aqui a operação
-- ganha `closed_at` / `outcome`, e nasce a tabela `dossiers` — o artefato
-- auditável do R4 no nível da operação.
--
-- Tudo no dossiê é DERIVADO. Nenhum número é escrito à mão: durações vêm
-- de phase_events, o financeiro do mandato + compromisso confirmado, a
-- folga do relógio da fase 1.
--
-- Aplicar no SQL Editor do Supabase, depois de 008_evidence.sql.
-- ═══════════════════════════════════════════════════════════════════════════

alter table operations
  add column if not exists closed_at timestamptz,
  add column if not exists outcome   text;   -- booked | failed | aborted

create table if not exists dossiers (
  operation_id uuid primary key references operations(id) on delete cascade,
  outcome      text not null,
  financial    jsonb not null default '{}',
  operational  jsonb not null default '{}',
  timeline     jsonb not null default '[]',
  commitments  jsonb not null default '[]',
  comparison   jsonb not null default '[]',
  escalations  jsonb not null default '[]',
  mandate_hash text,
  headline     text,
  created_at   timestamptz default now()
);

alter publication supabase_realtime add table dossiers;
alter table dossiers enable row level security;
create policy anon_read on dossiers for select to anon using (true);
