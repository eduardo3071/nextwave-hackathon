"""
AMARRA · desvio DISRUPTED → RENEGOTIATING

Cobre os resultados #2 e #3 da avaliação do enunciado:

  #2 Inbound → driver reports problem → agent decides + updates operation
  #3 Renegotiation — agent calls back the runner-up without exceeding mandate

Ponto de entrada: `handle_disruption(op_id, reason, needs_reschedule)`.
- Marca operação como DISRUPTED.
- Se needs_reschedule, avança pra RENEGOTIATING e dispara callback pro
  segundo colocado do último leilão (via auction_quotes) — sem exceder mandato.

Se não houver segundo colocado viável (todos acima do teto, ou sem cotação),
escala pra humano em vez de estourar autoridade.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException

from app import twilio_voice as tw
from app.db import db
from app.phases import Phase, PhaseError, advance

router = APIRouter(prefix="/disruption", tags=["desvio · disrupted"])


async def handle_disruption(operation_id: str, reason: str,
                            needs_reschedule: bool = True,
                            call_id: Optional[str] = None) -> dict:
    """
    Chamado pela tool `report_disruption` do agente, OU pelo endpoint
    `/disruption/report/{op_id}` (útil pra demo simular).
    """
    try:
        advance(operation_id, Phase.DISRUPTED, trigger="inbound_problem_reported",
                call_id=call_id, detail=f"Disruption reported: {reason}",
                payload={"reason": reason, "needs_reschedule": needs_reschedule})
    except PhaseError as e:
        print(f"[disruption] advance falhou: {e}")

    if not needs_reschedule:
        return {"operation_id": operation_id, "phase": "disrupted",
                "reason": reason, "reschedule_kicked": False}

    # Fire and forget: encontra segundo colocado e disca
    asyncio.create_task(renegotiate_with_runner_up(operation_id, reason))

    return {"operation_id": operation_id, "phase": "disrupted",
            "reason": reason, "reschedule_kicked": True}


async def renegotiate_with_runner_up(operation_id: str, reason: str) -> dict:
    """
    Encontra o segundo colocado do último leilão (via auction_quotes) e
    disca. Se não houver viável (todos acima do teto), escala.
    """
    op = db.get("operations", operation_id)
    auction_rows = (db.c.table("auctions").select("*")
                    .eq("operation_id", operation_id)
                    .order("id", desc=True).limit(1).execute().data)
    if not auction_rows:
        _escalate_no_runner_up(operation_id, "sem leilão anterior pra buscar runner-up")
        return {"escalated": True, "reason": "no_prior_auction"}
    last_auction = auction_rows[0]

    quotes = (db.c.table("auction_quotes").select("*")
              .eq("auction_id", last_auction["id"]).execute().data)
    # segundo colocado: NÃO foi winner, tem cotação dentro do teto
    ceiling = float(db.mandate(operation_id)["max_rate"])
    viable = [q for q in quotes
              if not q.get("winner")
              and q.get("final_ask") is not None
              and float(q["final_ask"]) <= ceiling]
    if not viable:
        _escalate_no_runner_up(operation_id,
                               "sem cotação viável dentro do teto pra renegociar")
        return {"escalated": True, "reason": "no_viable_runner_up"}

    runner = min(viable, key=lambda q: float(q["final_ask"]))

    # Puxa telefone do runner via calls (o dial_plan tinha guardado)
    prior_call = (db.c.table("calls").select("*")
                  .eq("auction_id", last_auction["id"])
                  .eq("carrier_id", runner["carrier_id"]).limit(1).execute().data)
    if not prior_call or not prior_call[0].get("phone"):
        _escalate_no_runner_up(operation_id,
                               f"runner-up {runner['carrier_id']} sem telefone registrado")
        return {"escalated": True, "reason": "no_phone_for_runner_up"}

    phone = prior_call[0]["phone"]
    carrier_name = runner.get("carrier_name") or runner["carrier_id"]

    try:
        advance(operation_id, Phase.RENEGOTIATING, trigger="callback_dialed",
                auction_id=last_auction["id"],
                detail=f"Discando de volta pra {carrier_name} — {reason}",
                payload={"runner_up": runner["carrier_id"],
                         "prior_ask": runner["final_ask"], "reason": reason})
    except PhaseError as e:
        print(f"[disruption] avanço pra RENEGOTIATING falhou: {e}")

    # Disca. Cria nova call row + conference + agent leg (mesma mecânica da fase 3).
    conf = f"amarra-reneg-{operation_id[:8]}"
    call_id = str(uuid.uuid4())
    db.insert("calls", {
        "id": call_id, "auction_id": last_auction["id"], "operation_id": operation_id,
        "direction": "outbound", "leg_role": "counterparty",
        "carrier_id": runner["carrier_id"], "carrier_name": carrier_name,
        "phone": phone, "conference_name": conf, "status": "dialing",
    })

    try:
        sid = tw.dial_counterparty(to=phone, conf=conf)
        db.update("calls", call_id, {"call_sid": sid})
        tw.join_agent(conf=conf, call_id=call_id)
    except Exception as e:
        print(f"[disruption] falha discando runner-up: {e}")
        db.update("calls", call_id, {"status": "failed",
                                     "dial_error": str(e)[:200]})
        _escalate_no_runner_up(operation_id, f"falha discando runner-up: {e}")
        return {"escalated": True, "reason": "dial_failed"}

    print(f"[disruption] callback pra {carrier_name} ({phone}) discado — "
          f"prior ask {runner['final_ask']}")
    return {"call_id": call_id, "carrier": carrier_name, "phone": phone,
            "prior_ask": runner["final_ask"], "conference": conf}


def _escalate_no_runner_up(operation_id: str, reason: str) -> None:
    try:
        advance(operation_id, Phase.ESCALATED, trigger="no_runner_up_after_disruption",
                detail=reason, payload={"reason": reason})
    except PhaseError as e:
        print(f"[disruption] escalação falhou: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# rotas
# ═══════════════════════════════════════════════════════════════════════════
@router.post("/report/{operation_id}")
async def report(operation_id: str, reason: str = "unspecified",
                 needs_reschedule: bool = True):
    """REST equivalente da tool `report_disruption` — útil pra teste sem
    passar por chamada. Ex.:
        curl -X POST '$HOST/disruption/report/OP_ID?reason=truck_broke&needs_reschedule=true'
    """
    return await handle_disruption(operation_id, reason, needs_reschedule)


@router.post("/demo/simulate/{operation_id}")
async def simulate(operation_id: str,
                   reason: str = "truck breakdown, need to reschedule"):
    """
    Simula o cenário completo do resultado #2 (inbound driver reports problem)
    e #3 (renegotiation) sem precisar de chamada de entrada real.

    Só valida se a operação tem leilão prévio com pelo menos 1 runner-up
    viável — se sim, dispara callback. Ideal pra ensaio da demo.
    """
    op = db.get("operations", operation_id)
    if op["phase"] not in ("committed", "verified", "reserved"):
        raise HTTPException(
            409, f"disruption só faz sentido depois de committed — "
                 f"operação está em '{op['phase']}'")
    return await handle_disruption(operation_id, reason, needs_reschedule=True)
