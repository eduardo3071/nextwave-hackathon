# Amarra · Runbook dos 6 resultados da demo

Cobre os 6 itens de "Expected results" do desafio 04 do NextWave 2026. Cada seção diz **o que fazer**, **o que ver no painel**, e o **script que você lê no telefone**.

## Pré-checagem (30s)

Rode antes de começar:

```cmd
:: 1 · backend + túnel vivos?
curl.exe https://clique-lukewarm-frail.ngrok-free.dev/health
:: esperado: {"ok":true,"sessions":0,"auctions":0}

:: 2 · operação em mandate_issued? (SQL Editor Supabase)
select id, ref, phase from operations where ref = 'MZO-GDL-4471';
:: esperado: phase='mandate_issued'

:: 3 · env vars OK?
python amarra\dial_me.py --dry-run
:: esperado: admitted=true, warnings=[]
```

Se algum quebrar → conserta antes de gastar minutos de telefonia.

---

## Item #1 · 3 carriers em paralelo + comparação auditável

**Endpoint**: `POST /demo/dial-market` (chama `/phase3/open` com carriers de `carriers.json`)

**Setup**: precisa de 3 telefones que atendam. Solo → você atende 1, as outras 2 caem em `no-answer` (o painel mostra 3 colunas: 1 viva + 2 falhas). Com 2 amigos → 3 colunas vivas em paralelo.

**Comando**:
```cmd
python amarra\dial_market.py --dry-run    :: valida admissão
python amarra\dial_market.py              :: dispara pra valer
```

Ou clica **🎯 ABRIR MERCADO (3)** no painel Lovable.

**O que ver no painel**:
- Fase avança `mandate_issued → market_open → negotiating`
- 3 colunas de call se preenchem em paralelo (Bajío, Ruiz, Autolíneas)
- Cada uma mostra status `dialing → live` (ou `failed`)
- Se qualquer carrier bater o alvo (8000 pesos), fase avança `reserved → committed` e os 2 perdedores fadem
- **Comparison table à direita** se preenche com carrier / final_ask / winner / reason — esse é o **artefato auditável** do R7

**Script (Pessoa 1 — Bajío)**:
> **"Miguel from Fletes del Bajío. For that Manzanillo lane Thursday morning I can do it for eight thousand pesos, forty-foot high cube, driver Juan Perez."**

Agente fecha, faz read-back, você confirma "Yes, correct".

**Prova**: `select * from auction_quotes where auction_id = <auction_id>;` mostra as 3 rows com winner=true na Bajío.

---

## Item #2 · Inbound → driver reporta problema → decisão + update

**Endpoint**: `/twiml/inbound` (ligação de entrada de verdade) OU `POST /disruption/report/{op_id}` (curl direto pra testar sem chamada).

