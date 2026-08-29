-- ═══════════════════════════════════════════════════════════════════════════
-- AMARRA · migração 004 — MANDATO EMITIDO
--
-- O mandato ganha identidade (hash canônico) e artefatos compilados:
--   · ladder            → escada de contra-ofertas determinística
--   · break_even_rate   → onde pagar mais passa a ser mais barato
--   · escalation_band   → faixa "bom e proibido"
--   · escalation_triggers → derivados, não escritos à mão
--   · issue_warnings    → avisos que o operador aceita explicitamente
--
-- policy_events e commitments passam a carregar `mandate_hash`, que responde
-- à pergunta do enunciado — "sob qual mandato" — para cada decisão e
-- compromisso.
--
-- Aplicar no SQL Editor do Supabase, depois de 003_clock.sql.
-- ═══════════════════════════════════════════════════════════════════════════

alter table mandates
  add column if not exists mandate_hash     text unique,
  add column if not exists canonical        jsonb,
  add column if not exists issued_at        timestamptz,
  add column if not exists ladder           jsonb default '[]',
  add column if not exists break_even_rate  numeric,
  add column if not exists escalation_band  jsonb,
  add column if not exists escalation_triggers jsonb default '[]',
  add column if not exists issue_warnings   jsonb default '[]';

-- "sob qual mandato" — R3
alter table policy_events add column if not exists mandate_hash text;
alter table commitments   add column if not exists mandate_hash text;

create index if not exists mandates_hash_idx on mandates (mandate_hash);
