# Amarra — Architecture

Voice agent for freight negotiation. Returns **commitments anchored to audio**, not transcripts.

NextWave Hackathon 2026 · Challenge 04 — *The Agent on the Line*

> 📖 **[FLIGHT LOG](FLIGHT_LOG.md)** — every architecture, product and infra decision, with alternatives considered and downstream consequences.

---

## Architecture (one line)

```
Twilio (Conference + ConversationRelay)
   ⇅ WebSocket + webhooks
FastAPI  ──writes──▶  Supabase (Postgres + Realtime)  ──pushes──▶  Lovable
```

The backend **never** talks to the frontend. It writes rows; Realtime delivers them. Zero custom WebSocket, zero polling, zero CORS.

![Architecture diagram](ARCHITECTURE.png)

Full diagram: [ARCHITECTURE.pdf](ARCHITECTURE.pdf) · Regenerate: `python generate_architecture_pdf.py`

---

## Layers

### Frontend — https://nextwave-hackathon.lovable.app
Vite + React + TanStack Router · mobile-first (430px) · Supabase Realtime subscriber

Components: top bar (countdown), phase rail, call dock, quote table, escalation panel, dossier view, recap card.

### Backend — FastAPI + uvicorn (ngrok: `clique-lukewarm-frail.ngrok-free.dev`)
9 routers + 6 Twilio endpoints + WebSocket `/ws`.

| Group | Endpoints |
|---|---|
| **Demo** | `/demo/scenario/full`, `/demo/dial-market`, `/demo/call-me`, `/demo/call-judge/{id}`, `/demo/recap/{op_id}`, `/demo/test-email`, `/demo/scenario/status/{ref}` |
| **Phases** | `/phase1/detect`, `/phase2/issue/{op_id}`, `/phase3/open`, `/phase5/release/{auc_id}`, `/phase6/commitments/{op_id}`, `/phase7/verify/{call_id}`, `/phase8/close/{op_id}`, `/phase8/dossier/{op_id}`, `/disruption/report/{op_id}` |
| **Twilio** | `POST /twiml/inbound`, `POST /twiml/agent`, `POST /twilio/recording`, `POST /twilio/conference`, `POST /twilio/status`, `WS /ws` (ConversationRelay) |

### External services
| Service | Role |
|---|---|
| **Twilio** | Voice + ConversationRelay (calls, conferences, recording) |
| **Deepgram** | `nova-3` ASR (audio → words with timestamps) |
| **OpenAI** | `gpt-4.1-mini` (negotiation reasoning) |
| **Resend** | Email SMTP (R3a recap) |

### Supabase — Postgres + Realtime + Storage
13 tables, RLS off for demo (permissive on read, `service_role` writes).

Core tables: `operations`, `mandates`, `auctions`, `auction_quotes`, `calls`, `utterances`, `policy_events`, `commitments`, `read_backs`, `escalations`, `recap_deliveries`, `dossiers`, `phase_events`. Storage bucket: `call-audio`.

---

## The three pillars

| # | What | Where |
|---|---|---|
| 01 | **Policy Guard** — model never speaks a number it invented | [app/policy.py](app/policy.py) |
| 02 | **Anchored evidence** — no anchor in audio, no field | [app/phase7_verified.py](app/phase7_verified.py) |
| 03 | **Auction with reservation lock** — 3 in parallel, only one can close | [app/auction.py](app/auction.py) |

---

## The 8-phase spine (+ 4 branches)

```
detected → mandate_issued → market_open → negotiating
        → reserved → committed → verified → closed
             ▲                        │
             └──── resolved ◄── escalated ◄── renegotiating ◄── disrupted
```

Mandatory guards inside `advance()`:
- `MARKET_OPEN` — at least 3 carriers (encodes R7)
- `RESERVED` / `COMMITTED` — reservation lock held
- `COMMITTED` — value ≤ ceiling
- `VERIFIED` — at least one commitment anchored in audio (Pillar 02 invariant)
- `CLOSED` — recap delivered (R3a)

---

## Requirements → code

| ID | Requirement | Where |
|---|---|---|
| R1 | Real outbound over the phone network | `twilio_voice.dial_counterparty` |
| R2 | Inbound understood and acted on | `POST /twiml/inbound` |
| R3a | Written recap post-call | `phase7_verified.send_recap` + Resend |
| R3b | Commitment tied to audio timestamp | `phase7_verified.anchor` |
| R4 | Structured call brief | `AgentSession.close` |
| R5 | Conversation and system consistent | `policy.gate_text` + `policy_events` |
| R6 | Mid-call escalation without hanging up | `twilio_voice.join_human` (coach whisper) |
| R7 | 3+ in parallel, auditable comparison | `auction.py` + `auction_quotes` |

---

## Proof

```bash
pytest tests/ -q       # 951 cases, <5s, zero ALLOW above ceiling
```

The invariant is the pitch: **no policy engine test ever authorizes a value above the mandate ceiling**, over ~800 parameterized adversarial asks.

---

## Run

```bash
pip install -r requirements.txt
cp .env.example .env                # fill in the blanks
psql < db/schema.sql                # or Supabase SQL Editor
psql < db/002_phases.sql
python 00_smoke_test.py +55...      # gate 0: the phone has to ring
uvicorn app.main:app --port 8000
ngrok http --domain=YOUR.ngrok.app 8000
```

Twilio console: create a **TwiML App** pointing at `https://YOUR.ngrok.app/twiml/agent` and paste the SID into `TWIML_APP_SID`. On the purchased number, point "A call comes in" at `/twiml/inbound`.

Rehearse without the phone:
```bash
python demo_driver.py --fast        # walks every phase, panel updates via Realtime
```

The agent speaks **English only**. See [FLIGHT_LOG.md](FLIGHT_LOG.md) for the reasoning behind every non-obvious decision.
