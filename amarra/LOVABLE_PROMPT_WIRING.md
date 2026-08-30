# Amarra Dashboard — wiring completo (das 8 fases)

**Não reconstrua o app.** Pegue o que já existe em `nextwave-hackathon.lovable.app` (Vite + React + TanStack Router + Supabase, componentes em `src/components/amarra/`) e conecte fim-a-fim ao backend real. **Remova todo dado mockado.** O objetivo é uma sala de controle que reage sozinha a cada linha que o backend escreve — nenhum polling, nenhum placeholder, nenhum estado inventado no front.

O backend nunca fala com o frontend. Ele escreve no Supabase; o Supabase Realtime empurra pro painel. **Assine, não pergunte.**

---

## 1 · Conexão

Duas variáveis de ambiente. Nada mais.

```
VITE_SUPABASE_URL          https://<projeto>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY   <anon key — NUNCA a service_role>
VITE_BACKEND_URL           https://<ngrok>.ngrok.app     (FastAPI do Amarra)
```

Use o cliente Supabase já existente em `src/integrations/supabase/client.ts`. Estenda `src/lib/useAmarraRealtime.ts` para cobrir TODAS as tabelas abaixo. Nada de `useEffect` com `setInterval` para buscar dados.

---

## 2 · Modelo de dados (13 tabelas do backend, todas com Realtime ligado)

| Tabela | O que traz | Chave prática |
|---|---|---|
| `operations` | uma linha por operação. `phase`, `clock_state`, `free_time_ends`, `demurrage_per_day`, `currency`, `outcome`, `closed_at` | filtra por `ref` |
| `mandates` | mandato compilado. `mandate_hash`, `target_rate`, `max_rate`, `ladder`, `break_even_rate`, `escalation_band`, `escalation_triggers`, `issue_warnings`, `pickup_from`, `pickup_to` | 1:1 com `operations` via `operation_id` |
| `phase_events` | append-only, a linha do tempo. `phase`, `previous`, `kind` (`spine`/`branch`/`terminal`), `trigger`, `detail`, `ms_in_previous`, `payload` | ordena por `id`, filtra por `operation_id` |
| `auctions` | leilão vivo. `status` (`running`/`committed`/`failed`/`escalated`), `reserved_by`, `reserve_amount`, `dial_plan`, `legs_planned`, `legs_budget`, `soft_deadline_s`, `hard_deadline_s`, `admission_warnings`, `winner_call_id`, `decision_reason` | 1:1 com `operations` |
| `auction_quotes` | tabela auditável do R7. `carrier_id`, `carrier_name`, `final_ask`, `approved`, `rounds`, `winner`, `reason` | filtra por `auction_id` |
| `calls` | uma perna por chamada. `leg_role` (`counterparty`/`agent`/`human`), `status`, `carrier_name`, `phone`, `language`, `answered_at`, `dial_attempt`, `dial_error`, `audio_public_url`, `transcript_words` | filtra por `auction_id` OU `operation_id` |
| `utterances` | transcrição ao vivo. `speaker` (`counterparty`/`agent`/`human`), `text`, `t_ms`, `interrupted` | filtra por `call_id`, ordena por `id` |
| `policy_events` | toda decisão de política. `counterparty_ask`, `decision` (`allow`/`deny`/`escalate`/`block`), `amount`, `reason`, `utterance`, `round`, `mandate_hash` | filtra por `call_id` |
| `read_backs` | cada tentativa de read-back da fase 6. `token`, `slots`, `spoken_text`, `response_text`, `outcome` (`confirmed`/`rejected`/`ambiguous`/`superseded`), `attempt`, `t_spoken_ms`, `t_response_ms` | filtra por `call_id` |
| `commitments` | fatos acordados. `field` (`rate`/`pickup_at`/`equipment`/`driver`/`mc_number`), `value`, `quote`, `state` (`proposed`/`read_back`/`confirmed`), `anchor_state` (`pending`/`anchored`/`not_found`/`low_confidence`), `t_start_ms`, `t_end_ms`, `affirmation_t_start_ms`, `affirmation_t_end_ms`, `audio_url`, `confidence`, `anchor_method`, `mandate_hash` | filtra por `operation_id` |
| `escalations` | humano na linha. `trigger`, `brief`, `computation` (jsonb com `option_on_time`/`option_late`/`delta`/`exceeds_mandate_by`), `human_joined_at`, `resolution` | filtra por `call_id` |
| `recap_deliveries` | R3a. `channel` (`email`/`sms`), `target`, `subject`, `body`, `status` (`sent`/`failed`), `error` | filtra por `operation_id` |
| `dossiers` | artefato final. `outcome`, `headline`, `financial`, `operational`, `timeline`, `commitments`, `comparison`, `escalations`, `mandate_hash` | 1:1 com `operations` |