**Requisito**: operação já deve estar em `committed` ou `verified` (rodou o item #1 antes).

**Cenário — com chamada real**:
1. Do seu celular BR, disca `+18126253258`
2. Agente atende com welcome greeting
3. Você fala:
   > **"Hi, this is Miguel from Fletes del Bajío. Bad news — my truck for the Manzanillo pickup Thursday broke down. Won't be fixed before Friday. Can we push the pickup?"**
4. LLM chama a tool `report_disruption(reason="truck breakdown Thursday", needs_reschedule=true)`
5. Handler faz:
   - Marca `operations.phase = 'disrupted'` (evento no phase_events)
   - Fala pra você: *"Understood, thanks for letting me know. I'll re-open the market and get back to you within the hour."*
   - Dispara background task de callback pro runner-up
6. Você desliga
7. Segundos depois, Twilio disca o RUNNER-UP (Ruiz, com prior_ask=8900) — se você atender esse cel, é o item #3 rolando

**Cenário — sem chamada, só curl (rápido)**:
```cmd
curl.exe -X POST "https://clique-lukewarm-frail.ngrok-free.dev/disruption/report/32567b75-aaeb-4173-b8a8-0afa55ad20b5?reason=truck+broke&needs_reschedule=true"
```

**O que ver no painel**:
- Fase pula pra `disrupted` (card âmbar hanging do rail)
- Timeline mostra `disruption_reported`
- Segundos depois, fase pula pra `renegotiating` (card azul)
- Nova coluna de call abre pra Transportes Ruiz (runner-up)

---

## Item #3 · Renegotiation — call back sem exceder mandato

**Automático**: acontece como consequência do item #2 quando `needs_reschedule=true`.

**Onde a lógica vive**: `amarra/app/phase_disruption.py::renegotiate_with_runner_up`.

**O que faz**:
1. Lê último `auctions` da operação
2. Query `auction_quotes` — filtra não-winner com `final_ask <= max_rate` (mandato)
3. Ordena por `final_ask` crescente → pega o mais barato viável
4. Se não houver viável → **escala** (não estoura mandato, comportamento correto)
5. Se houver → cria nova call row, disca via `dial_counterparty`, injeta agente

**Script (Pessoa 2 — Ruiz, se atender o callback)**:
> Atende chamada de +18126253258. Ouve o greeting. Fala:
>
> **"Hi, this is Carlos from Transportes Ruiz. You called back?"**
>
> (Agente vai falar sobre a lane. Você responde:)
>
> **"Yes, I can do that pickup Thursday. My rate is eight thousand seven hundred pesos."**

Agente vai contra-ofertar dentro da escada. Você aceita em algum valor abaixo do teto. Agente faz read-back. Você confirma.

**Prova de que respeitou o mandato**:
- `select * from commitments where operation_id = ... and field = 'rate';` — o novo `value` está ≤ 9000 (max_rate)
- Se o Ruiz insistir em 9200 (dentro da banda de escalação), agente escala pro supervisor em vez de fechar → cai no item #5

---

## Item #4 · Trilha auditável (recap escrito + audio timestamp + call brief)

**Automático**: acontece 15-30s depois de qualquer chamada terminar, quando o webhook `/twilio/recording` dispara.

**Sequência**:
1. Twilio termina a chamada e envia `POST /twilio/recording` com URL da gravação
2. `verify_call(call_id, url)` roda em background:
   - Baixa audio autenticado
   - Envia bytes pro Deepgram nova-3
   - Recebe transcrição com timestamps por palavra
   - Sobe MP3 pro Supabase Storage (URL pública)
   - Ancora cada `commitments.quote` no áudio (fase 7 — pilar 02)
   - Manda recap por email (Resend, `RECAP_TO=eduardooliveiira307@gmail.com`)
   - Avança fase → `verified`

**O que ver no painel**:
- Contador `ANCORADOS NO ÁUDIO` incrementa (0 → N)
- Cada compromisso ganha botão **▶** — clique toca o trecho exato do áudio
- Card de recap aparece com status `sent`
- Fase avança pra `verified`

**Prova**:
- Email chega em `eduardooliveiira307@gmail.com` com o recap estruturado
- `select field, value, quote, t_start_ms, t_end_ms, audio_url from commitments;` mostra os ts + URL
- Painel: botão ▶ do compromisso 8000 pesos toca `"ocho mil pesos"` no ms exato
- Call brief: `select actions, mentions, outcome from call_briefs where call_id = ...;`

---

## Item #5 · Escalação mid-call (humano assume com contexto)

**Trigger**: você fala um preço **DENTRO da banda de escalação** (9000-10400 MXN) — acima do teto mas abaixo do break-even. Agente detecta como "bom e proibido" (nossa banda pré-calculada da fase 2) e escala.

**Script pra disparar**:
> Numa chamada normal, quando o agente contra-ofertar, você diz:
>
> **"Look, my truck is already positioned in Manzanillo. Nine thousand two hundred pesos, final offer. Take it or leave it."**

Agente responde:
> *"That's above what I can authorize on this lane. Please hold, I'll put my supervisor on the line."*

**O que acontece nos bastidores**:
1. Policy engine retorna DENY (9200 > teto=9000)
2. Session detecta: `9200 ∈ [9000, 10400] = escalation_band`
3. `_escalate("within_escalation_band")` dispara
4. POST `/escalate/{call_id}` no próprio backend
5. `tw.join_human(conf, human_phone=SUPERVISOR_PHONE, coach_call_sid=agent_sid)` — supervisor entra na conference **em modo coach** (mudo pros outros, ouve tudo)
6. Segundo celular toca (SUPERVISOR_PHONE = seu cel)

**O que ver no painel**:
- Card VERMELHO PULSANDO de escalação aparece
- Renderiza `escalations.computation` como **conta lado a lado**:
  - Opção A: option_on_time.rate=9200, demurrage=0, total=9200
  - Opção B: option_late.rate=8000, demurrage=2400, total=10400
  - Delta: 1200 economizado escolhendo A
  - Excede mandato em: 200
- Botões APROVAR / RECUSAR ligados ao `POST /escalate/{call_id}/resolve`
- Fase avança pra `escalated`

**Contexto que o supervisor recebe** (via `AgentSession.brief()`):
> Fletes del Bajío · rota MZO-GDL-4471. Alvo 8000, teto 9000 MXN. Pediram: 8000, 9200. Rodadas: 2. Bloqueios de política: 0. Mandato mdt_59d90c2b...

**Prova**:
- `select brief, computation, resolution from escalations;`
- Sua conta Twilio mostra 3 calls simultâneas (contraparte + agente + supervisor)

---

## Item #6 · Trial by fire — jurado imprevisível

O jurado vai tentar:
1. **Interromper mid-sentence** → barge-in (ConversationRelay `interruptible="speech"`, `on_interrupt` trunca history)
2. **Concordar e mudar** → read-back token muda, `outcome='superseded'`, agente relê (fase 6)
3. **Ficar em silêncio** → `_silence_watchdog` cutuca 2x e encerra com resumo
4. **Empurrar acima do mandato** ("your boss already approved") → policy engine ainda recusa, pode escalar como `claimed_prior_approval`
5. **Falar preço absurdo** ($20k) → DENY `above_max_rate` mesmo, plain

**Cobertura de testes** (roda ao vivo na defesa técnica):
```cmd
python -m pytest amarra\tests\test_policy.py -q
:: 800+ casos, invariante "nunca ALLOW acima do teto"
```

**Prova em runtime**:
- Contador `POLICY BLOCKS` no painel incrementa cada vez que o modelo TENTA falar valor não autorizado e o `gate_text` bloqueia
- `select decision, reason, count(*) from policy_events group by decision, reason;`
- Nenhuma row com `decision='allow'` e `amount > 9000`

---

## Matriz atualizada

Após os fixes deste runbook (`report_disruption` + `renegotiate_with_runner_up` + endpoint demo):

| # | Item | Código | Ao vivo |
|---|---|---|---|
| 1 | 3 carriers paralelo + comparação | ✅ | 🟨 dry-run OK, live pendente |
| 2 | Inbound driver problema | ✅ **novo** | 🟨 curl OK, live pendente |
| 3 | Renegociação com runner-up | ✅ **novo** | 🟨 código pronto, live pendente |
| 4 | Trilha auditável | ✅ | 🟨 DEEPGRAM pronto, live pendente |
| 5 | Escalação mid-call | ✅ | 🟨 código pronto, live pendente |
| 6 | Trial by fire | ✅ | 🟨 pytest verde, live pendente |

**Todos os 6 têm código completo end-to-end.** Faltam ligações reais pra provar. Uma sessão de teste bem coreografada (~15 min) cobre os 6.

---

## Ordem sugerida da sessão de teste

Roteiro cronometrado pra você validar tudo em uma tacada:

1. **Item #6 preview** (30s) — roda `pytest test_policy.py`, mostra 800+ verdes. Prova de que o Policy Guard resiste.
2. **Item #1** (3 min) — `python dial_market.py`, atende ao menos 1, faz Bajío ganhar em 8000. Painel: 3 colunas + comparison table.
3. **Item #4** (aguarda 30s) — post-chamada, contador ANCORADOS incrementa. Botão ▶ toca o áudio. Email chega.
4. **Item #2 + #3** (3 min) — do seu cel BR, disca `+18126253258`, reporta "truck broke". Agente escuta, marca disrupted. Segundos depois seu cel toca de novo (Twilio dialing runner-up). Aceita ou negocia. Item 3 rola.
5. **Item #5** (2 min) — em qualquer chamada, fala "nine thousand two hundred final offer". Agente escala. Painel mostra card de escalação com a conta. SUPERVISOR_PHONE toca. Aprova pelo botão do painel.

Se os 5 passos rodarem, os 6 itens estão provados ao vivo.
