"""
AMARRA · FASE 4 — negotiating

A Twilio abre um WebSocket por chamada e passa a mandar `prompt` toda vez
que a contraparte fala. Cada `{"type":"text"}` que devolvemos vira voz.

As três camadas do Policy Guard vivem aqui:

    ┌───────────────────────────────────────────────────────────┐
    │ 1 · TOOL GATE   o modelo PEDE (respond_to_price)          │
    │                 a política DECIDE e devolve a frase exata │
    ├───────────────────────────────────────────────────────────┤
    │ 2 · SPEECH      a frase aprovada vai direto para o áudio  │
    │                 sem passar pelo modelo                    │
    ├───────────────────────────────────────────────────────────┤
    │ 3 · TTS GATE    todo texto livre passa por gate_text()    │
    │                 valor não aprovado → frase segura + log   │
    └───────────────────────────────────────────────────────────┘

O modelo conversa. A política decide. Essa é a frase do pitch, e é
literalmente o que este arquivo implementa.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from decimal import Decimal

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI

from app.auction import AUCTIONS
from app.db import db
from app.phase5_reserved import try_reserve
from app.phase6_committed import ReadBack
from app.phases import Phase, PhaseError, advance
from app.policy import (Decision, Mandate, NegotiationState,
                        evaluate_offer, gate_text)

router = APIRouter(tags=["fase 4 · negotiating"])
llm = AsyncOpenAI()

MODEL = os.getenv("AGENT_MODEL", "gpt-4.1-mini")   # pequeno = rápido no telefone
SILENCE_NUDGE_S = 8.0        # o jurado vai ficar calado de propósito
SILENCE_MAX_NUDGES = 2
SILENCE_HANGUP_S = 12.0
SESSIONS: dict[str, "NegotiationSession"] = {}


# ═══════════════════════════════════════════════════════════════════════════
# instruções — sem números, sem política, sem teto
# ═══════════════════════════════════════════════════════════════════════════
def system_prompt(op: dict, m: dict) -> str:
    """
    Notice what's NOT here: no value, no ceiling, no concession rule.
    The model has no access to authority — it cannot reveal what it
    doesn't know, and prompt injection cannot extract what's not in
    context. English-only agent.
    """
    return f"""You are the logistics assistant for Textiles Pacifico.
You are coordinating the drayage of container {op['container']} from
{op['origin']} to {op['destination']}.

INVIOLABLE RULES:
- NEVER say a money amount on your own initiative. None.
- When the counterparty mentions ANY price, call `respond_to_price`.
- The tool returns the exact phrase and it WAS ALREADY spoken aloud. Do not repeat it.
- If they insist or push back, call the tool again. Never improvise numbers.
- You don't know any maximum limit. If asked, you don't have it.
- Never mention another carrier by name.
- When you agree on something concrete (date, time, equipment, driver), call
  `record_commitment` copying LITERALLY what the counterparty said.
