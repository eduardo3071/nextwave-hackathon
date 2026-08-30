# Amarra · dos 7 objetivos aos 6 resultados

Mapa completo do enunciado NextWave 04. Cada linha mostra: **onde vive o objetivo no código** → **qual endpoint disparar** → **em qual dos 6 resultados ele aparece na demo**.

## 🎯 Mapa 7 × 6

| Objetivo (§2) | Arquivo do código | Rota / trigger | Resultado (§3) onde aparece |
|---|---|---|---|
| **1** Outbound real, 3+ paralelos, dentro do mandato | `phase3_market.py` | `POST /demo/scenario/full` OU `/demo/dial-market` | Resultado 1 |
| **2** Inbound entendido em tempo real | `phase4_negotiating.py::NegotiationSession` + tool `report_disruption` | Discar `+18126253258` | Resultado 2 |
| **3a** Recap escrito pós-chamada | `phase7_verified.py::send_recap` | Automático após qualquer chamada | Resultado 4 |
| **3b** Commitment ligado ao timestamp | `phase7_verified.py::anchor` (Deepgram nova-3) | Automático via webhook `/twilio/recording` | Resultado 4 |
| **4** Call brief estruturado | `phase4_negotiating.py::AgentSession.close()` | Automático ao encerrar chamada | Resultado 4 |
| **5** Conversa e sistema consistentes | `policy.py::gate_text` + `policy_events` | Automático em cada `_say()` | Resultado 6 (visível no contador POLICY BLOCKS) |
| **6** Casos feios (contradição, off-script, escalação sem hangup) | `escalation_triggers` do mandato + `_escalate` + `join_human` coach mode | Automático quando policy retorna DENY dentro da banda [teto, break_even] | Resultado 5 |
| **7** Mercado, não uma call (leilão paralelo + comparação auditável) | `auction.py::market_best` + `auction_quotes` table | Consequência do Objetivo 1 | Resultado 1 |

**Cruzamento inverso:**

| Resultado (§3) | Objetivos que satisfaz |
|---|---|
| **1** 3 carriers + comparação | 1, 5, 7 |
| **2** Inbound → decisão | 2, 5 |
| **3** Renegotiation | 2, 6 |
| **4** Auditable trail | 3a, 3b, 4, 5 |
| **5** Escalation mid-call | 6 |
| **6** Trial by fire | 5, 6, todos os invariantes |

Nenhum objetivo fica órfão. Nenhum resultado depende de código que ainda não existe.

## 🎬 Coreografia de 15 minutos

Encadeamento pra rodar a demo inteira sem parar entre passos. Cada minuto é UM comando OU UM script lido no telefone.

### 0:00 · Pré-check (30s)
```cmd
curl.exe https://clique-lukewarm-frail.ngrok-free.dev/health
python amarra\dial_me.py --dry-run
```
Espera: `{"ok":true,...}` e `admitted=true`.

### 0:30 · Trial by fire preview (30s) — Objetivo 5 + 6 antecipados
```cmd
python -m pytest amarra\tests\test_policy.py -q
```
No palco: "800+ casos, invariante 'nunca ALLOW acima do teto', tempo <1s".

### 1:00 · Kickoff (Objetivos 1 + 5 + 7 → Resultado 1)
```cmd
curl.exe -X POST https://clique-lukewarm-frail.ngrok-free.dev/demo/scenario/full
```
Backend faz internamente:
1. Reset se necessário
2. Emite mandato se ainda não emitido → mandate_hash cunhado
3. Dispara 3 carriers em paralelo

Painel Lovable mostra:
- Fase avança `mandate_issued → market_open → negotiating`
- 3 colunas de call se preenchem em paralelo
- Comparison table (auction_quotes) se preenche

### 2:00-5:00 · Negociação viva
Você ou os 2 amigos atendem, seguem os scripts. Recomendado:
- **Bajío em 8000** (buy-it-now — fecha na hora)
- **Ruiz em 9200** (dentro da banda — dispara Objetivo 6 → Resultado 5)

Painel:
- Contador POLICY BLOCKS zerado (mandato não foi violado — Obj 5)
- Card VERMELHO de escalação com a conta lado a lado (Obj 6 + Result 5)
- Card verde de commit na Bajío se ela ganhar

