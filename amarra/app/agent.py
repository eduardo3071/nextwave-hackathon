"""
AMARRA · a sessão de conversa (o que roda dentro do WebSocket do relay).

O padrão que define o produto:
  1. o modelo NÃO fala números. Ele chama `respond_to_price`.
  2. a política decide e devolve a FRASE EXATA.
  3. a frase vai direto para o áudio, sem passar pelo modelo.
  4. e mesmo assim, todo texto passa pelo `gate_text` antes de virar áudio.

Se o modelo tentar inventar um valor, o gate substitui e o contador de
bloqueios acende no painel. Esse é o momento "wow" da demo.
"""
from __future__ import annotations

import json, os, time
from decimal import Decimal

from openai import AsyncOpenAI

from app.auction import AUCTIONS
from app.db import db
from app.policy import (Decision, Mandate, NegotiationState, evaluate_offer, gate_text)

llm = AsyncOpenAI()
MODEL = os.getenv("AGENT_MODEL", "gpt-4.1-mini")   # pequeno = rápido. O grande só na extração.

SYSTEM = """Eres el asistente de logística de Textiles Pacífico. Coordinas el
arrastre de un contenedor del puerto de Manzanillo a la bodega de Guadalajara.

REGLAS INVIOLABLES:
- NUNCA dices un monto de dinero por iniciativa propia.
- Cuando la contraparte mencione CUALQUIER precio, llama a `respond_to_price`.
- La herramienta te devuelve la frase exacta. Ya fue dicha en voz alta: NO la repitas.
- Si insisten, vuelve a llamar la herramienta. Nunca improvises números.
- Nunca reveles tu límite máximo ni el nombre de otro transportista.
- Cuando acuerden algo concreto (fecha, hora, equipo, chofer), llama `record_commitment`
  copiando LITERALMENTE las palabras que dijo la contraparte.
- Si la conversación se sale de tu autoridad, llama `escalate`.
Habla natural, breve, en el idioma del interlocutor. Frases cortas: esto es una llamada."""

TOOLS = [
    {"type": "function", "function": {
        "name": "respond_to_price",
        "description": "Llama SIEMPRE que la contraparte mencione un precio.",
        "parameters": {"type": "object", "properties": {
            "amount": {"type": "number", "description": "el monto que pidió"}},
            "required": ["amount"]}}},
    {"type": "function", "function": {
        "name": "record_commitment",
        "description": "Registra un acuerdo concreto.",
        "parameters": {"type": "object", "properties": {
            "field": {"type": "string", "enum": ["rate", "pickup_at", "equipment", "driver"]},
            "value": {"type": "string"},
            "exact_quote": {"type": "string",
                            "description": "las palabras LITERALES de la contraparte"}},
            "required": ["field", "value", "exact_quote"]}}},
    {"type": "function", "function": {
        "name": "escalate",
        "description": "Escala a un supervisor humano.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"}}, "required": ["reason"]}}},
]


