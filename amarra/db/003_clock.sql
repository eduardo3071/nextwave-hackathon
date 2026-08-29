-- ═══════════════════════════════════════════════════════════════════════════
-- AMARRA · migração 003 — O RELÓGIO
--
-- Fase 1 é a ORIGEM: a operação nasce em 'detected' e o cronômetro que
-- custa dinheiro começa a correr. Duas coisas nascem no banco:
--
--   operations.clock_state    → safe | warning | critical | expired | stopped
--   operations.idempotency_key → mesmo contêiner + mesma descarga = mesma op
--
-- O cronômetro em si é derivado no navegador a partir de free_time_ends,
-- mas o ESTADO do relógio precisa vir do banco para o Realtime empurrar a
-- mudança de cor e para existir trilha de auditoria de quando cruzamos
-- cada limiar.
--
-- Aplicar no SQL Editor do Supabase, depois de 002_phases.sql.
-- ═══════════════════════════════════════════════════════════════════════════

do $$ begin
  create type clock_state as enum ('safe','warning','critical','expired','stopped');
exception when duplicate_object then null; end $$;

alter table operations
  add column if not exists clock_state clock_state not null default 'safe',
  add column if not exists clock_state_since timestamptz not null default now(),
  add column if not exists source_event jsonb default '{}',
  add column if not exists idempotency_key text unique;

create index if not exists operations_clock_idx on operations (clock_state, free_time_ends);