### 5:30 · Consequência automática — Objetivos 3a, 3b, 4 → Resultado 4
Espera 30 segundos após desligar. Webhook `/twilio/recording` roda:
- Baixa audio da Twilio
- Deepgram transcreve com timestamps
- Ancora cada commitment
- Sobe MP3 pro Supabase Storage
- Manda email de recap (Resend)
- Salva call_brief

Painel:
- Contador `ANCORADOS NO ÁUDIO` incrementa (0 → 2)
- Botões ▶ aparecem em cada compromisso — clique toca trecho exato
- Card de recap com status `sent`

### 8:00 · Inbound + Renegotiation (Obj 2 → Results 2 + 3)
Do seu celular BR, disca `+18126253258`. Após greeting:
> **"Hi, Miguel from Fletes del Bajío. Bad news, my truck broke down. Can we push pickup to Friday?"**

Agente ouve, chama tool `report_disruption(reason, needs_reschedule=true)`:
1. Marca operação como `disrupted` (Result 2) — card âmbar hanging
2. Fala ack em inglês: *"Understood, thanks. I'll re-open the market."*
3. Background: `renegotiate_with_runner_up` lê `auction_quotes`, filtra dentro do teto, disca segundo colocado
4. Alguns segundos depois, o cel do RUNNER-UP toca (Result 3)

### 11:00 · Fechamento (Objetivo cross-cutting)
```cmd
curl.exe -X POST https://clique-lukewarm-frail.ngrok-free.dev/phase8/close/32567b75-aaeb-4173-b8a8-0afa55ad20b5
```
Painel:
- Rail inteiro verde ✓
- Countdown congela: *"closed with 4d Xh to spare"*
- Link "Ver dossiê" aparece

### 12:00 · Dossiê — todos os artefatos num único JSON
```cmd
curl.exe https://clique-lukewarm-frail.ngrok-free.dev/phase8/dossier/32567b75-aaeb-4173-b8a8-0afa55ad20b5
```
Ou clica no link do painel. Um único JSON com:
- `mandate_hash` (Obj 5)
- `financial` (agreed_rate, exceeded_by, human_approved) — cobre Obj 1, 6, 7
- `commitments[]` com `audio_url` + `t_start_ms` (Obj 3a, 3b)
- `escalations[]` com `computation` (Obj 6)
- `timeline[]` com todos os phase_events (Obj 5, todos)
- `comparison[]` = auction_quotes (Obj 7)

**Isso é o entregável do R4 do enunciado.** Um jurado abre este JSON e vê a operação inteira sem precisar de nós.

### 14:00 · Sanity meta-view

```cmd
curl.exe https://clique-lukewarm-frail.ngrok-free.dev/demo/scenario/status/MZO-GDL-4471
```

Retorna um JSON estruturado com: **para cada um dos 7 objetivos**, se `met: true/false` e a `evidence`; **para cada um dos 6 resultados**, se `met: true/false` e o `artifact`.

Se todos os `met=true`, você provou tudo ao vivo.

## 🎯 Comando único pra checar tudo

```cmd
python amarra\demo_scenario.py
```

Uma vez implementado (veja abaixo), esse script:
1. Chama `/demo/scenario/full` (inicia o mercado)
2. Watches `/demo/scenario/status/MZO-GDL-4471` a cada 5 segundos
3. Pinta ✅/⏳ pra cada objetivo/resultado conforme vão ficando verde
4. Encerra quando todos verdes OU timeout

## Notas de defesa técnica

Quando o jurado perguntar "isso realmente funciona?", a resposta é:

- **Objetivo 1**: `POST /demo/scenario/full` — 3 chamadas simultâneas verificáveis nos logs do Twilio
- **Objetivo 2**: qualquer ligação de entrada aciona a tool `report_disruption`
- **Objetivo 3a/b**: cada linha em `commitments` tem `t_start_ms`, `t_end_ms`, `audio_url` e cada linha em `recap_deliveries` tem `status='sent'`
- **Objetivo 4**: cada `calls` tem uma row em `call_briefs` (JSONB com `actions` + `mentions`)
- **Objetivo 5**: `policy_events` tem 800+ rows testadas por pytest + `mandate_hash` em cada uma
- **Objetivo 6**: `escalation_band` pré-calculada no `mandates.canonical.derived.escalation_band` — nomeado ANTES da 1ª ligação; escalação usa `coaching=True` do Twilio pra whisper
- **Objetivo 7**: `auction_quotes` tem N rows com `winner=true` na melhor + razão em cada linha perdedora

Tudo é query SQL. Nada é slide.
