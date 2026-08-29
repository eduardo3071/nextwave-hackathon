# Amarra — Agente de Voz para Negociação de Frete (NextWave 2026)

Agente de voz que negocia frete dentro de um mandato e devolve **compromissos amarrados ao áudio**, não transcrições. Desafio 04 do NextWave Hackathon 2026 — "The Agent on the Line".

**Contexto e narrativa do pitch:** [O-Caso-Manzanillo.md](O-Caso-Manzanillo.md). **Código do backend + fases:** [amarra/](amarra/). **Painel:** projeto Vite/React na raiz (`src/`), publicado em https://nextwave-hackathon.lovable.app.

## A tese

O agente resolve sozinho tudo que cabe no mandato, e traz ao humano exatamente uma decisão — com a conta já feita.

Contra os dois modos de falha que matam agentes em produção: ultrapassar autoridade (risco jurídico) e escalar tudo (call center caro).

## Arquitetura em uma linha

```
Twilio (Conference + ConversationRelay)
   ⇅ WebSocket + webhooks
FastAPI  ──escreve──▶  Supabase (Postgres + Realtime)  ──empurra──▶  Lovable
```

O backend **nunca** fala com o frontend. Escreve linhas; o Realtime entrega. Zero WebSocket próprio, zero polling, zero CORS.

## Regras inegociáveis

1. **O modelo NUNCA fala um número que ele inventou.** O LLM chama `respond_to_price`, a política decide e devolve a frase EXATA, o agente fala essa frase. Uma terceira camada (`gate_text`) bloqueia qualquer valor não autorizado que escape.
2. **Sem âncora no áudio, o campo não entra.** A ancoragem por Deepgram nova-3 acontece depois da chamada; alucinação vira falha de gravação, nunca dado errado.
3. **Nenhuma chamada fecha sozinha.** Ela PEDE reserva ao lock do leilão; só uma recebe. Enquanto não confirmado, o agente diz "vou confirmar e te retorno", nunca "fechado".
4. **Toda chamada nasce dentro de uma `<Conference>`.** Sem isso, não dá para injetar um humano depois sem cortar o áudio — e injetar humano sem cortar áudio é o requisito R6.
5. **Pytest é a asserção da política.** `tests/test_policy.py` — ~878 casos, <1s, nenhum ALLOW acima do teto. Rodar AO VIVO na defesa técnica.
6. **A barra de fases é a asserção do produto.** Cada transição em `app/phases.py` tem uma guarda: `committed` exige lock, `verified` exige compromisso ancorado, `closed` exige recap enviado. Não dá para o painel mentir.

## Stack fixa

Python 3.12, FastAPI, Twilio (Conference + ConversationRelay), Deepgram nova-3, OpenAI (`gpt-4.1-mini` na conversa), Supabase (Postgres + Realtime, service_role no backend / anon no painel), Vite + React + Tailwind (painel Lovable).

**Não construir:** WebSocket próprio para o painel, autenticação de usuário, multi-organização, filas externas (Redis/RabbitMQ), banco além do Supabase.

## Árvore do projeto

```
nextwave-hackathon/
├── amarra/                        # backend + fases (o núcleo)
│   ├── app/
│   │   ├── main.py                # FastAPI: /auction/start, /escalate, /twiml/*, /ws
│   │   ├── auction.py             # leilão + LOCK de reserva (Pilar 03)
│   │   ├── policy.py              # policy engine PURO, sem LLM (Pilar 01)
│   │   ├── evidence.py            # ancoragem via Deepgram (Pilar 02)
│   │   ├── phases.py              # máquina de fases: 8 espinha + 4 desvios + guardas
│   │   ├── agent.py               # sessão do ConversationRelay
│   │   ├── twilio_voice.py        # Conference + join agente/humano/escalação
│   │   └── db.py                  # cliente Supabase
│   ├── db/
│   │   ├── schema.sql             # tabelas + Realtime + RLS + seed do caso
│   │   └── 002_phases.sql         # phase_events + advance_phase() atômico
│   ├── tests/test_policy.py       # a prova que vai para o palco
│   ├── demo_driver.py             # ensaia todas as fases sem telefonar
│   ├── 00_smoke_test.py           # PORTÃO 0: o telefone precisa tocar
│   ├── carriers.json              # mandato + 3 transportadoras
│   ├── .env.example
│   ├── README.md
│   ├── WIRING_PHASES.md           # 6 pontos onde as fases entram no código
│   ├── LOVABLE_PROMPT.md          # prompt inicial do painel
│   └── LOVABLE_PROMPT_PHASES.md   # prompt incremental do phase rail
├── src/                           # painel Vite/React (Lovable)
├── supabase/                      # migrações do Lovable
├── O-Caso-Manzanillo.md           # o pitch e a narrativa
└── CLAUDE.md                      # este arquivo
```

