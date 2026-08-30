# Demo Script · How the Phase Rail Advances While You Talk

The agent is Amarra, calling on behalf of **Textiles Pacífico**. You play the carrier who answered the phone. The **panel** should march through the spine in real time as you speak.

Target rate: **8,000 MXN** · Ceiling: **9,000 MXN** · Pickup window: Thursday 08:00 – 12:00 · Container MSKU 784 2219 · Manzanillo → Guadalajara.

---

## The full path (happy path)

```
DETECTED → MANDATE ISSUED → MARKET OPEN → NEGOTIATING → RESERVED
    → COMMITTED → VERIFIED → CLOSED
```

- **DETECTED / MANDATE ISSUED / MARKET OPEN** — happen automatically the moment you press **Start scenario** in the panel. Container discharge → ceiling/target computed → 3 carriers dialed in parallel.
- **NEGOTIATING** — flips when you answer the phone.
- **RESERVED** — flips when you say a number **at or below 8,000**.
- **COMMITTED** — flips when you say **"yes"** to the read-back.
- **VERIFIED → CLOSED** — flip a few seconds after you hang up, once Deepgram anchors the words in the recording and the recap email goes out.

---

## The dialogue (with what triggers each phase)

Agent lines are the ones Amarra will actually say. Your lines are examples — say whatever you want; the flow adapts.

### Opening — DETECTED → NEGOTIATING

> **Amarra:** Hello, this is the assistant from Textiles Pacifico. Do you have a minute?
>
> **You:** Yeah, go ahead. *(Any acknowledgement works: "sure", "yes", "what do you need?")*

> **Amarra:** We just cleared container MSKU 784 2219 in Manzanillo. Drayage to Guadalajara, pickup Thursday between eight and noon. What's your rate today?

*Panel: `NEGOTIATING` lights up.*

---

### First offer — stays in NEGOTIATING (counter-offer laddered)

> **You:** I can do it for eight thousand nine hundred pesos.

> **Amarra:** I have a better offer on this lane. Can you come down to 8,200 pesos?
> *(Policy computed this — not the LLM. 8900 is above target 8000 but ≤ ceiling 9000.)*

*Panel: `NEGOTIATING` still, one row appears in the quote table with `ask: 8,900`.*

**If you say 9,500 instead:** *"That's above what I can authorize on this lane. Thanks, but I can't close on that."* — flow stays in NEGOTIATING, but the row shows `denied`.

---

### Second offer — RESERVED (buy-it-now)

> **You:** Okay, I can do eight thousand.

> **Amarra:** Closed at 8,000 pesos. I'll send you the confirmation now.

*Panel: `NEGOTIATING → RESERVED` (lock taken in Postgres). The other two carrier calls end politely: "I appreciate your time. On this shipment we'll close with another option, but let's stay in touch for the next one."*

**If you say anything above 8,000 (but ≤ 9,000):** flow stays in NEGOTIATING, agent keeps countering. Eventually the escalation band kicks in.

---

### Read-back — RESERVED → COMMITTED

> **Amarra:** Let me confirm: 8,000 pesos, pickup Thursday 10:00. Is that correct? I need an explicit yes to close.

> **You:** Yes, that's right.

*Panel: `RESERVED → COMMITTED`.* A row lands in `commitments` with `state=confirmed` and the exact quote of your "yes".

**If you say "yes but change the time":** classify_response returns `rejected` (never confirmed). Agent asks *"Got it, let's fix that. What's the correct value?"* — stays in RESERVED.

**If you say "maybe" / "I think so" / "sounds okay":** returns `ambiguous`. Agent re-reads once. Two ambiguous in a row → escalates.

---

### Wrap-up — COMMITTED → (hangup) → VERIFIED → CLOSED

> **Amarra:** Closed. I'll send you the written confirmation right now. Thank you.

*The call ends. Twilio uploads the recording (usually 3–8 seconds later). The webhook fires `verify_call`, Deepgram nova-3 extracts words with timestamps, each commitment gets anchored, the recap email goes to `eduardooliveiira307@gmail.com` + judges (BR + AR).*

*Panel: `COMMITTED → VERIFIED → CLOSED`, all within ~10 seconds after hangup. Recap card appears with playable audio clip of your "yes".*

---

## Branch: DISRUPTED → RENEGOTIATING

Say **after** the read-back has been confirmed (or in a follow-up inbound call):

> **You:** Hey, the truck just broke down. I can't make Thursday.

> **Amarra:** Understood, thanks for letting me know. I'll re-open the market and get back to you within the hour.

*Panel: `COMMITTED → DISRUPTED → RENEGOTIATING`. Amarra dials the runner-up automatically, using the auction_quotes table to find the second-best carrier still within the ceiling.*

---

## Branch: ESCALATED → RESOLVED

Say something inside the **escalation band** (between ceiling 9,000 and break-even 10,400):

> **You:** The best I can do is nine thousand two hundred pesos.

> **Amarra:** That's above what I can authorize on this lane. Thanks, but I can't close on that. Give me one moment, I'll bring my supervisor onto the line.

*Panel: `NEGOTIATING → ESCALATED`. Supervisor gets whispered onto the conference (mid-call, nobody hangs up — that's R6). Supervisor either approves (→ RESOLVED → RESERVED) or refuses (→ RESOLVED → FAILED).*

---

## What breaks the flow (things to NOT say if you want the happy path)

- **Silence for 12+ seconds** — the silence watchdog nudges twice ("Are you still there?", "Can you hear me okay?"), then hangs up with a summary. Panel goes to CLOSED with `outcome=silence_timeout`.
- **Contradicting yourself mid read-back** ("yes… actually no, make it 8,500") — read-back token invalidates, re-reads, and after 3 attempts escalates.
- **Insisting on a value above 10,400** (break-even + demurrage) — policy refuses without escalating. No human would approve losing money that way.

---

## What controls the pacing

- **TTS speed** — [amarra/app/phase4_negotiating.py](app/phase4_negotiating.py) `_slow()` wraps every outgoing utterance in `<speak><prosody rate="90%">` with `<break time="250ms"/>` between sentences. If the pace still feels off, drop to `85%` or bump the break to `350ms`.
- **Voice** — `voice="Rachel"` (ElevenLabs, clear medium-paced). Change in [amarra/app/twilio_voice.py](app/twilio_voice.py) `agent_twiml()`.
- **Model** — `gpt-4.1-mini` (env `AGENT_MODEL`). Bigger models add latency, small ones stay snappy.

---

## Start the demo

From the panel (https://nextwave-hackathon.lovable.app): press **Start scenario**.

Or via curl:

```bash
curl -X POST https://clique-lukewarm-frail.ngrok-free.dev/demo/scenario/full
```

Then answer the phone.
