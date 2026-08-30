# Flight Log · Amarra

Narrative log of the architecture, product, and infrastructure decisions taken while building Amarra for the NextWave Hackathon 2026 · Challenge 04 "The Agent on the Line".

Each entry has: **decision**, **alternatives considered**, **why**, **consequence** (what that decision forced downstream).

---

## D01 · Pick "commitment" as the system's atomic unit, not "call"

**Alternatives:**
1. Model as transcript + later LLM extraction
2. Model as intents + entities detected per call
3. Model as **verified commitments** that only exist when anchored in the audio ✓

**Decision:** #3.

**Why:** The challenge is literal — "commitments, not transcripts." A transcript is weak audit because the LLM can hallucinate; a commitment anchored in the audio + confirmed by read-back + tied to the mandate has the properties of a contract. That becomes the product's atom and also opens the door to on-chain receivables in the future (design in INBOUND_PIPELINE.md).

**Consequence:** All of phase 6 (read-back) and phase 7 (anchor) exist because of this. Without the right atom, they'd be cosmetic features; with it, they became system invariants.

---

## D02 · 8 phases + 4 branches as an explicit spine, with guards inside advance()

**Alternatives:**
1. Free states, each endpoint changes whatever it wants
2. Lightweight state machine (only validates allowed transitions)
3. State machine **with semantic guards** that codify invariants ✓

**Decision:** #3.

**Why:** If `verified` only requires a valid transition, the phase can advance without an anchored commitment. If `closed` only requires a valid transition, the operation closes without a recap sent. If guards query the database (`SELECT count(*) FROM commitments WHERE anchor_state='anchored'` before allowing `verified`), the panel LITERALLY cannot lie.

**Consequence:** `phases.py::advance()` calls `_guard()` which queries the DB. That's slow compared to pure state machines (~50ms per transition vs microseconds), but the cost is worth it — the pitch can say "each phase codifies an invariant" and show the SQL.

---

## D03 · Pure policy engine (no LLM) — the model NEVER speaks a number it invented

**Alternatives:**
1. Let the model negotiate freely and check afterwards
2. Model negotiates, policy "reviews" at the end
3. Model **calls a tool** `respond_to_price`, policy **decides**, agent **says the exact phrase** returned by policy, without going through the model again ✓

**Decision:** #3 + a safety gate (`gate_text`) that blocks any non-pre-approved value that leaks.

**Why:** There's a published 2026 benchmark showing frontier models violate their mandate even when they negotiate well — economic reasoning and constraint satisfaction are decoupled in the model. So the constraint cannot live in the model. That's why policy_events has 800+ pytest cases with the invariant "never ALLOW above the ceiling."

**Consequence:** All the counter-offer logic is pre-computed in phase 2 (`concession_ladder`). The model is a dumb client of the policy engine.

---

## D04 · Mandate as canonical HASH (authority identity)

**Alternatives:**
1. Mandate is just a row in `mandates` with target/max
2. Mandate has simple versioning (`updated_at`)
3. Mandate is a **hash of canonical form** that appears on every `policy_events` and `commitments` ✓

**Decision:** #3.

**Why:** The challenge asks "under which mandate" (R3 of R4). If someone changes the ceiling mid-operation, the hash changes and the auditable trail shows exactly under which authority each decision was made. Same idea as a git commit hash, but for delegated authority.

**Consequence:** Phase 2 has `canonicalize()` + `mandate_hash()`. Every `policy_events` and `commitments` row carries `mandate_hash text`. Route `/phase2/verify/{op_id}` recomputes the hash from the stored canonical — divergence proves tampering.

---

## D05 · Pre-computed escalation band (the "good and forbidden" zone)

**Alternatives:**
1. Escalate whenever `ask > max_rate` (binary behavior)
2. Let the model decide when to escalate
3. **Pre-compute** in phase 2 the band `[max_rate, break_even]` as "escalation_band". If `ask` falls into it, escalate; if above break-even, refuse and move on. ✓

**Decision:** #3.

