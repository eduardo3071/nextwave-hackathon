"""
AMARRA · FASE 3 — market_open

Três transportadoras discando em paralelo. Parece a fase mais simples e é a
que tem mais chance de derrubar a demo, porque ela é a única que depende do
mundo físico: rede telefônica, limites de conta, gente que não atende.

Quatro responsabilidades:
  1. CONTROLE DE ADMISSÃO — recusar abrir o mercado quando abrir vai falhar
  2. ORÇAMENTO DE PERNAS  — cada negociação são 2 pernas; a conta tem limite
  3. DISCAGEM ESCALONADA  — 1 chamada/segundo é o teto padrão da Twilio
  4. RECONCILIAÇÃO        — quem tocou, quem caiu, quem não atendeu

A fase avança quando as pernas foram DISPARADAS. Quem atendeu é a fase 4.
Se ninguém atender dentro do watchdog, a operação vai para 'failed' — um
sistema que não consegue e diz que não conseguiu é comportamento correto.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from twilio.base.exceptions import TwilioRestException

from app import twilio_voice as tw
from app.auction import AUCTIONS, Auction
from app.db import db
from app.phases import Phase, PhaseError, advance

router = APIRouter(prefix="/phase3", tags=["fase 3 · market_open"])

E164 = re.compile(r"^\+[1-9]\d{7,14}$")

DIAL_SPACING_S = 1.2                 # > 1/CPS. Não abaixe sem pedir aumento.
DIAL_MAX_ATTEMPTS = 3
LEGS_PER_NEGOTIATION = 2             # contraparte + agente
LEGS_RESERVED_FOR_ESCALATION = 1     # a perna do humano precisa caber
ANSWER_WATCHDOG_S = 45               # ninguém atendeu nisso, o mercado falhou

# Perfil da conta Twilio. Sem perfil: 2. Individual: 3. Business: ilimitado.
CONCURRENCY = int(os.getenv("TWILIO_CONCURRENCY", "3"))
ERR_CONCURRENCY = 10004


# ═══════════════════════════════════════════════════════════════════════════
# entrada
# ═══════════════════════════════════════════════════════════════════════════
class Carrier(BaseModel):
    id: str = Field(..., min_length=2)
    name: str
    phone: str
    language: str = "es-MX"

    @field_validator("phone")
    @classmethod
    def e164(cls, v):
        if not E164.match(v):
            raise ValueError(f"'{v}' não é E.164 — use +52..., +55...")
        return v


class OpenMarket(BaseModel):
    operation_ref: str
    carriers: list[Carrier]
    dry_run: bool = False            # valida tudo e não disca nada


# ═══════════════════════════════════════════════════════════════════════════
# prazos derivados do relógio — a fase 3 lê a fase 1
# ═══════════════════════════════════════════════════════════════════════════
def deadline_budget(seconds_left: int) -> tuple[int, int]:
    """
    Quanto tempo o leilão pode levar, dado o que sobrou de free time.

    Com folga, negocia com calma. Com o relógio apertado, aceita mais rápido
    e escala mais cedo — porque cada minuto gasto negociando é um minuto a
    menos para o caminhão chegar.
    """
    if seconds_left <= 0:
        return 30, 60                       # já expirou: decidir é urgente
    soft = max(30, min(90, seconds_left // 40))
    hard = max(60, min(180, seconds_left // 20))
    return int(soft), int(max(hard, soft + 30))


# ═══════════════════════════════════════════════════════════════════════════
# controle de admissão
# ═══════════════════════════════════════════════════════════════════════════
def admit(op: dict, m: dict, carriers: list[Carrier]) -> tuple[int, int, list[str]]:
    """
    Recusa alto quando abrir o mercado vai dar errado.
    Devolve (pernas_planejadas, orçamento, avisos).
    """
    warnings: list[str] = []

    # 1 · a fase 2 rodou?
    if not m.get("mandate_hash"):
        raise ValueError("mandato não emitido — rode a fase 2 antes de discar")
    if op["phase"] != Phase.MANDATE_ISSUED.value:
        raise ValueError(f"operação está em '{op['phase']}', não em 'mandate_issued'")

    # 2 · R7 — o requisito, não uma preferência
    if len(carriers) < 3:
        raise ValueError("R7 exige ao menos 3 transportadoras em paralelo")

    # 3 · números repetidos derrubam o leilão de forma silenciosa: duas
    #     "transportadoras" seriam a mesma pessoa e a comparação seria falsa
    fones = [c.phone for c in carriers]
    if len(set(fones)) != len(fones):
        raise ValueError("números repetidos entre as transportadoras")
    ids = [c.id for c in carriers]
    if len(set(ids)) != len(ids):
        raise ValueError("ids repetidos entre as transportadoras")
    if os.environ["TWILIO_PHONE_NUMBER"] in fones:
        raise ValueError("uma das transportadoras é o próprio número do agente")

    # 4 · orçamento de pernas — a armadilha nº 1 desta fase
    planned = len(carriers) * LEGS_PER_NEGOTIATION
    budget = CONCURRENCY
    if planned + LEGS_RESERVED_FOR_ESCALATION > budget:
        raise ValueError(
            f"orçamento de pernas estourado: {len(carriers)} negociações = "
            f"{planned} pernas, mais 1 reservada para a escalação, contra um "
            f"limite de {budget} chamadas simultâneas. Submeta o Customer "
            f"Profile como Business, ou defina TWILIO_CONCURRENCY corretamente.")
    if planned + LEGS_RESERVED_FOR_ESCALATION == budget:
        warnings.append("orçamento de pernas no limite — não haverá folga "
                        "para uma segunda escalação")

    # 5 · o relógio ainda permite negociar?
    fte = datetime.fromisoformat(op["free_time_ends"])
    left = int((fte - datetime.now(timezone.utc)).total_seconds())
    if left <= 0:
        warnings.append("free time JÁ EXPIROU — cada minuto agora custa "
                        f"{op['demurrage_per_day']} {op['currency']}/dia")
    elif left < 900:
        warnings.append(f"restam {left//60} min de free time — "
                        f"prazos do leilão comprimidos")

    # 6 · a janela de coleta ainda é alcançável?
    pt = datetime.fromisoformat(m["pickup_to"])
    if pt <= datetime.now(timezone.utc):
        raise ValueError("a janela de coleta terminou — não há o que negociar")

    return planned, budget, warnings


# ═══════════════════════════════════════════════════════════════════════════
# abertura
# ═══════════════════════════════════════════════════════════════════════════
@router.post("/open")
async def open_market(req: OpenMarket):
    """
    curl -X POST $HOST/phase3/open -H 'content-type: application/json' \\
         -d '{"operation_ref":"MZO-GDL-4471","carriers":[...]}'
    """
    op = db.operation(req.operation_ref)
    m = db.mandate(op["id"])

    try:
        planned, budget, warnings = admit(op, m, req.carriers)
    except ValueError as e:
        raise HTTPException(422, str(e))

    fte = datetime.fromisoformat(op["free_time_ends"])
    left = int((fte - datetime.now(timezone.utc)).total_seconds())
    soft, hard = deadline_budget(left)

    plan = [{"carrier_id": c.id, "name": c.name, "phone": c.phone,
             "language": c.language, "slot": i} for i, c in enumerate(req.carriers)]

    if req.dry_run:
        return {"dry_run": True, "admitted": True, "legs_planned": planned,
                "legs_budget": budget, "soft_deadline_s": soft,
                "hard_deadline_s": hard, "warnings": warnings, "dial_plan": plan}

    auction = Auction(op=op, mandate=m)
    AUCTIONS[auction.id] = auction
    db.insert("auctions", {
        "id": auction.id, "operation_id": op["id"], "mandate_id": m["id"],
        "status": "running", "opened_at": "now()", "dial_plan": plan,
        "legs_planned": planned, "legs_budget": budget,
        "soft_deadline_s": soft, "hard_deadline_s": hard,
        "admission_warnings": warnings,
    })
    auction.soft_deadline_s, auction.hard_deadline_s = soft, hard

    asyncio.create_task(_dial_all(auction, op, req.carriers))

    detail = f"{len(req.carriers)} transportadoras discando · " \
             f"{planned}/{budget} pernas · soft {soft}s / hard {hard}s"
    try:
        advance(op["id"], Phase.MARKET_OPEN, trigger="auction_dispatched",
                auction_id=auction.id, ctx={"carriers": len(req.carriers)},
                detail=detail,
                payload={"dial_plan": plan, "legs_planned": planned,
                         "legs_budget": budget, "soft_deadline_s": soft,
                         "hard_deadline_s": hard, "warnings": warnings})
    except PhaseError as e:
        raise HTTPException(409, str(e))

    return {"auction_id": auction.id, "carriers": len(req.carriers),
            "legs_planned": planned, "legs_budget": budget,
            "soft_deadline_s": soft, "hard_deadline_s": hard,
            "warnings": warnings}


# ═══════════════════════════════════════════════════════════════════════════
# o discador
# ═══════════════════════════════════════════════════════════════════════════
async def _dial_one(auction: Auction, op: dict, c: Carrier) -> str | None:
    """Uma negociação: perna da contraparte + perna do agente na mesma conference."""
    conf = f"amarra-{auction.id[:8]}-{c.id}"
    call_id = str(uuid.uuid4())

    db.insert("calls", {
        "id": call_id, "auction_id": auction.id, "operation_id": op["id"],
        "direction": "outbound", "leg_role": "counterparty",
        "carrier_id": c.id, "carrier_name": c.name, "phone": c.phone,
        "conference_name": conf, "language": c.language, "status": "dialing",
    })

    for attempt in range(1, DIAL_MAX_ATTEMPTS + 1):
        try:
            sid = tw.dial_counterparty(to=c.phone, conf=conf)
            db.update("calls", call_id, {"call_sid": sid, "dial_attempt": attempt})
            break
        except TwilioRestException as e:
            if e.code == ERR_CONCURRENCY and attempt < DIAL_MAX_ATTEMPTS:
                # backoff: uma perna está para liberar
                await asyncio.sleep(1.5 * attempt)
                continue
            db.update("calls", call_id, {"status": "failed", "dial_attempt": attempt,
                                         "dial_error": f"{e.code}: {e.msg}"})
            print(f"[dial] {c.id} falhou: {e.code} {e.msg}")
            return None

    # perna do agente
    try:
        agent_sid = tw.join_agent(conf=conf, call_id=call_id, lang=c.language)
    except TwilioRestException as e:
        db.update("calls", call_id, {"status": "failed",
                                     "dial_error": f"agent leg {e.code}: {e.msg}"})
        tw.hangup(db.get("calls", call_id).get("call_sid"))
        return None

    db.insert("calls", {
        "id": str(uuid.uuid4()), "auction_id": auction.id, "operation_id": op["id"],
        "direction": "outbound", "leg_role": "agent", "carrier_id": c.id,
        "carrier_name": f"{c.name} · agente", "conference_name": conf,
        "call_sid": agent_sid, "status": "live", "language": c.language,
    })

    auction.register(call_id=call_id, carrier_id=c.id, conf=conf,
                     sid=db.get("calls", call_id)["call_sid"])
    return call_id


async def _dial_all(auction: Auction, op: dict, carriers: list[Carrier]) -> None:
    """Escalonado. Três `create` no mesmo instante viram rate limit."""
    dialed = []
    for c in carriers:
        cid = await _dial_one(auction, op, c)
        if cid:
            dialed.append(cid)
        await asyncio.sleep(DIAL_SPACING_S)

    print(f"[market] {len(dialed)}/{len(carriers)} pernas no ar")

    if not dialed:
        advance(op["id"], Phase.FAILED, trigger="all_dials_failed",
                auction_id=auction.id,
                detail="Nenhuma perna subiu — verifique permissões geográficas "
                       "e o limite de chamadas simultâneas")
        db.update("auctions", auction.id, {"status": "failed",
                                           "decision_reason": "all_dials_failed"})
        return

    asyncio.create_task(_answer_watchdog(auction, op))
    asyncio.create_task(auction.run_deadlines())


async def _answer_watchdog(auction: Auction, op: dict) -> None:
    """
    Ninguém atendeu no prazo? A operação falha, e falha dizendo por quê.
    Sem isto o leilão fica pendurado e o painel mente durante o pitch.
    """
    await asyncio.sleep(ANSWER_WATCHDOG_S)

    if op["id"] and db.get("operations", op["id"])["phase"] != Phase.MARKET_OPEN.value:
        return   # alguém atendeu, a fase 4 já assumiu

    rows = db.c.table("calls").select("status,carrier_name") \
              .eq("auction_id", auction.id).eq("leg_role", "counterparty").execute().data
    vivos = [r for r in rows if r["status"] in ("live",)]
    if vivos:
        return

    for leg in auction.legs.values():
        tw.hangup(leg.sid)
    advance(op["id"], Phase.FAILED, trigger="no_answer",
            auction_id=auction.id,
            detail=f"Nenhuma transportadora atendeu em {ANSWER_WATCHDOG_S}s")
    db.update("auctions", auction.id, {"status": "failed",
                                       "decision_reason": "no_answer"})


# ═══════════════════════════════════════════════════════════════════════════
# reconciliação e leitura
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/status/{auction_id}")
async def status(auction_id: str):
    """O que o painel lê enquanto as três colunas se preenchem."""
    a = db.get("auctions", auction_id)
    legs = db.c.table("calls").select("*").eq("auction_id", auction_id).execute().data
    cp = [l for l in legs if l["leg_role"] == "counterparty"]
    return {
        "auction_id": auction_id,
        "status": a["status"],
        "legs": {"planned": a["legs_planned"], "budget": a["legs_budget"],
                 "up": len([l for l in legs if l["status"] == "live"])},
        "deadlines": {"soft_s": a["soft_deadline_s"], "hard_s": a["hard_deadline_s"],
                      "opened_at": a["opened_at"]},
        "carriers": [{"id": l["carrier_id"], "name": l["carrier_name"],
                      "status": l["status"], "attempt": l["dial_attempt"],
                      "error": l["dial_error"]} for l in cp],
        "warnings": a["admission_warnings"],
    }


@router.post("/abort/{auction_id}")
async def abort(auction_id: str):
    """Botão de pânico. Derruba todas as pernas e falha limpo."""
    a = db.get("auctions", auction_id)
    for l in db.c.table("calls").select("call_sid").eq("auction_id", auction_id).execute().data:
        if l.get("call_sid"):
            tw.hangup(l["call_sid"])
    db.update("auctions", auction_id, {"status": "failed",
                                       "decision_reason": "aborted_by_operator"})
    advance(a["operation_id"], Phase.FAILED, trigger="aborted_by_operator",
            auction_id=auction_id, detail="Leilão abortado manualmente")
    return {"ok": True}
