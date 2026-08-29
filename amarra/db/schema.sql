-- ═══════════════════════════════════════════════════════════════════════════
-- AMARRA · schema Supabase
--
-- Este arquivo é O CONTRATO entre o backend Python e o frontend Lovable.
-- Escrevam ele PRIMEIRO. Enquanto ele não estiver aplicado, as duas metades
-- do time não conseguem trabalhar em paralelo.
--
-- Como aplicar: Supabase > SQL Editor > cola tudo > Run.
--
-- O truque que economiza horas: o backend NUNCA fala com o frontend.
-- O backend escreve linhas; o Supabase Realtime empurra para o Lovable.
-- Zero WebSocket próprio, zero polling, zero CORS.
-- ═══════════════════════════════════════════════════════════════════════════

create extension if not exists "uuid-ossp";

-- ── operação ───────────────────────────────────────────────────────────────
create table operations (
  id              uuid primary key default uuid_generate_v4(),
  ref             text unique not null,          -- 'MZO-GDL-4471'
  container       text,                          -- 'MSKU 784 2219'
  origin          text,
  destination     text,
  cargo_value_usd numeric,
  free_time_ends  timestamptz not null,          -- o relógio que custa dinheiro
  demurrage_per_day numeric not null default 0,
  currency        text not null default 'MXN',
  status          text not null default 'open',  -- open | booked | escalated | closed
  created_at      timestamptz default now()
);

-- ── mandato: DADO, não prompt ──────────────────────────────────────────────
create table mandates (
  id              uuid primary key default uuid_generate_v4(),
  operation_id    uuid references operations(id) on delete cascade,
  target_rate     numeric not null,
  max_rate        numeric not null,              -- teto absoluto
  min_rate        numeric not null default 0,
  max_rounds      int    not null default 4,
  pickup_from     timestamptz not null,
  pickup_to       timestamptz not null,
  -- o que o agente pode revelar ao jogar uma cotação contra a outra
  may_reveal_best_price      boolean not null default true,
  may_reveal_competitor_name boolean not null default false,
  may_reveal_max_rate        boolean not null default false,
  created_at      timestamptz default now(),
  constraint mandate_sane check (max_rate >= target_rate and target_rate >= min_rate)
);

-- ── leilão ─────────────────────────────────────────────────────────────────
create table auctions (
  id              uuid primary key default uuid_generate_v4(),
  operation_id    uuid references operations(id) on delete cascade,
  mandate_id      uuid references mandates(id),
  status          text not null default 'running',  -- running | committed | escalated | failed
  winner_call_id  uuid,
  -- LOCK DE RESERVA: só uma chamada pode fechar. Ver auction.py.
  reserved_by     uuid,
  reserved_at     timestamptz,
  started_at      timestamptz default now(),
  decided_at      timestamptz,
  decision_reason text
);

-- ── chamada ────────────────────────────────────────────────────────────────
create table calls (
  id              uuid primary key default uuid_generate_v4(),
  auction_id      uuid references auctions(id) on delete cascade,
  operation_id    uuid references operations(id) on delete cascade,
  direction       text not null,                 -- outbound | inbound
  carrier_id      text,
  carrier_name    text,
  phone           text,
  call_sid        text unique,                   -- SID da Twilio
  conference_name text,                          -- toda chamada nasce numa conference
  status          text not null default 'dialing', -- dialing | live | escalated | done | failed
  language        text default 'es-MX',
  recording_url   text,
  started_at      timestamptz default now(),
  ended_at        timestamptz
);

-- ── transcrição ao vivo (é o que faz o painel se mexer) ────────────────────
create table utterances (
  id              bigserial primary key,
  call_id         uuid references calls(id) on delete cascade,
  speaker         text not null,                 -- agent | counterparty | human
  text            text not null,
  t_ms            int,                           -- offset desde o início da chamada
  interrupted     boolean default false,
  created_at      timestamptz default now()
);