**Why:** Between the ceiling and the break-even point there's a zone where closing is **economically correct AND politically forbidden**. The agent escalates because the system NAMED that band before the first call. This separates "the agent got confused" from "the system predicted this situation." In the pitch's case, it's Transportes Ruiz's 9200 pesos — Amarra refuses because ceiling=9000, but escalates because break_even=10400 (economically better than losing a day of demurrage).

**Consequence:** `escalation_triggers` in the mandate includes `within_escalation_band`. The escalation card renders the math side-by-side (on-time option vs late option) with "exceeds mandate by X pesos" — the human decides in 9 seconds.

---

## D06 · ATOMIC reservation lock in Postgres (not asyncio.Lock)

**Alternatives:**
1. `asyncio.Lock` in-process (works with 1 worker)
2. Lock via Redis / distributed lock
3. **`UPDATE ... WHERE reserved_by IS NULL` inside `SELECT FOR UPDATE`** — Postgres ✓

**Decision:** #3.

**Why:** The first version used asyncio.Lock. Falls apart at the first serious juror question: "what if you scale to 2 workers?". Postgres already has an atomic primitive for this (row lock). Zero extra infra, and the ceiling is re-verified INSIDE POSTGRES — belt and suspenders beyond the policy engine.

**Consequence:** Phase 5 has a stored function `try_reserve_auction(op_id, call_id, amount, reason)` that does the atomic UPDATE. The Python client is 3 lines. Wins points in the technical defense: "holds with 1 worker or with 10."

---

## D07 · Backend never talks to the frontend — only writes to Supabase

**Alternatives:**
1. Own WebSocket from backend to panel
2. Server-Sent Events (SSE)
3. **Supabase Realtime pub/sub** — backend only writes, panel only reads ✓

**Decision:** #3.

**Why:** Eliminates all the complexity of: keeping panel connections alive, WebSocket authentication, WS CORS, reconnection. Supabase Realtime is WebSocket already solved. Backend stays stateless as far as the panel is concerned.