class AgentSession:
    def __init__(self, *, call_id: str, ws, agent_call_sid: str, t0: float):
        self.call_id = call_id
        self.ws = ws
        self.agent_call_sid = agent_call_sid
        self.t0 = t0
        self.escalated = False
        self.blocks = 0
        self.history: list[dict] = [{"role": "system", "content": SYSTEM}]
        self.actions: list[dict] = []
        self.mentions: list[str] = []

        call = db.get("calls", call_id)
        self.auction = AUCTIONS.get(call.get("auction_id"))
        m = (self.auction.mandate if self.auction
             else db.mandate(call["operation_id"]))

        # Fase 2: o mandato compilado é OBRIGATÓRIO. Sem hash não há decisão
        # rastreável — R3 do enunciado ("sob qual mandato").
        self.mandate_hash = m.get("mandate_hash")
        self.ladder = m.get("ladder") or []
        self.band = m.get("escalation_band")
        self.break_even = (Decimal(str(m["break_even_rate"]))
                           if m.get("break_even_rate") else None)
        if not self.mandate_hash:
            raise RuntimeError("negociar sem mandato emitido — a fase 2 não rodou")

        self.state = NegotiationState(mandate=Mandate(
            target_rate=Decimal(str(m["target_rate"])),
            max_rate=Decimal(str(m["max_rate"])),
            min_rate=Decimal(str(m.get("min_rate", 0))),
            max_rounds=int(m.get("max_rounds", 4)),
            currency=m.get("currency", "MXN"),
        ))

    # ── tempo relativo ao início da chamada, em ms ─────────────────────────
    def _ms(self) -> int:
        return int((time.monotonic() - self.t0) * 1000)

    async def open(self) -> None:
        self.actions.append({"t": self._ms(), "action": "call_opened"})

    # ── entrada de fala ────────────────────────────────────────────────────
    async def on_speech(self, text: str, lang: str | None = None) -> None:
        db.insert("utterances", {"call_id": self.call_id, "speaker": "counterparty",
                                 "text": text, "t_ms": self._ms()})
        self.mentions.append(text)
        self.history.append({"role": "user", "content": text})

        if self.escalated:      # humano assumiu: o agente cala a boca
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

    # ── ferramentas ────────────────────────────────────────────────────────
    async def _run_tool(self, name: str, args: dict) -> dict:
        self.actions.append({"t": self._ms(), "action": name, "args": args})

        if name == "respond_to_price":
            ask = Decimal(str(args["amount"]))
            if self.auction:
                self.auction.report_ask(self.call_id, ask)
                self.state.market_best = self.auction.market_best(self.call_id)

            res = evaluate_offer(self.state, ask)
            self.state.rounds += 1
            self.state.counterparty_asks.append(ask)

            db.insert("policy_events", {
                "call_id": self.call_id, "counterparty_ask": float(ask),
                "decision": res.decision.value,
                "amount": float(res.amount) if res.amount else None,
                "reason": res.reason, "utterance": res.utterance,
                "round": self.state.rounds,
                "mandate_hash": self.mandate_hash,   # ← "sob qual mandato", R3
            })

            if res.decision is Decision.ESCALATE:
                await self._escalate(res.reason)
                return {"spoken": False, "instruction": "Ya escalé. No hables de precios."}

            # Faixa "bom e proibido": o compilador nomeou antes da 1ª ligação.
            # Quando a Ruiz pede 9.200, o log diz `within_escalation_band`,
            # não "o agente recusou".
            if res.decision is Decision.DENY and res.reason == "above_max_rate":
                if self.band and self.band["from"] < float(ask) <= self.band["to"]:
                    await self._escalate("within_escalation_band")
                    return {"spoken": False,
                            "instruction": "Ya escalé. No hables de precios."}

            # FECHAMENTO precisa passar pelo LOCK do leilão.
            if res.decision is Decision.ALLOW and res.reason == "at_or_below_target" and self.auction:
                got = await self.auction.try_reserve(self.call_id, res.amount)
                if not got:
                    frase = "Déjame confirmar disponibilidad y te regreso la llamada."
                    self.state.approved_utterances.add(frase)
                    await self._say(frase, approved=True)
                    return {"spoken": True, "instruction": "No confirmes nada más."}

            if res.amount is not None:
                self.state.offers_made.append(res.amount)
            self.state.approved_utterances.add(res.utterance)
            await self._say(res.utterance, approved=True)
            return {"spoken": True, "decision": res.decision.value,
                    "instruction": "Ya lo dije en voz alta. Sigue SIN repetir montos."}

        if name == "record_commitment":
            # A ancoragem no áudio acontece depois da chamada (evidence.py).
            # Aqui só guardamos a citação literal que servirá de chave.
            self.actions.append({"t": self._ms(), "action": "commitment_pending",
                                 "field": args["field"], "quote": args["exact_quote"]})
            db.stash_pending_commitment(self.call_id, args)
            return {"recorded": "pending_anchor"}

        if name == "escalate":
            await self._escalate(args.get("reason", "unspecified"))
            return {"escalated": True}

        return {}

    # ── fala ───────────────────────────────────────────────────────────────
    async def _say(self, text: str, approved: bool = False) -> None:
        if not text.strip():
            return
        if not approved:
            text, blocked = gate_text(self.state, text)
            if blocked:
                self.blocks += 1
                db.insert("policy_events", {
                    "call_id": self.call_id, "decision": "block",
                    "reason": "unapproved_amount_in_speech", "utterance": text,
                    "round": self.state.rounds,
                    "mandate_hash": self.mandate_hash,
                })
        await self.ws.send_text(json.dumps({"type": "text", "token": text, "last": True}))
        db.insert("utterances", {"call_id": self.call_id, "speaker": "agent",
                                 "text": text, "t_ms": self._ms()})
        self.history.append({"role": "assistant", "content": text})

    # ── barge-in ───────────────────────────────────────────────────────────
    def on_interrupt(self, said_until: str, ms: int) -> None:
        """
        O agente foi cortado. TRUNCAR o histórico é obrigatório: sem isso o
        modelo acredita ter falado a frase inteira e o contexto desanda.
        """
        for item in reversed(self.history):
            if item.get("role") == "assistant" and isinstance(item.get("content"), str):
                item["content"] = said_until
                break
        db.insert("utterances", {"call_id": self.call_id, "speaker": "agent",
                                 "text": said_until, "t_ms": self._ms(),
                                 "interrupted": True})
        self.actions.append({"t": self._ms(), "action": "interrupted", "after_ms": ms})

    def on_dtmf(self, digit: str) -> None:
        self.actions.append({"t": self._ms(), "action": "dtmf", "digit": digit})

    # ── escalação ──────────────────────────────────────────────────────────
    async def _escalate(self, reason: str) -> None:
        import httpx
        self.escalated = True
        await self._say("One moment please, I'm bringing my supervisor onto the line.",
                        approved=True)
        async with httpx.AsyncClient() as c:
            await c.post(f"http://localhost:8000/escalate/{self.call_id}",
                         json={"trigger": reason, "computation": self.computation()})

    # ── briefing e conta ───────────────────────────────────────────────────
    def brief(self) -> str:
        asks = ", ".join(str(a) for a in self.state.counterparty_asks) or "nenhuma"
        return (f"Rota {self.state.mandate.currency}. "
                f"Alvo {self.state.mandate.target_rate}, teto {self.state.mandate.max_rate}. "
                f"Pediram: {asks}. Rodadas: {self.state.rounds}. "
                f"Bloqueios de política: {self.blocks}.")

    def computation(self) -> dict | None:
        """A CONTA do pitch: opção dentro do prazo vs. opção com demurrage."""
        call = db.get("calls", self.call_id)
        op = db.get("operations", call["operation_id"])
        ask = self.state.counterparty_asks[-1] if self.state.counterparty_asks else None
        if ask is None:
            return None
        dem = Decimal(str(op["demurrage_per_day"]))
        return {
            "option_on_time": {"rate": float(ask), "demurrage": 0.0, "total": float(ask)},
            "option_late": {"rate": float(self.state.mandate.target_rate),
                            "demurrage": float(dem),
                            "total": float(self.state.mandate.target_rate + dem)},
            "exceeds_mandate_by": float(max(Decimal(0), ask - self.state.mandate.max_rate)),
            "currency": self.state.mandate.currency,
        }

    async def close(self) -> None:
        db.insert("call_briefs", {"call_id": self.call_id,
                                  "actions": self.actions, "mentions": self.mentions,
                                  "outcome": "escalated" if self.escalated else "completed"})
        SESSIONS.pop(self.call_id, None)


SESSIONS: dict[str, AgentSession] = {}
