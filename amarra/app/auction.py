"""
AMARRA · orquestrador do leilão.

Duas coisas moram aqui, e as duas são pontos de defesa técnica:

1. AS REGRAS DE PARADA — buy-it-now, soft deadline, hard deadline.
   O buy-it-now é o que faz as duas chamadas perdedoras desligarem sozinhas
   na frente do júri.

2. O LOCK DE RESERVA — duas transportadoras podem aceitar no MESMO segundo.
   Se as duas sessões fecharem, você se comprometeu com dois caminhões para
   o mesmo contêiner, e um compromisso falso é pior que nenhum.
   Nenhuma sessão fecha sozinha: ela PEDE reserva, e só uma recebe.

   Corolário para o requisito R5: enquanto não confirmado, o agente diz
   "vou confirmar e te retorno", nunca "fechado".
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from app.db import db

SOFT_DEADLINE_S = 90.0
HARD_DEADLINE_S = 180.0


@dataclass
class Leg:
    call_id: str
    carrier_id: str
    conf: str
    sid: str
    best_ask: Decimal | None = None
    approved: Decimal | None = None
    done: bool = False


@dataclass
class Auction:
    op: dict
    mandate: dict
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    legs: dict[str, Leg] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    reserved_by: str | None = None
    at_target: asyncio.Event = field(default_factory=asyncio.Event)

    # ── registro ───────────────────────────────────────────────────────────
    def register(self, *, call_id: str, carrier_id: str, conf: str, sid: str) -> None:
        self.legs[call_id] = Leg(call_id, carrier_id, conf, sid)

    @property
    def target(self) -> Decimal:
        return Decimal(str(self.mandate["target_rate"]))

    @property
    def max_rate(self) -> Decimal:
        return Decimal(str(self.mandate["max_rate"]))

    # ── mercado vivo: é isto que faz "quotes played against each other" ────
    def market_best(self, exclude_call_id: str) -> Decimal | None:
        vals = [l.best_ask for cid, l in self.legs.items()
                if cid != exclude_call_id and l.best_ask is not None]
        return min(vals) if vals else None

    def report_ask(self, call_id: str, ask: Decimal) -> None:
        leg = self.legs[call_id]
        if leg.best_ask is None or ask < leg.best_ask:
            leg.best_ask = ask

    # ── O LOCK ─────────────────────────────────────────────────────────────
    async def try_reserve(self, call_id: str, amount: Decimal) -> bool:
        """
        Pede autorização para FECHAR. Só uma chamada recebe.
        Devolve True se esta chamada pode dizer a frase de fechamento.
        """
        async with self.lock:
            if self.reserved_by is not None:
                return False
            if amount > self.max_rate:          # cinto e suspensório
                return False
            self.reserved_by = call_id
            self.legs[call_id].approved = amount
            db.update("auctions", self.id, {
                "reserved_by": call_id, "reserved_at": "now()",
                "status": "committed", "winner_call_id": call_id,
                "decision_reason": ("buy_it_now" if amount <= self.target
                                    else "best_within_mandate"),
                "decided_at": "now()",
            })
            if amount <= self.target:
                self.at_target.set()
            return True

    async def release(self, call_id: str) -> None:
        """Se o fechamento falhar depois de reservado, devolve o lock."""
        async with self.lock:
            if self.reserved_by == call_id:
                self.reserved_by = None
                db.update("auctions", self.id, {"reserved_by": None, "status": "running"})

    # ── regras de parada ───────────────────────────────────────────────────
    async def run_deadlines(self) -> None:
        from app import twilio_voice as tw

        try:
            await asyncio.wait_for(self.at_target.wait(), timeout=SOFT_DEADLINE_S)
            # BUY-IT-NOW: alguém bateu o alvo. Derruba as perdedoras.
            self._hangup_losers(tw)
            return
        except asyncio.TimeoutError:
            pass

        # soft deadline: ninguém no alvo. Melhor dentro do teto entre quem falou.
        best = self._best_within_mandate()
        if best:
            await self.try_reserve(best.call_id, best.best_ask)
            self._hangup_losers(tw)
            return

        # hard deadline: mais um tempo, e se nada vier, humano decide.
        await asyncio.sleep(HARD_DEADLINE_S - SOFT_DEADLINE_S)
        best = self._best_within_mandate()
        if best:
            await self.try_reserve(best.call_id, best.best_ask)
            self._hangup_losers(tw)
        else:
            db.update("auctions", self.id, {
                "status": "escalated", "decided_at": "now()",
                "decision_reason": "no_offer_within_mandate"})

    def _best_within_mandate(self) -> Leg | None:
        viable = [l for l in self.legs.values()
                  if l.best_ask is not None and l.best_ask <= self.max_rate]
        return min(viable, key=lambda l: l.best_ask) if viable else None

    def _hangup_losers(self, tw) -> None:
        for cid, leg in self.legs.items():
            if cid != self.reserved_by and not leg.done:
                leg.done = True
                tw.hangup(leg.sid)
                db.update("calls", cid, {"status": "done"})

    # ── a tabela auditável do requisito R7 ─────────────────────────────────
    def comparison(self) -> list[dict]:
        rows = []
        for cid, leg in self.legs.items():
            rows.append({
                "carrier_id": leg.carrier_id,
                "final_ask": float(leg.best_ask) if leg.best_ask else None,
                "approved": float(leg.approved) if leg.approved else None,
                "winner": cid == self.reserved_by,
                "reason": ("buy_it_now" if cid == self.reserved_by
                                           and leg.approved and leg.approved <= self.target
                           else "melhor dentro do teto" if cid == self.reserved_by
                           else "acima do teto" if leg.best_ask and leg.best_ask > self.max_rate
                           else "mais caro" if leg.best_ask
                           else "sem cotação"),
            })
        return sorted(rows, key=lambda r: (not r["winner"], r["final_ask"] or 9e9))


AUCTIONS: dict[str, Auction] = {}
