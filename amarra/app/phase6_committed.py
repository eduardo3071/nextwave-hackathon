"""
AMARRA · FASE 6 — committed

O read-back é o coração desta fase. O agente repete os termos materiais com
os valores EXATOS que o sistema registrou, e exige um sim explícito. O sim
vira evidência com carimbo próprio.

Estado do compromisso:

    proposed ──read_back()──▶ read_back ──sim explícito──▶ confirmed
        ▲                          │
        └──── não / ambíguo ───────┘        (até MAX_ATTEMPTS)

Nada aqui é gerado por modelo. A frase do read-back é montada por template a
partir dos valores registrados — se ela fosse escrita pelo LLM, o agente
poderia ler um valor diferente do que o sistema guardou, e a fase inteira
perderia sentido.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException

from app.db import db
from app.phases import Phase, PhaseError, advance

router = APIRouter(prefix="/phase6", tags=["fase 6 · committed"])

MAX_READ_BACK_ATTEMPTS = 3

# Sem estes campos não existe compromisso — são os termos materiais.
MATERIAL_SLOTS = ("rate", "pickup_at")
OPTIONAL_SLOTS = ("equipment", "driver", "mc_number")


# ═══════════════════════════════════════════════════════════════════════════
# detecção de afirmação — conservadora de propósito
# ═══════════════════════════════════════════════════════════════════════════
AFFIRM = {
    "es": {"si", "sí", "claro", "correcto", "exacto", "confirmado", "de acuerdo",
           "va", "vale", "asi es", "así es", "perfecto", "afirmativo", "hecho",
           "cerramos", "confirmo", "quedamos asi", "quedamos así"},
    "pt": {"sim", "isso", "correto", "exato", "confirmado", "confirmo", "fechado",
           "combinado", "certo", "pode ser", "positivo", "isso mesmo", "beleza"},
}
NEGATE = {
    "es": {"no", "negativo", "espera", "espere", "momento", "cambio", "cambia",
           "corrige", "corrijo", "esta mal", "está mal", "incorrecto", "pero"},
    "pt": {"nao", "não", "negativo", "espera", "espere", "calma", "muda", "mudar",
           "corrige", "corrijo", "errado", "incorreto", "mas"},
}
HEDGE = {"creo", "acho", "talvez", "quiza", "quizá", "quizas", "quizás",
         "mais o menos", "mas o menos", "mais ou menos", "possivelmente",
         "posiblemente", "provavelmente", "probablemente", "quase", "casi"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", " ", s)


def classify_response(text: str) -> str:
    """
    Devolve: confirmed | rejected | ambiguous

    Regras, nesta ordem:
      1. qualquer negação presente  → rejected  (mesmo com um "sim" junto:
         "sim, mas muda a hora" é rejeição, não confirmação)
      2. hedge presente             → ambiguous ("acho que sim" não é sim)
      3. afirmação explícita        → confirmed
      4. qualquer outra coisa       → ambiguous (silêncio, "aham", ruído)
    """
    t = _norm(text)
    if not t.strip():
        return "ambiguous"
    tokens = set(t.split())
    todas_neg = NEGATE["es"] | NEGATE["pt"]
    todas_afr = AFFIRM["es"] | AFFIRM["pt"]

    if tokens & todas_neg or any(f in t for f in todas_neg if " " in f):
        return "rejected"
    if tokens & HEDGE or any(h in t for h in HEDGE if " " in h):
        return "ambiguous"
    if tokens & todas_afr or any(a in t for a in todas_afr if " " in a):
        return "confirmed"
    return "ambiguous"


# ═══════════════════════════════════════════════════════════════════════════
# slots e token
# ═══════════════════════════════════════════════════════════════════════════
def collect_slots(call_id: str) -> dict:
    """Compromissos propostos nesta chamada, o último valor de cada campo."""
    rows = db.c.table("commitments").select("*") \
             .eq("call_id", call_id).order("id").execute().data
    slots: dict[str, dict] = {}
    for r in rows:
        if r["state"] in ("proposed", "read_back", "confirmed"):
            slots[r["field"]] = r
    return slots


def missing_material(slots: dict) -> list[str]:
    return [s for s in MATERIAL_SLOTS if s not in slots]


def read_back_token(slots: dict) -> str:
    """
    Prende a confirmação a ESTE conjunto de valores. Mudou um valor,
    muda o token, e o sim anterior deixa de valer.
    """
    canon = {k: str(slots[k]["value"]) for k in sorted(slots)}
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode()
    return "rb_" + hashlib.sha256(blob).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════════════
# a frase — template, nunca modelo
# ═══════════════════════════════════════════════════════════════════════════
def _fmt_money(v: str, currency: str, lang: str) -> str:
    n = Decimal(re.sub(r"[^\d.]", "", str(v)) or 0)
    unidade = {"MXN": "pesos", "BRL": "reais", "USD": "dólares"}.get(currency, currency)
    return f"{n.quantize(Decimal('1')):,.0f} {unidade}".replace(",", ".")


DAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday",
           "Friday", "Saturday", "Sunday"],
    "es": ["lunes", "martes", "miércoles", "jueves",
           "viernes", "sábado", "domingo"],
    "pt": ["segunda", "terça", "quarta", "quinta",
           "sexta", "sábado", "domingo"],
}


def _lang_key(lang: str) -> str:
    """en | es | pt — English é o default do produto."""
    if not lang:
        return "en"
    p = lang[:2].lower()
    return p if p in ("en", "es", "pt") else "en"


def _fmt_when(iso: str, lang: str) -> str:
    try:
        dt = datetime.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    days = DAYS.get(_lang_key(lang), DAYS["en"])
    return f"{days[dt.weekday()]} {dt.strftime('%H:%M')}"


def build_read_back(slots: dict, *, currency: str, lang: str) -> str:
    L = _lang_key(lang)
    partes = []
    if "rate" in slots:
        partes.append(_fmt_money(slots["rate"]["value"], currency, lang))
    if "pickup_at" in slots:
        quando = _fmt_when(slots["pickup_at"]["value"], lang)
        prefix = {"en": "pickup", "es": "recolección", "pt": "coleta"}[L]
        partes.append(f"{prefix} {quando}")
    if "equipment" in slots:
        partes.append(str(slots["equipment"]["value"]))
    if "driver" in slots:
        cond = {"en": "driver", "es": "chofer", "pt": "motorista"}[L]
        partes.append(f"{cond} {slots['driver']['value']}")

    corpo = ", ".join(partes)
    if L == "es":
        return (f"Le repito para confirmar: {corpo}. "
                f"¿Es correcto? Necesito un sí explícito para cerrarlo.")
    if L == "pt":
        return (f"Vou repetir para confirmar: {corpo}. "
                f"Está correto? Preciso de um sim explícito para fechar.")
    return (f"Let me confirm: {corpo}. "
            f"Is that correct? I need an explicit yes to close.")


def ask_missing(faltando: list[str], lang: str) -> str:
    L = _lang_key(lang)
    nomes = {
        "rate":      {"en": "the amount",
                      "es": "el monto",
                      "pt": "o valor"},
        "pickup_at": {"en": "the pickup date and time",
                      "es": "la fecha y hora de recolección",
                      "pt": "a data e hora da coleta"},
    }
    itens = [nomes[f][L] for f in faltando]
    join_word = {"en": " and ", "es": " y ", "pt": " e "}[L]
    lista = join_word.join(itens) if len(itens) > 1 else itens[0]
    if L == "es":
        return f"Antes de cerrar me falta {lista}. ¿Me lo confirma?"
    if L == "pt":
        return f"Antes de fechar falta {lista}. Pode confirmar?"
    return f"Before closing I still need {lista}. Can you confirm?"


# ═══════════════════════════════════════════════════════════════════════════
# o protocolo
# ═══════════════════════════════════════════════════════════════════════════
class ReadBack:
    """
    Conduzido pela sessão da fase 4. A sessão só chama `start()` e depois
    entrega cada fala da contraparte para `handle_response()`.
    """

    def __init__(self, session):
        self.s = session
        self.attempt = 0
        self.token: str | None = None
        self.slots: dict = {}
        self.active = False
        self.spoken_ms = 0
        self.row_id: int | None = None

    async def start(self) -> bool:
        """
        Devolve True se o read-back começou; False se faltam termos materiais
        (nesse caso o agente pergunta em vez de repetir).
        """
        self.slots = collect_slots(self.s.call_id)
        faltando = missing_material(self.slots)
        lang = self.s.call.get("language") or "en-US"

        if faltando:
            frase = ask_missing(faltando, lang)
            self.s.state.approved_utterances.add(frase)
            await self.s._say(frase, approved=True)
            return False

        self.attempt += 1
        if self.attempt > MAX_READ_BACK_ATTEMPTS:
            await self.s._escalate("read_back_failed")
            return False

        self.token = read_back_token(self.slots)
        frase = build_read_back(self.slots, currency=self.s.op["currency"], lang=lang)
        self.spoken_ms = self.s._ms()

        self.s.state.approved_utterances.add(frase)
        await self.s._say(frase, approved=True)

        row = db.insert("read_backs", {
            "call_id": self.s.call_id, "operation_id": self.s.op["id"],
            "token": self.token,
            "slots": {k: {"value": str(v["value"]), "quote": v["quote"]}
                      for k, v in self.slots.items()},
            "spoken_text": frase, "attempt": self.attempt,
            "t_spoken_ms": self.spoken_ms,
        })
        self.row_id = row["id"]

        for c in self.slots.values():
            db.update("commitments", c["id"], {
                "state": "read_back", "read_back_token": self.token,
                "read_back_at": "now()"})

        self.active = True
        return True

    async def handle_response(self, text: str) -> str | None:
        """
        Devolve o desfecho, ou None se o read-back não estava ativo
        (nesse caso a fala segue o fluxo normal da fase 4).
        """
        if not self.active:
            return None

        outcome = classify_response(text)
        t_ms = self.s._ms()
        db.update("read_backs", self.row_id,
                  {"response_text": text, "outcome": outcome, "t_response_ms": t_ms})

        # ── os valores mudaram entre a leitura e a resposta? ───────────────
        atuais = collect_slots(self.s.call_id)
        if outcome == "confirmed" and read_back_token(atuais) != self.token:
            db.update("read_backs", self.row_id, {"outcome": "superseded"})
            self.active = False
            return await self._restart("values_changed_during_read_back")

        if outcome == "confirmed":
            self.active = False
            await self._confirm(text, t_ms)
            return "confirmed"

        if outcome == "rejected":
            self.active = False
            L = _lang_key(self.s.call.get("language") or "en-US")
            frase = {
                "en": "Got it, let's fix that. What's the correct value?",
                "es": "Perfecto, corrijamos. ¿Cuál es el dato correcto?",
                "pt": "Perfeito, vamos corrigir. Qual é o dado correto?",
            }[L]
            self.s.state.approved_utterances.add(frase)
            await self.s._say(frase, approved=True)
            for c in self.slots.values():
                db.update("commitments", c["id"], {"state": "proposed"})
            return "rejected"

        # ambíguo: relê uma vez. "Acho que sim" nunca vira compromisso.
        self.active = False
        return await self._restart("ambiguous_response")

    async def _restart(self, motivo: str) -> str:
        self.s.actions.append({"t": self.s._ms(), "action": "read_back_retry",
                               "reason": motivo, "attempt": self.attempt})
        ok = await self.start()
        return "retry" if ok else "escalated"

    async def _confirm(self, affirmation: str, t_ms: int) -> None:
        """
        O sim explícito. Cada compromisso passa a `confirmed` e guarda a
        citação da afirmação — que a fase 7 vai ancorar no áudio junto com
        a citação original. É o "verificado duas vezes".
        """
        for c in self.slots.values():
            db.update("commitments", c["id"], {
                "state": "confirmed",
                "confirmed_at": "now()",
                "affirmation_quote": affirmation,
                "negotiation_round": self.s.state.rounds,
                "mandate_hash": self.s.mandate_hash,
            })

        await commit_operation(self.s, self.slots)


# ═══════════════════════════════════════════════════════════════════════════
# a transição de fase, com as guardas
# ═══════════════════════════════════════════════════════════════════════════
async def commit_operation(session, slots: dict) -> None:
    """
    Avança para `committed`. As guardas da máquina de fases recusam se não
    houver lock de reserva ou se o valor exceder o teto — de novo, em outra
    camada.

    E aqui mora uma verificação que nenhuma outra faz: o valor CONFIRMADO
    em voz alta bate com o valor RESERVADO? Se não bater, a contraparte
    mudou o combinado no meio do read-back, e isso é escalação.
    """
    op = session.op
    auction = session.auction

    rate = slots.get("rate", {}).get("value")
    confirmado = Decimal(re.sub(r"[^\d.]", "", str(rate)) or 0) if rate else None

    if auction and auction.id:
        a = db.get("auctions", auction.id)
        reservado = (Decimal(str(a["reserve_amount"]))
                     if a.get("reserve_amount") is not None else None)
        if reservado is not None and confirmado is not None and confirmado != reservado:
            db.insert("policy_events", {
                "call_id": session.call_id, "counterparty_ask": float(confirmado),
                "decision": "escalate", "reason": "confirmed_differs_from_reserved",
                "round": session.state.rounds, "mandate_hash": session.mandate_hash,
                "utterance": None})
            await session._escalate("confirmed_differs_from_reserved")
            return

    try:
        advance(
            op["id"], Phase.COMMITTED, trigger="agreement_confirmed",
            call_id=session.call_id,
            auction_id=session.call.get("auction_id"),
            ctx={"reserved_by": session.call_id,
                 "amount": float(confirmado) if confirmado else None,
                 "max_rate": float(session.state.mandate.max_rate)},
            payload={"amount": float(confirmado) if confirmado else None,
                     "slots": {k: str(v["value"]) for k, v in slots.items()},
                     "carrier": session.call.get("carrier_name"),
                     "mandate_hash": session.mandate_hash},
            detail=f"{session.call.get('carrier_name')} confirmou: "
                   f"{confirmado} {op['currency']}, "
                   f"coleta {slots.get('pickup_at', {}).get('value', '—')}",
        )
    except PhaseError as e:
        print(f"[fase6] guarda recusou o commit: {e}")
        await session._escalate(f"commit_guard_failed:{e}")
        return

    L = _lang_key(session.call.get("language") or "en-US")
    fecho = {
        "en": "Closed. I'll send you the written confirmation right now. Thank you.",
        "es": "Cerrado. Le mando ahora mismo la confirmación por escrito. Gracias.",
        "pt": "Fechado. Já te mando a confirmação por escrito. Obrigado.",
    }[L]
    session.state.approved_utterances.add(fecho)
    await session._say(fecho, approved=True)
    session.actions.append({"t": session._ms(), "action": "committed",
                            "amount": float(confirmado) if confirmado else None})

    # A gravação vira evidência na fase 7, disparada pelo webhook /twilio/recording.
    await session._close_call("committed")


# ═══════════════════════════════════════════════════════════════════════════
# rotas de leitura
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/commitments/{operation_id}")
async def commitments(operation_id: str):
    rows = db.c.table("commitments").select("*") \
             .eq("operation_id", operation_id).order("id").execute().data
    return {
        "operation_id": operation_id,
        "confirmed": [r for r in rows if r["state"] == "confirmed"],
        "pending": [r for r in rows if r["state"] in ("proposed", "read_back")],
        "anchored": len([r for r in rows if r.get("t_start_ms") is not None]),
        "awaiting_anchor": len([r for r in rows
                                if r["state"] == "confirmed" and r.get("t_start_ms") is None]),
    }


@router.get("/read-backs/{call_id}")
async def read_backs(call_id: str):
    """O painel mostra cada tentativa — inclusive as que a contraparte recusou."""
    return db.c.table("read_backs").select("*") \
             .eq("call_id", call_id).order("id").execute().data
