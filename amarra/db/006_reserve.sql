-- ═══════════════════════════════════════════════════════════════════════════
-- AMARRA · migração 006 — RESERVA ATÔMICA
--
-- O árbitro sai do processo e vai para o banco. `UPDATE ... WHERE reserved_by
-- IS NULL` dentro de um `FOR UPDATE` garante que duas transportadoras não
-- fecham no mesmo segundo. Vale com um worker ou com dez.
--
-- E o teto do mandato é REVERIFICADO na camada de storage — cinto e
-- suspensório. Nem um cliente com bug consegue comprometer acima da autoridade.
--
-- Aplicar no SQL Editor do Supabase, depois de 005_market.sql.
-- ═══════════════════════════════════════════════════════════════════════════

alter table auctions
  add column if not exists reserve_amount numeric,
  add column if not exists reserve_attempts int not null default 0,
  add column if not exists released_from uuid,
  add column if not exists release_reason text;

-- a tabela de comparação auditável — o artefato do R7
create table if not exists auction_quotes (
  id           bigserial primary key,
  auction_id   uuid not null references auctions(id) on delete cascade,
  call_id      uuid references calls(id) on delete set null,
  carrier_id   text not null,
  carrier_name text,
  final_ask    numeric,
  approved     numeric,
  rounds       int not null default 0,
  winner       boolean not null default false,
  reason       text not null,
  quote_ms     int,                      -- âncora da última cotação no áudio
  created_at   timestamptz default now(),
  unique (auction_id, carrier_id)
);

alter publication supabase_realtime add table auction_quotes;
alter table auction_quotes enable row level security;
create policy anon_read on auction_quotes for select to anon using (true);

-- ═══════════════════════════════════════════════════════════════════════════
-- O LOCK. Atômico, no banco, imune a quantos workers existirem.
-- ═══════════════════════════════════════════════════════════════════════════
create or replace function try_reserve_auction(
  p_auction_id uuid,
  p_call_id    uuid,
  p_amount     numeric,
  p_reason     text
) returns jsonb
language plpgsql as $$
declare
  a         auctions%rowtype;
  v_ceiling numeric;
begin
  -- serializa as tentativas concorrentes nesta linha
  select * into a from auctions where id = p_auction_id for update;
  if not found then
    return jsonb_build_object('granted', false, 'reason', 'auction_not_found');
  end if;

  -- reserved_by antes de status: na corrida, o vencedor seta os dois no mesmo
  -- UPDATE, e a razão mais informativa para os perdedores é 'already_reserved'
  if a.reserved_by is not null then
    return jsonb_build_object('granted', false, 'reason', 'already_reserved',
                              'winner', a.reserved_by);
  end if;

  if a.status <> 'running' then
    return jsonb_build_object('granted', false, 'reason', 'auction_not_running',
                              'winner', a.reserved_by);
  end if;

  -- CINTO E SUSPENSÓRIO: o teto é reverificado aqui, na camada de storage.
  -- Nem um cliente com bug consegue comprometer acima da autoridade.
  select max_rate into v_ceiling from mandates where id = a.mandate_id;
  if p_amount > v_ceiling then
    return jsonb_build_object('granted', false, 'reason', 'above_max_rate',
                              'ceiling', v_ceiling);
  end if;

  update auctions
     set reserved_by = p_call_id, reserved_at = now(),
         reserve_amount = p_amount, reserve_attempts = reserve_attempts + 1,
         winner_call_id = p_call_id, status = 'committed',
         decision_reason = p_reason, decided_at = now()
   where id = p_auction_id;

  return jsonb_build_object('granted', true, 'winner', p_call_id,
                            'amount', p_amount, 'reason', p_reason);
end $$;

-- devolve o lock quando o vencedor não confirma
create or replace function release_reservation(
  p_auction_id uuid, p_reason text
) returns jsonb
language plpgsql as $$
declare a auctions%rowtype;
begin
  select * into a from auctions where id = p_auction_id for update;
  if a.reserved_by is null then
    return jsonb_build_object('released', false, 'reason', 'not_reserved');
  end if;
  update auctions
     set released_from = a.reserved_by, release_reason = p_reason,
         reserved_by = null, reserved_at = null, reserve_amount = null,
         winner_call_id = null, status = 'running',
         decision_reason = null, decided_at = null
   where id = p_auction_id;
  return jsonb_build_object('released', true, 'was', a.reserved_by);
end $$;