Para CADA tabela acima, `supabase.channel(...).on('postgres_changes', { event: '*', schema: 'public', table: '...' }, ...)`. Zero exceções.

---

## 3 · Layout — sala de controle escura, densa, monoespaçada para números

Ordem visual, de cima pra baixo:

```
┌─────────────────────────────────────────────────────────────────┐
│  TOP BAR              op ref · contêiner · ROTA                 │
│                       ⏱ COUNTDOWN GIGANTE       BLOCKS · COMMITS │
├─────────────────────────────────────────────────────────────────┤
│  PHASE RAIL   detected → mandate → market → negotiating →      │
│               reserved → committed → verified → closed         │
├─────────────────────────────────────────┬───────────────────────┤
│                                         │  QUOTE COMPARISON     │
│  THREE CALL COLUMNS (side by side)      │  (audit table)        │
│                                         ├───────────────────────┤
│  · header (carrier · phone · status)    │  COMMITMENTS          │
│  · live transcript                      │  (click → plays clip) │
│  · policy strip                         ├───────────────────────┤
│                                         │  ESCALATION PANEL     │
│                                         │  (side-by-side calc)  │
├─────────────────────────────────────────┴───────────────────────┤
│  RECAPS · DOSSIER (quando `closed` chegar)                      │
└─────────────────────────────────────────────────────────────────┘
```

Regra de tipografia: **`tabular-nums`** em TODO número, tempo e valor. Fonte de UI sans, fonte mono para dados. Contraste alto — o painel roda em projetor.

---

## 4 · Top bar

### Contexto
- Esquerda: `operations.ref`, `operations.container`, `operations.origin → operations.destination`
- Direita: dois contadores grandes:
  - **POLICY BLOCKS** — `count(policy_events)` onde `decision = 'block'` filtrado pela operação atual. **Piscar vermelho** quando incrementa.
  - **COMMITMENTS ANCHORED** — `count(commitments)` onde `anchor_state = 'anchored'`.

### O relógio (centro emocional da tela)
Derive no navegador:
```
remaining_ms = new Date(operations.free_time_ends) - Date.now()
```
Formate em `HH:MM:SS` monoespaçado, **enorme** (tipo `text-8xl`). Abaixo, uma linha menor: `"após esse prazo: {demurrage_per_day} {currency}/dia"`.

**Cor vem do banco, NÃO da conta local**. Leia `operations.clock_state`:
- `safe` → verde
- `warning` → âmbar
- `critical` → vermelho pulsante
- `expired` → vermelho fixo
- `stopped` → cinza (fase 8: mostre `"encerrado com {slack_hours}h de folga"` ao invés do countdown)

O `clock_state` muda por Realtime — o backend só escreve quando cruza o limiar, então nunca vai piscar sozinho.

### Chips do mandato (abaixo do relógio, menor)
De `mandates`:
- `target_rate` — cinza
- `max_rate` — borda vermelha grossa (fronteira dura, não sugestão)
- `pickup_from` a `pickup_to` — janela de coleta
- Hover no chip do teto revela: `"break-even {break_even_rate} · banda {escalation_band.from}–{escalation_band.to}"`

Se `mandates.issue_warnings` não estiver vazio, ícone de alerta amarelo com tooltip listando os avisos.

---

## 5 · Phase rail