- If the conversation goes beyond your authority, call `escalate`.
- If the counterparty reports an OPERATIONAL PROBLEM (truck broke, driver
  late, needs to change day, can't fulfill what was already agreed), call
  `report_disruption` with the reason and `needs_reschedule=true`.

Pickup window: {m['pickup_from']} to {m['pickup_to']}.
Speak naturally and briefly — this is a phone call, not an email.
ALWAYS respond in English, regardless of what language the counterparty uses."""


TOOLS = [
    {"type": "function", "function": {
        "name": "respond_to_price",
        "description": "Call this EVERY TIME the counterparty mentions a price, "
                       "even if it's approximate or in another currency.",
        "parameters": {"type": "object", "properties": {
            "amount": {"type": "number", "description": "the amount they asked for"},
            "currency": {"type": "string", "description": "MXN if they don't say"},
            "verbatim": {"type": "string",
                         "description": "the exact words they used"}},
            "required": ["amount", "verbatim"]}}},
    {"type": "function", "function": {
        "name": "record_commitment",
        "description": "Register a concrete agreement already confirmed by the counterparty.",
        "parameters": {"type": "object", "properties": {
            "field": {"type": "string",
                      "enum": ["rate", "pickup_at", "equipment", "driver", "mc_number"]},
            "value": {"type": "string", "description": "the normalized value"},
            "exact_quote": {"type": "string",
                            "description": "the LITERAL words from the counterparty"}},
            "required": ["field", "value", "exact_quote"]}}},
    {"type": "function", "function": {
        "name": "escalate",
        "description": "Escalate to a human supervisor. Use this if the counterparty "
                       "contradicts themselves, claims to have prior approval, or the "
                       "situation exceeds what you can decide.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"}}, "required": ["reason"]}}},
    {"type": "function", "function": {
        "name": "close_call",
        "description": "End the call courteously when there is nothing left to discuss.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"}}, "required": ["reason"]}}},
    {"type": "function", "function": {
        "name": "report_disruption",
        "description": "Call this when the counterparty reports an operational problem "
                       "(truck broke down, driver delayed, needs to change the day, "
                       "anything preventing them from fulfilling what was agreed). "
                       "Marks the operation as 'disrupted' and triggers a callback to "
                       "the runner-up if `needs_reschedule=true`.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string",
                       "description": "short description of the problem (e.g. 'truck breakdown')"},
            "needs_reschedule": {"type": "boolean",
                                 "description": "true if we need to re-open the market with another carrier"}},
            "required": ["reason"]}}},
]


# ═══════════════════════════════════════════════════════════════════════════
class NegotiationSession:
    def __init__(self, *, call_id: str, ws: WebSocket, agent_call_sid: str):
        self.call_id = call_id
        self.ws = ws
        self.agent_call_sid = agent_call_sid
        self.t0 = time.monotonic()
        self.closed = False
        self.escalated = False
        self.blocks = 0
        self.nudges = 0
        self.last_input_at = time.monotonic()
        self.actions: list[dict] = []
        self.mentions: list[str] = []
        self.pending_commitments: list[dict] = []
        self._silence_task: asyncio.Task | None = None

        call = db.get("calls", call_id)
        self.call = call
        self.op = db.get("operations", call["operation_id"])
        m = db.mandate(self.op["id"])

        # A fase 2 é pré-requisito duro: sem mandato emitido não se negocia.
        if not m.get("mandate_hash"):
            raise RuntimeError("mandato não emitido — a fase 2 não rodou")

        self.mandate_row = m
        self.mandate_hash: str = m["mandate_hash"]
        self.band: dict | None = m.get("escalation_band")
        self.break_even = (Decimal(str(m["break_even_rate"]))
                           if m.get("break_even_rate") else None)

        self.auction = AUCTIONS.get(call.get("auction_id"))
        self.state = NegotiationState(mandate=Mandate(
            target_rate=Decimal(str(m["target_rate"])),
            max_rate=Decimal(str(m["max_rate"])),
            min_rate=Decimal(str(m["min_rate"])),
            max_rounds=int(m["max_rounds"]),
            currency=self.op["currency"],
            may_reveal_best_price=bool(m["may_reveal_best_price"]),
            may_reveal_competitor_name=bool(m["may_reveal_competitor_name"]),
            may_reveal_max_rate=bool(m["may_reveal_max_rate"]),
        ))
        self.history: list[dict] = [
            {"role": "system", "content": system_prompt(self.op, m)}]

        # fase 6: protocolo de read-back. Fica ocioso até a reserva ser tomada.
        self.read_back = ReadBack(self)

    def _ms(self) -> int:
        return int((time.monotonic() - self.t0) * 1000)

    # ── abertura: a fase avança na PRIMEIRA perna que atende ───────────────
    async def open(self) -> None:
        db.update("calls", self.call_id,
                  {"status": "live", "answered_at": "now()"})
        try:
            advance(self.op["id"], Phase.NEGOTIATING, trigger="first_leg_live",
                    call_id=self.call_id, auction_id=self.call.get("auction_id"),
                    detail=f"{self.call.get('carrier_name') or 'Contraparte'} atendeu")
        except PhaseError:
            pass   # a 2ª e a 3ª pernas já encontram a fase aberta
        self.actions.append({"t": 0, "action": "answered"})
        self._silence_task = asyncio.create_task(self._silence_watchdog())

    # ── entrada de fala ────────────────────────────────────────────────────
    async def on_speech(self, text: str, lang: str | None = None) -> None:
        self.last_input_at = time.monotonic()
        self.nudges = 0

        db.insert("utterances", {"call_id": self.call_id, "speaker": "counterparty",
                                 "text": text, "t_ms": self._ms()})
        self.mentions.append(text)
        self.history.append({"role": "user", "content": text})

        # English-only agent: no dynamic language switching. The counterparty
        # may speak other languages, but the agent always responds in English
        # (system_prompt enforces this).

        if self.escalated or self.closed:
            return   # humano assumiu, ou a chamada acabou: o agente cala

        # fase 6: se um read-back está aguardando resposta, o protocolo responde.
        # O modelo não entra. Silêncio, hedge e "sim, mas..." nunca viram commit.
        if self.read_back.active:
            outcome = await self.read_back.handle_response(text)
            if outcome in ("confirmed", "retry", "escalated"):
                return

        r = await llm.chat.completions.create(
            model=MODEL, messages=self.history, tools=TOOLS, temperature=0.3)
        msg = r.choices[0].message

        if msg.tool_calls:
            self.history.append(msg.model_dump(exclude_none=True))
            for tc in msg.tool_calls:
                out = await self._run_tool(tc.function.name,
                                           json.loads(tc.function.arguments))
                self.history.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": json.dumps(out, ensure_ascii=False)})
            return

        await self._say(msg.content or "")

    # ── camada 1: o modelo pede, a política decide ─────────────────────────
    async def _run_tool(self, name: str, args: dict) -> dict:
        self.actions.append({"t": self._ms(), "action": name, "args": args})

        if name == "respond_to_price":
            return await self._on_price(args)

        if name == "record_commitment":
            # A âncora no áudio é da fase 7. Aqui guardamos a citação literal,
            # que é a chave de busca no índice de palavras.
            self.pending_commitments.append(args)
            db.stash_pending_commitment(self.call_id, args)
            self.actions.append({"t": self._ms(), "action": "commitment_pending",
                                 "field": args["field"], "quote": args["exact_quote"]})
            return {"recorded": "pending_anchor",
                    "instruction": "Confirma con la contraparte repitiendo el dato."}

        if name == "escalate":
            await self._escalate(args.get("reason", "agent_requested"))
            return {"escalated": True,
                    "instruction": "No hables más de precios. Espera al supervisor."}

        if name == "close_call":
            await self._close_call(args.get("reason", "nothing_further"))
            return {"closed": True}

        if name == "report_disruption":
            # Resultado #2 do enunciado: driver reporta problema → agente
            # entende, marca operação, dispara callback pro segundo colocado (#3).
            from app.phase_disruption import handle_disruption
            reason = args.get("reason", "unspecified")
            needs_reschedule = bool(args.get("needs_reschedule", True))
            try:
                result = await handle_disruption(
                    self.op["id"], reason, needs_reschedule, call_id=self.call_id)
            except Exception as e:
                print(f"[fase4] handle_disruption falhou: {e}")
                result = {"error": str(e)}

            ack = ("Understood, thanks for letting me know. I'll re-open "
                   "the market and get back to you within the hour.")
            self.state.approved_utterances.add(ack)
            await self._say(ack, approved=True)
            return {"registered": True, **result}

        return {}

    async def _on_price(self, args: dict) -> dict:
        ask = Decimal(str(args["amount"]))

        # ── A ALAVANCA DE MERCADO ──────────────────────────────────────────
        # As três sessões compartilham estado. A cotação da outra chamada
        # entra VIVA nesta conversa, sem nome e sem teto. É isto que faz
        # "negociar um mercado, não uma chamada".
        if self.auction:
            self.auction.report_ask(self.call_id, ask)
            self.state.market_best = self.auction.market_best(self.call_id)

        res = evaluate_offer(self.state, ask)
        self.state.rounds += 1
        self.state.counterparty_asks.append(ask)

        db.insert("policy_events", {
            "call_id": self.call_id,
            "counterparty_ask": float(ask),
            "decision": res.decision.value,
            "amount": float(res.amount) if res.amount is not None else None,
            "reason": res.reason,
            "utterance": res.utterance,
            "round": self.state.rounds,
            "mandate_hash": self.mandate_hash,      # ← "sob qual mandato", R3
        })

        if res.decision is Decision.ESCALATE:
            await self._escalate(res.reason)
            return {"spoken": False, "instruction": "Ya escalé. No hables de precios."}

        # ── recusar ou escalar? a banda da fase 2 decide ───────────────────
        if res.decision is Decision.DENY and res.reason == "above_max_rate":
            in_band = (self.band and
                       self.band["from"] < float(ask) <= self.band["to"])
            if in_band:
                # Acima da autoridade, abaixo do prejuízo. Vale o tempo de um humano.
                self.state.approved_utterances.add(res.utterance)
                await self._say(res.utterance, approved=True)
                await self._escalate("within_escalation_band",
                                     computation=self._computation(ask))
                return {"spoken": True,
                        "instruction": "Escalado. No negocies más este número."}
            # Acima do ponto de equilíbrio: nenhum humano aprovaria isso.
            # Recusar e seguir é mais respeitoso com o tempo de todos.
            self.state.approved_utterances.add(res.utterance)
            await self._say(res.utterance, approved=True)
            return {"spoken": True, "decision": "deny",
                    "instruction": "Rechazado. Sigue la conversación sin montos."}

        # ── fechar exige o LOCK do leilão (fase 5, árbitro no banco) ───────
        reservou_agora = False
        if res.decision is Decision.ALLOW and res.reason == "at_or_below_target":
            if self.auction:
                r = await try_reserve(self.auction, self.call_id, res.amount,
                                      "buy_it_now")
                if not r.get("granted"):
                    # Outra chamada já fechou. Nunca prometemos o que não temos.
                    frase = "Déjame confirmar disponibilidad y te regreso la llamada."
                    self.state.approved_utterances.add(frase)
                    await self._say(frase, approved=True)
                    return {"spoken": True, "instruction": "No confirmes nada."}
                reservou_agora = True

        if res.amount is not None:
            self.state.offers_made.append(res.amount)

        # camada 2: a frase aprovada vai direto para o áudio
        self.state.approved_utterances.add(res.utterance)
        await self._say(res.utterance, approved=True)

        # fase 6: com o lock na mão, começa o read-back antes de comprometer
        if reservou_agora:
            await self.read_back.start()
            return {"spoken": True, "decision": res.decision.value,
                    "instruction": "Read-back in progress. Wait for an explicit yes."}

        return {"spoken": True, "decision": res.decision.value,
                "instruction": "Already spoken aloud. Continue WITHOUT repeating amounts."}

    async def _on_reserved(self, amount: Decimal) -> None:
        """O lock foi tomado: esta chamada é a vencedora. Fase 5."""
        try:
            advance(self.op["id"], Phase.RESERVED, trigger="lock_acquired",
                    call_id=self.call_id, auction_id=self.call.get("auction_id"),
                    ctx={"reserved_by": self.call_id},
                    payload={"amount": float(amount),
                             "comparison": self.auction.comparison()},
                    detail=f"Reserva em {amount} {self.op['currency']} com "
                           f"{self.call.get('carrier_name')}")
        except PhaseError as e:
            print(f"[fase4] reserva não avançou a fase: {e}")

    # ── camada 3: nada com número vira som sem aprovação ───────────────────
    async def _say(self, text: str, approved: bool = False) -> None:
        text = (text or "").strip()
        if not text or self.closed:
            return

        if not approved:
            text, blocked = gate_text(self.state, text)
            if blocked:
                self.blocks += 1
                db.insert("policy_events", {
                    "call_id": self.call_id, "decision": "block",
                    "reason": "unapproved_amount_in_speech",
                    "utterance": text, "round": self.state.rounds,
                    "mandate_hash": self.mandate_hash})
                self.actions.append({"t": self._ms(), "action": "policy_block"})
                print(f"[POLICY BLOCK] {self.call_id}")

        await self.ws.send_text(json.dumps(
            {"type": "text", "token": text, "last": True}))
        db.insert("utterances", {"call_id": self.call_id, "speaker": "agent",
                                 "text": text, "t_ms": self._ms()})
        self.history.append({"role": "assistant", "content": text})

    # (english-only agent: no _switch_language method anymore)

    # ── barge-in ───────────────────────────────────────────────────────────
    def on_interrupt(self, said_until: str, ms: int) -> None:
        """
        O agente foi cortado no meio da frase. Truncar o histórico no ponto
        exato do corte é OBRIGATÓRIO: sem isso o modelo acredita ter dito a
        frase inteira, e a conversa desanda em duas ou três rodadas.
        """
        for item in reversed(self.history):
            if item.get("role") == "assistant" and isinstance(item.get("content"), str):
                item["content"] = said_until
                break
        db.insert("utterances", {"call_id": self.call_id, "speaker": "agent",
                                 "text": said_until, "t_ms": self._ms(),
                                 "interrupted": True})
        self.actions.append({"t": self._ms(), "action": "interrupted", "after_ms": ms})
        self.last_input_at = time.monotonic()

    def on_dtmf(self, digit: str) -> None:
        self.actions.append({"t": self._ms(), "action": "dtmf", "digit": digit})

    # ── silêncio: o jurado vai calar de propósito ──────────────────────────
    async def _silence_watchdog(self) -> None:
        """
        O ConversationRelay não avisa sobre silêncio. Sem este relógio o
        agente fica mudo esperando, e no palco isso parece travamento.
        Nunca inventa acordo: cutuca, cutuca de novo, e encerra com resumo.
        """
        try:
            while not self.closed and not self.escalated:
                await asyncio.sleep(1.0)
                quiet = time.monotonic() - self.last_input_at

                if quiet > SILENCE_HANGUP_S and self.nudges >= SILENCE_MAX_NUDGES:
                    await self._say("Parece que se cortó. Le mando el resumen por "
                                    "escrito y quedo al pendiente. Gracias.",
                                    approved=True)
                    await self._close_call("silence_timeout")
                    return

                if quiet > SILENCE_NUDGE_S and self.nudges < SILENCE_MAX_NUDGES:
                    self.nudges += 1
                    self.last_input_at = time.monotonic()
                    await self._say("¿Sigue en la línea?" if self.nudges == 1
                                    else "¿Me escucha bien?", approved=True)
                    self.actions.append({"t": self._ms(), "action": "silence_nudge",
                                         "n": self.nudges})
        except asyncio.CancelledError:
            pass

    # ── escalação ──────────────────────────────────────────────────────────
    async def _escalate(self, reason: str, computation: dict | None = None) -> None:
        if self.escalated:
            return
        self.escalated = True
        await self._say("Permítame un momento, voy a poner a mi supervisor en la línea.",
                        approved=True)
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                await c.post(
                    f"http://localhost:{os.getenv('PORT','8000')}/escalate/{self.call_id}",
                    json={"trigger": reason,
                          "computation": computation or self._computation()})
        except Exception as e:
            print(f"[fase4] falha ao escalar: {e}")

    def _computation(self, ask: Decimal | None = None) -> dict | None:
        """A conta que o supervisor lê em nove segundos."""
        ask = ask or (self.state.counterparty_asks[-1]
                      if self.state.counterparty_asks else None)
        if ask is None:
            return None
        dem = Decimal(str(self.op["demurrage_per_day"]))
        alvo = self.state.mandate.target_rate
        return {
            "option_on_time": {"label": f"{self.call.get('carrier_name')} · dentro da janela",
                               "rate": float(ask), "demurrage": 0.0, "total": float(ask)},
            "option_late": {"label": "manter o combinado, fora da janela",
                            "rate": float(alvo), "demurrage": float(dem),
                            "total": float(alvo + dem)},
            "delta": float((alvo + dem) - ask),
            "exceeds_mandate_by": float(max(Decimal(0), ask - self.state.mandate.max_rate)),
            "currency": self.op["currency"],
            "mandate_hash": self.mandate_hash,
        }

    # ── encerramento ───────────────────────────────────────────────────────
    async def _close_call(self, reason: str) -> None:
        if self.closed:
            return
        self.closed = True
        await self.ws.send_text(json.dumps(
            {"type": "end", "handoffData": json.dumps({"reason": reason})}))

    def brief(self) -> str:
        asks = ", ".join(str(a) for a in self.state.counterparty_asks) or "nenhuma"
        return (f"{self.call.get('carrier_name')} · rota {self.op['ref']}. "
                f"Alvo {self.state.mandate.target_rate}, teto "
                f"{self.state.mandate.max_rate} {self.op['currency']}. "
                f"Pediram: {asks}. Rodadas: {self.state.rounds}. "
                f"Bloqueios de política: {self.blocks}. "
                f"Mandato {self.mandate_hash}.")

    async def close(self) -> None:
        if self._silence_task:
            self._silence_task.cancel()
        db.insert("call_briefs", {
            "call_id": self.call_id,
            "actions": self.actions,
            "mentions": self.mentions,
            "outcome": ("escalated" if self.escalated else "completed"),
        })
        db.update("calls", self.call_id,
                  {"status": "escalated" if self.escalated else "done",
                   "ended_at": "now()"})
        SESSIONS.pop(self.call_id, None)


# ═══════════════════════════════════════════════════════════════════════════
# o WebSocket — a Twilio conecta aqui
# ═══════════════════════════════════════════════════════════════════════════
@router.websocket("/ws")
async def relay(ws: WebSocket):
    await ws.accept()
    sess: NegotiationSession | None = None
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.get("type")

            if kind == "setup":
                params = msg.get("customParameters") or {}
                call_id = params.get("call_id")
                if not call_id:
                    await ws.close(code=1008)
                    return
                sess = NegotiationSession(call_id=call_id, ws=ws,
                                          agent_call_sid=msg.get("callSid"))
                SESSIONS[call_id] = sess
                await sess.open()

            elif kind == "prompt" and sess:
                await sess.on_speech(msg.get("voicePrompt", ""), lang=msg.get("lang"))

            elif kind == "interrupt" and sess:
                sess.on_interrupt(msg.get("utteranceUntilInterrupt", ""),
                                  int(msg.get("durationUntilInterruptMs") or 0))

            elif kind == "dtmf" and sess:
                sess.on_dtmf(msg.get("digit"))

            elif kind == "error":
                print("[relay error]", msg)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[fase4] erro na sessão: {e}")
    finally:
        if sess:
            await sess.close()
