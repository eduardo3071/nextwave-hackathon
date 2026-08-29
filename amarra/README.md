# Amarra

Agente de voz que negocia frete dentro de um mandato e devolve **compromissos
amarrados ao áudio**, não transcrições.

NextWave Hackathon 2026 · Desafio 04 — The Agent on the Line

## Arquitetura em uma linha

```
Twilio (Conference + ConversationRelay)
   ⇅ WebSocket + webhooks
FastAPI  ──escreve──▶  Supabase (Postgres + Realtime)  ──empurra──▶  Lovable
```

O backend **nunca** fala com o frontend. Escreve linhas; o Realtime entrega.
Zero WebSocket próprio, zero polling, zero CORS.

## Os três pilares

| | O quê | Onde |
|---|---|---|
| 01 | **Policy Guard** — o modelo nunca fala um número que ele inventou | `app/policy.py` |
| 02 | **Evidência ancorada** — sem âncora no áudio, o campo não entra | `app/evidence.py` |
| 03 | **Leilão com lock de reserva** — 3 em paralelo, só um pode fechar | `app/auction.py` |

## A prova

```bash
pytest tests/ -q       # 878 casos, <1s, nenhum ALLOW acima do teto
```

## Rodar

```bash
pip install -r requirements.txt
cp .env.example .env            # preencher
psql < db/schema.sql            # ou Supabase SQL Editor
python 00_smoke_test.py +55...  # PORTÃO: o telefone precisa tocar
uvicorn app.main:app --port 8000
ngrok http --domain=SEU.ngrok.app 8000
```

Console Twilio: crie uma **TwiML App** apontando para
`https://SEU.ngrok.app/twiml/agent` e cole o SID em `TWIML_APP_SID`.
No número comprado, aponte "A call comes in" para `/twiml/inbound`.

## Requisitos do enunciado

| ID | Requisito | Onde |
|---|---|---|
| R1 | Outbound real pela rede telefônica | `twilio_voice.dial_counterparty` |
| R2 | Inbound compreendido e agido | `POST /twiml/inbound` |
| R3a | Recap escrito pós-chamada | `evidence` + e-mail |
| R3b | Compromisso ligado ao timestamp do áudio | `evidence.anchor` |
| R4 | Call brief estruturado | `AgentSession.close` |
| R5 | Conversa e sistema consistentes | `policy.gate_text` + `policy_events` |
| R6 | Escalação mid-call sem desligar | `twilio_voice.join_human` |
| R7 | 3+ em paralelo, comparação auditável | `auction.py` |

## Fases

Espinha de 8 passos e 4 desvios, com guardas que codificam as invariantes:
`committed` exige o lock de reserva, `verified` exige compromisso ancorado,
`closed` exige recap enviado. A barra de progresso É a asserção.

```bash
psql < db/002_phases.sql          # ou Supabase SQL Editor
python demo_driver.py             # percorre tudo sem telefonar
python demo_driver.py --fast      # sem pausas, para desenvolver a UI
```

Ver `WIRING_PHASES.md` para os seis pontos de integração no código existente.