Barra horizontal fixa logo abaixo do top bar. Oito passos da espinha, SEMPRE nesta ordem, SEMPRE todos visíveis:

```
detected → mandate issued → market open → negotiating → reserved → committed → verified → closed
```

Regras:
- **Completed**: preenchido, com tempo decorrido dentro (formato `1m 12s`) — leia de `phase_events.ms_in_previous`.
- **Current**: contorno pulsante, maior, com `phase_events.detail` do último evento embaixo da barra.
- **Future**: contorno esmaecido.
- Linha conectora que preenche progressivamente.

### Desvios (não substituem a espinha, INTERROMPEM)
Quatro fases de branch: `disrupted` (âmbar), `renegotiating` (azul), `escalated` (vermelho pulsante), `resolved` (verde).

Quando `operations.phase` for uma dessas:
- **Congele o passo da espinha atual** — não avance.
- **Solte um card BRANCH abaixo do rail**, visualmente pendurado no passo congelado. Título = nome do desvio. Corpo = `phase_events.detail`.
- Em `escalated`, o card expande para o painel de escalação (ver seção 8).
- Quando a fase voltar pra espinha, colapse o branch card em um marcador pequeno preso ao passo — **o desvio permanece visível no rail terminado**. É a coisa mais interessante que aconteceu; o júri vai perguntar.

### Estados terminais
- `closed`: rail inteiro verde; countdown congela mostrando `"closed with {slack_hours}h to spare"`.
- `failed`: rail vermelho no ponto onde parou, com `phase_events.detail` como motivo.

### Linha do tempo (opcional, no rail lateral)
Lista reverso-cronológica de `phase_events`. Cada linha: label da fase, `trigger` em mono esmaecido, `detail`, tempo. Rows de branch com cor própria. Novas entradas deslizam.

O `trigger` é evidência: é o evento que causou a transição (`lock_acquired`, `above_max_rate`, `inbound_problem_reported`). Mostre **verbatim, em monoespaçada** — prova que a fase veio do sistema, não de um script.

---

## 6 · Três colunas de chamada

Uma coluna por row em `calls` onde `auction_id` = leilão vivo E `leg_role = 'counterparty'`. Máximo 3 lado a lado.

### Header da coluna
- `carrier_name` grande
- `phone` monoespaçado, menor
- Pill de status colorido:
  - `dialing` — cinza, ícone de telefone tocando
  - `live` — verde, **ponto pulsante**
  - `escalated` — azul pulsante
  - `done` — cinza escuro, opacidade 60%
  - `failed` — vermelho com `calls.dial_error` em tooltip

### Transcrição ao vivo
`utterances` filtrada por `call_id` desta coluna, ordenada por `id`, mais novo em baixo, auto-scroll.
- `speaker = 'counterparty'`: alinhado à esquerda, fundo cinza escuro
- `speaker = 'agent'`: alinhado à direita, fundo azul-escuro, itálico
- `speaker = 'human'`: alinhado à direita, borda amarela, badge "supervisor"
- `interrupted = true`: badge pequeno `"interrompido"` no canto

### Policy strip (abaixo da transcrição)
Cada linha de `policy_events` filtrada por `call_id`, uma linha compacta:

```
{counterparty_ask} → {decision}   {reason}
```

Cores:
- `allow` verde
- `deny` âmbar
- `block` vermelho — **este pisca** quando adicionado (é o momento "o modelo tentou, a política não deixou")
- `escalate` azul

Hover mostra `utterance` completa e `mandate_hash` truncado.

### Column release
Quando `calls.status` vai pra `done` porque outra ganhou, fade a coluna para opacidade 40% e carimbe **"released"** no topo. Não remova — a evidência de que existiu.

---

## 7 · Right rail

### Quote comparison table (topo)
De `auction_quotes` filtrada por `auction_id`:

| Carrier | Final ask | Rounds | Reason | ✓ |
|---|---|---|---|---|

Ordenar por winner primeiro, depois por `final_ask` crescente. Row vencedora com fundo verde, ícone ✓. **Estilize como artefato de auditoria** — bordas finas, cabeçalho monoespaçado, zero animação. É o que um jurado vai apontar.