## Os três pilares

| # | O quê | Onde |
|---|---|---|
| 01 | **Policy Guard** — modelo nunca fala número inventado | [amarra/app/policy.py](amarra/app/policy.py) |
| 02 | **Evidência ancorada** — sem âncora no áudio, campo não entra | [amarra/app/evidence.py](amarra/app/evidence.py) |
| 03 | **Leilão com lock** — 3 em paralelo, só um pode fechar | [amarra/app/auction.py](amarra/app/auction.py) |

## As fases (espinha + desvios)

```
detected → mandate_issued → market_open → negotiating
         → reserved → committed → verified → closed
               ▲                        │
               └──── resolved ◄── escalated ◄── renegotiating ◄── disrupted
```

Guardas obrigatórias em `advance()`:
- `MARKET_OPEN` — ao menos 3 transportadoras (codifica R7)
- `RESERVED` / `COMMITTED` — lock tomado
- `COMMITTED` — valor ≤ teto
- `VERIFIED` — pelo menos um compromisso ancorado no áudio (invariante do Pilar 02)
- `CLOSED` — recap enviado (R3a)

Ver [amarra/WIRING_PHASES.md](amarra/WIRING_PHASES.md) para os 6 pontos onde as fases entram no código existente.

## Requisitos do enunciado

| ID | Requisito | Onde |
|---|---|---|
| R1 | Outbound real pela rede telefônica | `twilio_voice.dial_counterparty` |
| R2 | Inbound compreendido e agido | `POST /twiml/inbound` |
| R3a | Recap escrito pós-chamada | `evidence` + e-mail |
| R3b | Compromisso ligado ao timestamp do áudio | `evidence.anchor` |
| R4 | Call brief estruturado | `AgentSession.close` |
| R5 | Conversa e sistema consistentes | `policy.gate_text` + `policy_events` |
| R6 | Escalação mid-call sem desligar | `twilio_voice.join_human` (coach whisper) |
| R7 | 3+ em paralelo, comparação auditável | `auction.py` |

## Ordem de trabalho

1. **PORTÃO 0** — `python amarra/00_smoke_test.py +55...`. Se o telefone não toca, nada mais importa.
2. **Schema** — aplicar `amarra/db/schema.sql` e `amarra/db/002_phases.sql` no SQL Editor do Supabase. É o contrato entre backend e painel.
3. **Motor** — o backend sobe com `uvicorn app.main:app --port 8000` a partir de `amarra/`. `pytest tests/ -q` precisa passar antes de cada commit.
4. **Painel** — o Lovable já subiu com o prompt de [amarra/LOVABLE_PROMPT.md](amarra/LOVABLE_PROMPT.md); o incremento do phase rail está em [amarra/LOVABLE_PROMPT_PHASES.md](amarra/LOVABLE_PROMPT_PHASES.md).
5. **Ensaio** — `python amarra/demo_driver.py --fast` percorre todas as fases sem telefonar, para trabalhar no painel sem depender da telefonia.

## Como pedir mudanças

Trabalhe em UMA fase / UM pilar por vez. Ao acabar, rode `pytest`, faça commit com o nome do que mudou, e pare. Não refatorar código adjacente por conta própria — hackathon é velocidade acima de elegância.