**Consequence:** RLS open for anonymous reads (it's a demo). Panel uses `supabase.channel().on('postgres_changes', ...)` for 13 tables. The Lovable prompt literally says "subscribe, don't poll."

---

## D08 · ConversationRelay instead of Media Streams (Twilio)

**Alternatives:**
1. Twilio Media Streams: raw audio stream, you handle STT/TTS/VAD/barge-in
2. **Twilio ConversationRelay: STT + TTS + VAD + barge-in built in, you only write the conversation WebSocket** ✓

**Decision:** #2.

**Why:** Media Streams saves 2 weeks if you need deep audio control (background music, custom mixer, etc). Not our case — Amarra just needs to "receive transcription, respond with text, survive interruption." ConversationRelay delivers that and more: `interruptible="speech"`, `reportInputDuringAgentSpeech`, native Deepgram nova-3, ElevenLabs TTS.

**Consequence:** All of phase 4 is 300 lines of Python. If it were Media Streams, it'd be ~2000 lines + Deepgram streaming integration + managing audio queues.

---

## D09 · TwiML App + Conference (not direct `<Dial><Number>`)

**Alternatives:**
1. Direct `<Dial><Number>` — simpler for 1-to-1
2. **`<Dial><Conference>` + agent-leg injection** ✓

**Decision:** #2.

**Why:** Without Conference, you can't inject a human later without cutting the audio. And injecting a human without cutting audio is requirement **R6** of the challenge (mid-call escalation). If the call isn't in a Conference from second zero, escalation requires drop+reconnect (loses context, loses robustness).

**Consequence:** Every call is born inside a `<Conference>`. Escalation uses `join_human(coaching=True)` — supervisor enters MUTED, agent hears, when `coaching=False` the human speaks to everyone. Nobody hung up. R6 is one line of code, not an architecture.

---

## D10 · Deepgram nova-3 post-call (not real-time during the call)

**Alternatives:**
1. Deepgram nova-3 real-time during the call, anchor words as they arrive
2. **Record the entire conference; anchor AFTERWARDS via Deepgram batch** ✓

**Decision:** #2.

**Why:** ConversationRelay already gives transcription for real-time decision making (via Twilio's own Deepgram config). Needing WORD-LEVEL TIMESTAMPS for anchoring only makes sense post-call, when you have the complete commitment to look up in the audio. Running 2 Deepgram pipelines (real-time + batch) would be expensive without gain.

**Consequence:** Phase 7 downloads the Twilio recording, sends bytes to Deepgram, receives words with start/end, matches each `commitments.quote` against the index. `number_variants` generates "ocho mil cuatrocientos" when the quote is "8400" and vice versa — without this, anchoring fails on spoken numbers.

---

## D11 · Read-back token (the "yes" bound to specific values)

**Alternatives:**
1. Accept counterparty's "yes" as generic confirmation
2. Accept "yes" only within a specific time window
3. **Hash of the slots ("read_back_token"); if any value changes, the token changes and the old "yes" becomes `superseded`** ✓

**Decision:** #3.

**Why:** Counterparty says "yes, 8500, Thursday 10am" and then changes to "9000, Friday." The first "yes" doesn't apply to the second. Token = hash of the values at the moment of the read-back; if any value changed, token changes, `outcome='superseded'`, agent re-reads. And `classify_response` is conservative — silence, "uh-huh", hedge never become yes.

**Consequence:** Phase 6 has PHRASES + classify_response + read_back_token + 28 tests covering every yes/no/ambiguous variant. Trial by fire ("agree and then change") has a pre-tested response.

---

## D12 · Phases 1-8 as SEPARATE modules, not god-class

**Alternatives:**
1. A single `amarra_engine.py` with all phases
2. **`phase1_detected.py` through `phase8_closed.py` + `phase_disruption.py`**, each with its own router ✓

**Decision:** #2.

**Why:** Makes technical defense easier ("show me phase 5") + makes test isolation easier (each phase has its own test_phaseN.py). Also maps 1:1 to the panel's visual rail, which reduces cognitive load for the juror to follow the demo.

**Consequence:** 9 `phase*.py` files, each ~200-400 lines. main.py just does orchestration. Cost: importing between phases requires care (phase 4 imports phase 5 and 6, but 5 and 6 can't import phase 4). Circular imports resolved via late-import inside functions.

---

## D13 · Auto-reset of the operation in `/demo/dial-market`

**Alternatives:**
1. Each dispatch requires manual reset via SQL
2. Separate endpoint `/demo/reset`
3. **`/demo/dial-market` does auto-reset unless `reset: false` is passed** ✓

**Decision:** #3.

**Why:** Without this, every test of the "OPEN MARKET" button in the panel hits admit() with "operation is in 'negotiating'". The panel button becomes one-click-and-works. Trade-off: if you WANTED to preserve the previous operation (for audit), you have to explicitly pass `reset:false`.

**Consequence:** `_demo_reset()` clears `calls`, `auctions`, `phase_events` for the operation and puts it back to `mandate_issued`. Preserves `mandates` (hash doesn't change). Endpoint `/demo/reset` also exposed for explicit reset.

---

## D14 · Default language = English (AGENT_LANG=en), not Spanish

**Alternatives:**
1. Spanish default (the case is Manzanillo, Nauta's market is LatAm)
2. **English default; pt/es as fallbacks when the carrier explicitly speaks them** ✓

**Decision:** #2.

**Why:** NextWave judge is international (Y.uno, Yuno). English is lingua franca. The challenge's bonus B2 allows language mixing — implemented via `_switch_language` which senses language change via Deepgram and reconfigures TTS on-the-fly. If the juror wants to test in Spanish, the agent follows along.

**Consequence:** Every policy phrase has 3 branches (en/es/pt). Spanish tests preserved via `Mandate.lang` default "es" (only the runtime session uses "en" via env var). PHRASES dict + `_lang_key` helper.

---

## D15 · SMS DROPPED — email is the sole R3a channel

**Alternatives:**
1. SMS via Twilio (~$0.03/msg to BR)
2. SMS + email
3. **Email only** ✓

**Decision:** #3, taken on 2026-08-30 afternoon.

**Why:** SMS US→BR is frequently filtered by Brazilian carriers (Vivo, Claro, TIM). We tested — worked for the first 3 short messages but failed on the real recap (multi-segment with accents). WhatsApp Business API would be a robust alternative but requires Meta approval (days). Email via Resend works globally without restrictions and the challenge says "(SMS/email)" with a slash — one satisfies.

**Consequence:** `send_recap_sms` deleted. `/demo/test-sms` endpoint gone. Cleaner codebase for the pitch — no need to explain "why SMS fails." Trade-off: we lose channel redundancy. Mitigation: `RECAP_TO` + `RECAP_CC` comma-separated for multiple emails (jurors included).

---

## D16 · Ngrok instead of real deploy (Fly.io, Railway)

**Alternatives:**
1. Real deploy on Fly.io / Railway (backend 24/7)
2. **Ngrok + local laptop** ✓

**Decision:** #2.

**Why:** Ngrok reserved domain (free) solves the "public HTTPS for Twilio + Lovable to talk to the backend" problem in 5 minutes. Real deploy would take 30-40 min of setup + first failure. Trade-off: laptop must be running during the demo. Acceptable for the hackathon format.

**Consequence:** `PUBLIC_HOST=clique-lukewarm-frail.ngrok-free.dev` in `.env`. Script `start_all.ps1` boots uvicorn + ngrok in one click. If one day migrating to real deploy, just change `PUBLIC_HOST` — code doesn't change.

---

## D17 · Auto-commit + push after every change that passes tests

**Alternatives:**
1. Ask before each commit
2. Commit small changes, ask before big ones
3. **Auto-commit + push after `pytest` green** ✓

**Decision:** #3, formalized on 2026-08-30 afternoon after user confirmed preference.

**Why:** Speed — hackathon is speed above elegance. Each round-trip "should I commit?" costs 30s. Saved to the assistant's permanent memory so future sessions honor it.

**Consequence:** Standard commit format: short imperative title + body with context + "N tests still green" + Co-Authored-By. Push directly to `main` (the primary branch, same one Lovable uses). Exception: big schema change, public API refactor, or anything affecting the pitch — still ask first.

---

## D18 · Jurors as config, not hard-code

**Alternatives:**
1. Hard-code juror phone numbers in the code
2. Env var per juror
3. **`judges.json` with structured roster + endpoint `/demo/call-judge/{id}`** ✓

**Decision:** #3.

**Why:** Jurors can change until pitch day. Config in a separate file is edit-without-touching-code. The endpoint uses the callback pattern (Twilio dials them, zero cost on their side). `RECAP_CC` in `.env` makes the recap email automatically land in their inbox.

**Consequence:** `judges.json` has Walter (BR) and Denis Dvoretskikh (AR). Denis is AR — documented flag that requires Geo Permission ARG on Twilio before the first `/demo/call-judge/denis`.

---

## D19 · Mobile-first frontend (430px) even when running on desktop

**Alternatives:**
1. Traditional desktop layout (3 columns side by side)
2. Responsive (same UI, adaptive layouts)
3. **Fixed mobile-first (max-width 430px, tabs instead of columns)** ✓

**Decision:** #3.

**Why:** The operations panel is mid-call consumption, not browsing. Mobile forces clear visual hierarchy — huge countdown, phase rail, one tab per view. Also makes it easier for the juror to open on their own phone during the demo.

**Consequence:** Lovable prompts (`LOVABLE_PROMPT_MOBILE_CALL.md`, `LOVABLE_PROMPT_OUTBOUND_BUTTON.md`) describe bottom-sheet-style, 56px pill buttons, tabs instead of sidebar. Lovable implemented (commits from bot `gpt-engineer-app`).

---

## D20 · Automatic renegotiation with runner-up (disruption phase)

**Alternatives:**
1. When `report_disruption` fires, just mark the operation as disrupted and stop
2. Mark disrupted + escalate for the human to decide what to do
3. **Mark disrupted + auto-dispatch callback to the second-place from the last auction (within ceiling)** ✓

**Decision:** #3.

**Why:** Expected result #3 of the challenge requires renegotiation without exceeding the mandate. If we wait for a human, we lose free-time (the clock!). Runner-up was already negotiated, `auction_quotes` has the final price — if it still fits under the ceiling, it's the right auto decision. If it doesn't fit → escalate.

**Consequence:** `phase_disruption.py::renegotiate_with_runner_up` reads `auction_quotes`, filters `winner=false` + `final_ask <= max_rate`, sorts by price, dials the winner via `tw.dial_counterparty`. If no viable one, calls `_escalate_no_runner_up`.

---

## D21 · Dossier as a single auditable artifact (nested JSON)

**Alternatives:**
1. Multiple queries the juror has to cross-reference
2. Aggregated SQL view
3. **Row in `dossiers` with JSON blob containing everything: financial, operational, timeline, commitments, comparison, escalations, mandate_hash, headline** ✓

**Decision:** #3.

**Why:** R4 of the challenge is "auditable trail". If the juror opens a URL and sees everything, R4 is literally answered. JSON format lets us render however we want in the panel + consume via API + upload on-chain as IPFS metadata in the future.

**Consequence:** Phase 8 has `build_dossier()` that aggregates 6 sources. Frontend route `/dossier/:ref`. Endpoint `/phase8/dossier/{op_id}`. R3a recap is the same thing in human text (email).

---

## D22 · 20-min choreography with single endpoint `/demo/scenario/full`

**Alternatives:**
1. Each phase is a separate curl, juror watches you type
2. Bash script that sequences curls
3. **`POST /demo/scenario/full`** that does reset → issue mandate → open market and returns plan ✓

**Decision:** #3.

**Why:** A 7-min pitch can't have "wait, let me type the next curl". Single button. `demo_scenario.py` polls `/demo/scenario/status/{ref}` and shows a 7/6 green scorecard in real time.

**Consequence:** `demo_scenario.py` + `OBJECTIVES_TO_RESULTS.md` + `SYNC_STATUS.md` document the choreography. Run during the pitch: 1 kickoff command + 1 close command, the rest happens via real calls.

---

## D23 · Permissive CORS (`allow_origins=["*"]`) on the backend

**Alternatives:**
1. Explicit origin whitelist (Lovable, localhost)
2. **Wildcard `*` with `allow_credentials=False`** ✓

**Decision:** #2.

**Why:** Hackathon mode. Wildcard is safe when there are no cookies (credentials=False enforces this). The Lovable panel + dev `curl` + the developer's browser preview all pass without drama. Trade-off: any external site can call the backend. Acceptable for demo, would be restricted in production.

**Consequence:** `main.py` has 8 lines of `app.add_middleware(CORSMiddleware, ...)`. Escape hatch: if a juror opens the panel on their phone, it works without extra config.

---

## D24 · Git workflow — auto-commit directly to `main` (no PR)

**Alternatives:**
1. `main` protected, everything via reviewed PR
2. `dev` branch + PR to `main` per block
3. **Directly to `main`, no intermediate branch** ✓

**Decision:** #3, after trying #2 and finding out Lovable also writes to `main` directly.

**Why:** Lovable auto-commits to `main`. If we use `dev`, every PR needs to rebase against Lovable. High overhead for a hackathon. Directly to `main` naturally syncs with Lovable.

**Consequence:** `dev` branch deleted. All pushes go to `main`. Trust in `pytest` green as the gate.

---

## Flight metrics

- **34 commits** between start and this log
- **9 `phase*.py` files** in the spine (~2500 lines)
- **9 SQL migration files** (~500 lines)
- **951 pytest cases**, ~15 seconds total
- **13 REST demo endpoints** + 9 phase endpoints + 6 Twilio webhooks + 1 WebSocket
- **13 Supabase tables** + Realtime + Storage
- **5 Lovable prompts** consumed (`LOVABLE_PROMPT_*.md`)
- **Zero heavy dependencies outside the stack** — no Redis, RabbitMQ, K8s, Elasticsearch

## Last decision · when to stop

**D25 — Stop shipping features, focus on proving live:** from now until the demo, every minute goes to running `dial_market` for real + real inbound call + real `close` + generating the dossier. Each objective that turns ✅ on the status view is more valuable than any new feature. The software is ready; it needs to be used.

---

_Log compiled on 2026-08-30, afternoon. Living version — each future decision becomes D26, D27..._