### Commitments (meio) — **a interação mais importante**
Uma linha por row em `commitments` filtrada por `operation_id` E `anchor_state IN ('anchored', 'low_confidence')`:

```
{field}: {value}                              [confidence]
"{quote}"                                     [método]
  dito às {mmss(t_start_ms)}                  ▶
  confirmado às {mmss(affirmation_t_start_ms)} ▶
```

Cada `▶` é um botão. **Clicando, toca EXATAMENTE aquele trecho de `audio_url`** usando `<audio>` HTML5:
```ts
const el = new Audio(commitment.audio_url);
el.currentTime = commitment.t_start_ms / 1000;
el.play();
setTimeout(() => el.pause(), commitment.t_end_ms - commitment.t_start_ms);
```

Faça isso funcionar **primeira vez, sem pré-carregar**. Se `audio_url` for null, o botão fica cinza com tooltip `"áudio ainda sendo processado"`.

Commitments com `anchor_state = 'not_found'` aparecem em uma seção separada **NÃO REGISTRADO** com fundo vermelho fraco: `"{field}: mencionado, mas não localizado no áudio — precisa de confirmação humana"`.

Compromissos com `anchor_method = 'fuzzy'` ou `'numeric'` ganham um badge pequeno indicando o método.

### Read-back log (opcional, expansível)
`read_backs` filtrada por `call_id`. Cada linha:
```
tentativa {attempt}     {outcome}
"{spoken_text}"
resposta: "{response_text}"
```
`confirmed` verde, `rejected` âmbar, `ambiguous` cinza, `superseded` roxo. Mostre TODAS as tentativas — inclusive as que a contraparte recusou. É a prova de que o "sim" é conservador.

---

## 8 · Painel de escalação (aparece SOB DEMANDA)

Aparece quando chega uma linha em `escalations`. Modal ou card expandido sobrepondo o phase rail no ponto do desvio.

Estrutura:

### Cabeçalho
- Trigger em monoespaçada grande (`above_max_rate`, `within_escalation_band`, `confirmed_differs_from_reserved`, `max_rounds_exceeded`)
- Brief em prosa (`escalations.brief`)
- Mandato: `mandate_hash` truncado

### A conta (o coração do pitch)
De `escalations.computation` (jsonb):

```
┌─────────────────────────────────┬─────────────────────────────────┐
│  OPÇÃO A: {option_on_time.label}│  OPÇÃO B: {option_late.label}   │
│                                 │                                 │
│  Rate:      {rate}              │  Rate:      {rate}              │
│  Demurrage: {demurrage}         │  Demurrage: {demurrage}         │
│  ─────────────                  │  ─────────────                  │
│  TOTAL:     {total}             │  TOTAL:     {total}             │
└─────────────────────────────────┴─────────────────────────────────┘

                     Δ = {delta} {currency}

              ⚠ EXCEDE O MANDATO EM {exceeds_mandate_by} {currency}
```

A linha "EXCEDE O MANDATO" em vermelho, fonte grande, borda em cima. Ela desaparece se `exceeds_mandate_by == 0`.

### Ações
Dois botões grandes:
- **APROVAR** (verde) → `POST ${VITE_BACKEND_URL}/escalate/{call_id}/resolve` body `{ "approved": true, "note": "..." }`
- **RECUSAR** (vermelho) → mesmo endpoint, `{ "approved": false, "note": "..." }`

Campo de texto opcional para `note`. Após clicar, o card colapsa e o phase rail volta a andar (a fase vai pra `resolved`).

Se `resolution` já estiver preenchido, mostre o desfecho ao invés dos botões.

---

## 9 · Recaps

Card no rodapé mostrando `recap_deliveries` filtrado por `operation_id`. Uma linha por envio:

```
✉ email  →  {target}     [sent | failed]     {created_at}
📱 sms   →  {target}     [sent | failed]     {created_at}
```

