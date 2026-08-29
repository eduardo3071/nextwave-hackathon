-- ═══════════════════════════════════════════════════════════════════════════
-- AMARRA · migração 002 — AS FASES
--
-- O que faltava: a operação tinha estados espalhados (operations.status,
-- auctions.status, calls.status) mas nenhum eixo único do início ao fim.
-- Sem isso o painel não conta uma história e o júri não sabe onde estamos.
--
-- Duas peças:
--   operations.phase   → onde estamos AGORA
--   phase_events       → append-only, é a linha do tempo que o painel desenha
--
-- Aplicar no SQL Editor do Supabase, depois de schema.sql.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── a espinha e os desvios ─────────────────────────────────────────────────
do $$ begin
  create type phase_key as enum (
    -- espinha: sempre nesta ordem
    'detected',        -- 1 contêiner descarregado, relógio do free time começa
    'mandate_issued',  -- 2 mandato emitido como DADO
    'market_open',     -- 3 chamadas discando em paralelo
    'negotiating',     -- 4 cotações vivas, cruzando entre as chamadas
    'reserved',        -- 5 lock tomado: uma e só uma pode fechar
    'committed',       -- 6 acordo dito e confirmado com a contraparte
    'verified',        -- 7 evidência ancorada no áudio + recap enviado
    'closed',          -- 8 operação encerrada
    -- desvios: interrompem a espinha e voltam para ela
    'disrupted',       -- chegou problema (caminhão quebrou)
    'renegotiating',   -- agente ligando de volta para mover o combinado
    'escalated',       -- humano na linha, decisão excede o mandato
    'resolved',        -- humano decidiu, volta para a espinha
    -- terminal ruim
    'failed'           -- nenhuma opção dentro do mandato e ninguém resolveu
  );
exception when duplicate_object then null; end $$;

alter table operations
  add column if not exists phase phase_key not null default 'detected',
  add column if not exists phase_since timestamptz not null default now();

-- ── linha do tempo append-only ─────────────────────────────────────────────
create table if not exists phase_events (
  id           bigserial primary key,
  operation_id uuid not null references operations(id) on delete cascade,
  phase        phase_key not null,
  previous     phase_key,
  kind         text not null,          -- spine | branch | terminal
  trigger      text not null,          -- o que causou (evento, não narrativa)
  detail       text,                   -- uma linha legível para o painel
  call_id      uuid references calls(id) on delete set null,
  auction_id   uuid references auctions(id) on delete set null,
  payload      jsonb default '{}',     -- a conta da escalação, a comparação, etc.
  ms_in_previous int,                  -- quanto tempo ficamos na fase anterior
  created_at   timestamptz default now()
);

create index if not exists phase_events_op_idx on phase_events (operation_id, id);

-- ── transição atômica: grava o evento E move a operação ────────────────────
create or replace function advance_phase(
  p_operation_id uuid,
  p_phase        phase_key,
  p_kind         text,
  p_trigger      text,
  p_detail       text default null,
  p_call_id      uuid  default null,
  p_auction_id   uuid  default null,
  p_payload      jsonb default '{}'
) returns bigint
language plpgsql as $$
declare
  v_prev  phase_key;
  v_since timestamptz;
  v_id    bigint;
begin
  select phase, phase_since into v_prev, v_since
  from operations where id = p_operation_id for update;

  -- idempotente: reentrar na mesma fase não polui a linha do tempo
  if v_prev = p_phase then
    return null;
  end if;

  insert into phase_events (operation_id, phase, previous, kind, trigger, detail,
                            call_id, auction_id, payload, ms_in_previous)
  values (p_operation_id, p_phase, v_prev, p_kind, p_trigger, p_detail,
          p_call_id, p_auction_id, p_payload,
          extract(epoch from (now() - v_since)) * 1000)
  returning id into v_id;

  -- desvio não apaga onde a espinha estava; quem controla isso é o Python
  update operations
     set phase = p_phase, phase_since = now(),
         status = case
           when p_phase = 'closed'  then 'closed'
           when p_phase = 'failed'  then 'failed'
           when p_phase in ('committed','verified') then 'booked'
           when p_phase = 'escalated' then 'escalated'
           else 'open' end
   where id = p_operation_id;

  return v_id;
end $$;

alter publication supabase_realtime add table phase_events;

-- ── o que o painel lê para desenhar a barra de progresso ───────────────────
create or replace view operation_progress as
select
  o.id, o.ref, o.phase, o.phase_since,
  case o.phase
    when 'detected' then 1 when 'mandate_issued' then 2
    when 'market_open' then 3 when 'negotiating' then 4
    when 'reserved' then 5 when 'committed' then 6
    when 'verified' then 7 when 'closed' then 8
    else null end                                    as spine_step,
  o.phase in ('disrupted','renegotiating','escalated','resolved') as on_branch,
  (select count(*) from phase_events e where e.operation_id = o.id) as steps_taken,
  (select max(created_at) from phase_events e where e.operation_id = o.id) as last_event_at
from operations o;

grant select on operation_progress to anon;