-- ── toda decisão de política vira linha. É a auditoria do Pilar 01. ────────
create table policy_events (
  id              bigserial primary key,
  call_id         uuid references calls(id) on delete cascade,
  counterparty_ask numeric,
  decision        text not null,                 -- allow | deny | escalate | block
  amount          numeric,                       -- o que a política autorizou
  reason          text not null,                 -- at_or_below_target | above_max_rate | ...
  utterance       text,                          -- a frase EXATA autorizada a falar
  round           int,
  created_at      timestamptz default now()
);

-- ── compromisso: sem âncora no áudio, não existe ───────────────────────────
create table commitments (
  id              bigserial primary key,
  call_id         uuid references calls(id) on delete cascade,
  operation_id    uuid references operations(id) on delete cascade,
  field           text not null,                 -- rate | pickup_at | equipment | driver
  value           text not null,
  quote           text not null,                 -- as palavras literais ditas
  t_start_ms      int  not null,                 -- ← a âncora
  t_end_ms        int  not null,
  confidence      numeric,
  state           text not null default 'proposed',
  -- proposed | read_back | confirmed | in_execution | amended | retracted
  supersedes      bigint references commitments(id),
  created_at      timestamptz default now(),
  -- INVARIANTE: nenhum compromisso sem janela de áudio.
  constraint anchored check (t_end_ms >= t_start_ms and t_start_ms >= 0)
);

-- ── call brief ─────────────────────────────────────────────────────────────
create table call_briefs (
  call_id         uuid primary key references calls(id) on delete cascade,
  actions         jsonb not null default '[]',   -- o que o agente FEZ
  mentions        jsonb not null default '[]',   -- o que foi dito e é relevante
  outcome         text,
  recap_sent_to   text,
  recap_sent_at   timestamptz,
  created_at      timestamptz default now()
);

-- ── escalação ──────────────────────────────────────────────────────────────
create table escalations (
  id              bigserial primary key,
  call_id         uuid references calls(id) on delete cascade,
  trigger         text not null,                 -- above_max_rate | max_rounds | contradiction
  brief           text not null,                 -- o resumo entregue ao humano
  computation     jsonb,                         -- a CONTA: opção A vs opção B
  human_phone     text,
  human_joined_at timestamptz,
  resolution      text,
  created_at      timestamptz default now()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- REALTIME — sem isto o painel do Lovable fica parado
-- ═══════════════════════════════════════════════════════════════════════════
alter publication supabase_realtime add table operations;
alter publication supabase_realtime add table auctions;
alter publication supabase_realtime add table calls;
alter publication supabase_realtime add table utterances;
alter publication supabase_realtime add table policy_events;
alter publication supabase_realtime add table commitments;
alter publication supabase_realtime add table escalations;

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS — aberto para leitura, porque é demo de hackathon e o painel é anônimo.
-- Escrita só pela service_role (o backend). DIGAM ISSO NA DEFESA:
-- "sabemos que é permissivo; é escopo de demo, e o caminho de produção é
--  autenticação por organização com policy por operation_id."
-- ═══════════════════════════════════════════════════════════════════════════
do $$ declare t text;
begin
  foreach t in array array['operations','mandates','auctions','calls','utterances',
                           'policy_events','commitments','call_briefs','escalations']
  loop
    execute format('alter table %I enable row level security', t);
    execute format('create policy anon_read on %I for select to anon using (true)', t);
  end loop;
end $$;

create index on utterances (call_id, id);
create index on policy_events (call_id, id);
create index on commitments (operation_id, created_at);
create index on calls (auction_id);

-- ── seed do caso do enunciado ──────────────────────────────────────────────
insert into operations (ref, container, origin, destination, cargo_value_usd,
                        free_time_ends, demurrage_per_day, currency)
values ('MZO-GDL-4471', 'MSKU 784 2219', 'Puerto de Manzanillo',
        'Bodega Guadalajara', 180000,
        '2026-09-03 18:00-06', 2400, 'MXN');

insert into mandates (operation_id, target_rate, max_rate, min_rate,
                      pickup_from, pickup_to)
select id, 8000, 9000, 6000, '2026-09-03 08:00-06', '2026-09-03 18:00-06'
from operations where ref = 'MZO-GDL-4471';