Se `status = failed`, tooltip mostra `error`. Botão pequeno **"Reenviar"** que faz `POST ${VITE_BACKEND_URL}/phase7/verify/{call_id}` (reprocessa a evidência e dispara o recap de novo).

---

## 10 · Dossier view (quando `operations.phase = 'closed'` ou `'failed'`)

Rota separada `/dossier/:operation_ref` — link aparece no top bar como **"Ver dossiê"** assim que `dossiers` recebe uma linha.

A página renderiza `dossiers` inteiro:

### Headline (topo, gigante)
`dossiers.headline` — a frase calculada, tipo:
> `MZO-GDL-4471 · 4 ligações · 3 desvios · uma decisão humana de 9s · 19h de folga no relógio`

### Financial (card grande)
De `dossiers.financial`:
- `agreed_rate` (grande, verde ou vermelho conforme `exceeded_mandate`)
- Comparação com `target_rate` e `max_rate` — `vs_target`, `vs_ceiling`
- Se `exceeded_mandate = true`: badge âmbar `"Excedeu em {exceeded_by} — aprovado por humano"` (contra `human_approved`)
- `demurrage_avoided` — quanto teria custado perder o prazo
- `slack_hours` — folga que sobrou

### Operational (card)
De `dossiers.operational`:
- `calls_dialed` / `calls_answered` / `carriers_compared`
- `policy_blocks` — vermelho
- `escalations` — azul
- `human_decision` — se existir
- `total_duration`
- `branches` — lista de desvios que ocorreram

### Timeline (lista)
De `dossiers.timeline`: cada `phase_event` como uma linha:
```
{label}                    {trigger} · {held_previous}
{detail}
```
Rows de branch com cor. Mostre `at` (timestamp) menor em cinza.

### Comparison table (auditável)
De `dossiers.comparison` — a mesma quote table de antes, mas congelada.

### Commitments com áudio (a joia)
De `dossiers.commitments` — mesmo widget da lista viva, mas agora IMUTÁVEL. Clicando ainda toca o trecho. É o que um jurado abre e usa sem precisar de você do lado.

### Escalations
De `dossiers.escalations` — cada uma como card com brief + computation + resolution.

### Mandate hash (rodapé)
`dossiers.mandate_hash` em monoespaçada, com tooltip `"identidade da autoridade sob a qual cada decisão foi tomada"`.

---

## 11 · Ações (botões que fazem POST)

Um botão único de **"Iniciar operação"** no top bar quando não há operação viva:
```
POST ${VITE_BACKEND_URL}/phase1/detect
body = { ref, container, origin, destination, discharged_at, free_days, demurrage_per_day, mandate: {...}, source: {...} }
```

Depois disso, os botões contextuais aparecem conforme a fase:

| Fase atual | Botão | Chamada |
|---|---|---|
| `detected` | Emitir mandato | `POST /phase2/issue/{operation_id}` |
| `mandate_issued` | Abrir mercado | `POST /phase3/open` com `{ operation_ref, carriers: [...] }` |
| `market_open`, `negotiating` | Abortar leilão | `POST /phase3/abort/{auction_id}` |
| `reserved` | Devolver reserva | `POST /phase5/release/{auction_id}` |
| `escalated` | (botões dentro do painel de escalação) | ver seção 8 |
| `verified` | Encerrar | `POST /phase8/close/{operation_id}` |
| qualquer | Falhar manualmente | `POST /phase8/fail/{operation_id}` |
| `closed`, `failed` | Reabrir | `POST /phase8/reopen/{operation_id}?call_id=...` |

Todos os botões destrutivos (abortar, falhar) pedem confirmação inline. Nenhum modal pesado.

Erros do backend: mostre um **toast** com o corpo da resposta. Nunca engula silenciosamente. Códigos 409 são esperados (guardas de fase); mostre o motivo tal como o backend deu (é sempre uma frase legível).

---

## 12 · Empty states — SEM MOCK

Se não houver operação: mostre `"Aguardando descarga do primeiro contêiner"` no lugar do relógio. Não invente números.

Se `operations` existe mas `mandates.mandate_hash` é `null`: mostre `"Mandato aguardando emissão — rode a fase 2"` no lugar dos chips.

Se `auctions` existe mas `calls` está vazio: mostre `"Discando..."` na área das colunas com spinner monoespaçado (`⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`).

Se `commitments` vazio: `"Nenhum compromisso ancorado ainda"`.

Se `escalations` vazio: **NADA**. Não mostre "sem escalações"; o painel de escalação não deve existir na tela até ter uma linha.

Se `dossiers` vazio (operação em andamento): **NÃO mostre** a rota de dossiê.

---

## 13 · Anti-padrões

**NUNCA** faça nenhuma destas:
- `setInterval` pra buscar dados. **Assine.**
- `useMemo` computando cor/estado a partir de `Date.now()` a cada render. Cor vem de `operations.clock_state`.
- `fetch('/api/mock/...')` ou qualquer coisa que retorne fixture. Se a tabela está vazia, mostre empty state (seção 12).
- Cache local persistente (`localStorage`) de dados de operação. Recarregar o painel = ler do zero do Supabase.
- Renderizar valores calculados no cliente que o backend já expõe (agreed_rate, break_even, ladder — leia do banco).
- Mostrar `carrier_name` em lugar nenhum quando o mandato tem `may_reveal_competitor_name = false`. O painel É a visão interna, mas o print vira slide — dado que não pode vazar não deve aparecer NEM ali.
- Aceitar comprimento variável nas 3 colunas de chamada. Sempre 3 slots; se `calls_dialed < 3`, os outros ficam com skeleton mostrando `"aguardando..."`.
- Números em fonte proporcional. **Sempre `tabular-nums`**.

---

## 14 · Micro-animações (do menos ao mais chamativo)

- Novo `utterance` chegando: fade + slide de 200ms
- Novo `policy_event`: fade
- **`policy_event` com `decision = 'block'`**: flash vermelho + shake no contador POLICY BLOCKS (é o momento wow)
- Nova `commitment` com `state = 'confirmed'`: pulso verde no contador COMMITMENTS ANCHORED
- Transição de fase na espinha: shimmer no passo novo
- Chegada de `escalation`: slam entrance no card (0.4s cubic-bezier)
- `clock_state` mudando pra `critical`: pulso vermelho contínuo no relógio
- `dossiers` chegando: fade-in da rota `/dossier/...` + toast `"Dossiê pronto"`

Todas as animações **são ligadas a mudanças de dado Realtime**, não a timers.

---

## 15 · Checklist do que precisa acontecer visualmente para o pitch fluir

- [ ] Countdown gigante muda de verde → âmbar → vermelho sem intervenção
- [ ] Três colunas discam, atendem, conversam em paralelo (transcrição rolando)
- [ ] Contador POLICY BLOCKS incrementa quando o modelo tenta valor não autorizado
- [ ] Quote comparison table se preenche à medida que as cotações chegam
- [ ] Coluna vencedora fica marcada; as outras duas fazem fade e stampam "released"
- [ ] Read-back aparece no log de read-backs
- [ ] Commitment surge na lista com `anchor_state = 'pending'`, depois vira `anchored`
- [ ] Clique no ▶ toca o trecho exato (esse é O momento da defesa técnica)
- [ ] Card `disrupted` (âmbar) surge pendurado no phase rail
- [ ] Card `renegotiating` (azul) substitui
- [ ] Card `escalated` (vermelho pulsante) expande no painel de escalação com a conta lado a lado
- [ ] Botão APROVAR é clicado, phase rail volta pra `resolved` → `committed`
- [ ] Commitment novo (9.200) aparece com badge "aprovado por humano"
- [ ] Recap chega em `recap_deliveries` com `status = 'sent'`
- [ ] `operations.phase → 'closed'`, countdown congela com "19h de folga"
- [ ] Link "Ver dossiê" aparece no top bar
- [ ] Página do dossiê traz `headline`, `financial`, `operational`, `timeline`, `commitments` com áudio, `escalations` com a conta

Se todos esses ✅ estiverem acesos com o `demo_driver.py --fast` rodando no backend, o painel está pronto para o palco.
