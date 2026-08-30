"""
AMARRA · FASE 5 — reserved

Uma única pergunta: QUEM pode fechar?

Três regras de parada, herdadas dos prazos que a fase 3 derivou do relógio:

    buy-it-now   alguém ≤ alvo          → fecha na hora, derruba as outras
    soft         prazo curto estourou   → melhor abaixo do teto entre quem falou
    hard         prazo final            → melhor dentro do teto, ou escala

E um lock atômico no banco. Nenhuma sessão fecha sozinha: ela PEDE, e uma só
recebe. Enquanto a reserva não é concedida, o agente diz "vou confirmar e te
retorno" — nunca "fechado". É a definição operacional do requisito R5.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException

from app import twilio_voice as tw
from app.auction import AUCTIONS, Auction
from app.db import db
from app.phases import Phase, PhaseError, advance

router = APIRouter(prefix="/phase5", tags=["fase 5 · reserved"])

CONFIRM_TIMEOUT_S = 45      # reservou e não confirmou nesse prazo → devolve o lock
GOODBYE_EN = ("I appreciate your time. On this shipment we'll close with "
              "another option, but let's stay in touch for the next one.")
GOODBYE_ES = ("Le agradezco el tiempo. Por esta carga vamos a cerrar con otra "
              "opción, pero seguimos en contacto para la próxima.")
GOODBYE_PT = ("Agradeço o tempo. Nesta carga vamos fechar com outra opção, "
              "mas seguimos em contato para a próxima.")


# ═══════════════════════════════════════════════════════════════════════════
# o lock
# ═══════════════════════════════════════════════════════════════════════════
async def try_reserve(auction: Auction, call_id: str, amount: Decimal,
                      reason: str) -> dict:
    """
    Pede autorização para FECHAR. Devolve {'granted': bool, ...}.

    Chamada pela sessão da fase 4 no instante em que a política aprova um
    valor de fechamento. Só uma chamada recebe `granted: true`.
    """
    res = db.rpc("try_reserve_auction", {
        "p_auction_id": auction.id,
        "p_call_id": call_id,
        "p_amount": float(amount),
        "p_reason": reason,
    }).data

    if not res.get("granted"):
        print(f"[fase5] {call_id} não obteve a reserva: {res.get('reason')}")
        return res

    auction.reserved_by = call_id
    auction.legs[call_id].approved = amount

    call = db.get("calls", call_id)
    try:
        advance(auction.op["id"], Phase.RESERVED, trigger="lock_acquired",
                call_id=call_id, auction_id=auction.id,
                ctx={"reserved_by": call_id},
                payload={"amount": float(amount), "reason": reason,
                         "carrier": call.get("carrier_name")},
                detail=f"Reserva em {amount} {auction.op['currency']} com "
                       f"{call.get('carrier_name')}")
    except PhaseError as e:
        print(f"[fase5] fase não avançou: {e}")

    await settle(auction, winner_call_id=call_id, reason=reason)
    asyncio.create_task(_confirmation_watchdog(auction, call_id))
    return res


async def release(auction: Auction, reason: str) -> dict:
    """Devolve o lock. O vencedor caiu, se contradisse, ou não confirmou."""
    res = db.rpc("release_reservation",
                 {"p_auction_id": auction.id, "p_reason": reason}).data
    if res.get("released"):
        auction.reserved_by = None
        auction.at_target.clear()
        print(f"[fase5] reserva devolvida: {reason}")
    return res


# ═══════════════════════════════════════════════════════════════════════════
# liquidação: encerra as perdedoras e materializa a comparação
# ═══════════════════════════════════════════════════════════════════════════
async def settle(auction: Auction, *, winner_call_id: str | None,
                 reason: str) -> list[dict]:
    rows = _build_comparison(auction, winner_call_id, reason)

    for r in rows:
        try:
            db.insert("auction_quotes", {"auction_id": auction.id, **r})
        except Exception:
            db.c.table("auction_quotes").update(r) \
                .eq("auction_id", auction.id).eq("carrier_id", r["carrier_id"]).execute()

    await asyncio.gather(*[
        _release_loser(cid) for cid in auction.legs
        if cid != winner_call_id and not auction.legs[cid].done
    ])
    return rows


def _build_comparison(auction: Auction, winner: str | None, reason: str) -> list[dict]:
    """
    A tabela auditável do R7. Não é uma lista de preços — é o registro de
    POR QUE aquela foi a escolha.
    """
    ceiling = auction.max_rate
    target = auction.target
    out = []
    for cid, leg in auction.legs.items():
        call = db.get("calls", cid)
        ask = leg.best_ask
        if cid == winner:
            why = ("buy-it-now · bateu o alvo" if ask is not None and ask <= target
                   else f"melhor dentro do teto · {reason}")
        elif ask is None:
            why = "sem cotação"
        elif ask > ceiling:
            why = "acima do teto do mandato"
        else:
            why = "dentro do teto, porém mais caro"
        out.append({
            "call_id": cid,
            "carrier_id": leg.carrier_id,
            "carrier_name": call.get("carrier_name"),
            "final_ask": float(ask) if ask is not None else None,
            "approved": float(leg.approved) if leg.approved is not None else None,
            "rounds": len(auction.legs[cid].asks) if hasattr(leg, "asks") else 0,
            "winner": cid == winner,
            "reason": why,
        })
    return sorted(out, key=lambda r: (not r["winner"], r["final_ask"] or 9e12))


async def _release_loser(call_id: str) -> None:
    """
    Encerra com cortesia, não cortando a linha no meio da frase.

    Detalhe que parece secundário e não é: essas transportadoras são
    fornecedores reais e vocês vão precisar delas na próxima carga.
    Também é o que faz as duas colunas desaparecerem bonito no palco.
    """
    from app.phase4_negotiating import SESSIONS   # import tardio: evita ciclo

    sess = SESSIONS.get(call_id)
    call = db.get("calls", call_id)
    try:
        if sess and not sess.closed:
            lang = (call.get("language") or "en")[:2]
            fala = {"pt": GOODBYE_PT, "es": GOODBYE_ES}.get(lang, GOODBYE_EN)
            sess.state.approved_utterances.add(fala)
            await sess._say(fala, approved=True)
            await asyncio.sleep(3.5)          # deixa a frase terminar
            await sess._close_call("auction_lost")
        else:
            tw.hangup(call.get("call_sid"))
    except Exception as e:
        print(f"[fase5] encerramento cortês falhou, desligando: {e}")
        tw.hangup(call.get("call_sid"))
    finally:
        db.update("calls", call_id, {"status": "done", "ended_at": "now()"})


# ═══════════════════════════════════════════════════════════════════════════
# as regras de parada
# ═══════════════════════════════════════════════════════════════════════════
async def run_stopping_rules(auction: Auction) -> None:
    """
    Disparado pela fase 3 assim que as pernas sobem. Os prazos vêm do
    relógio do porto, não de constantes.
    """
    soft = getattr(auction, "soft_deadline_s", 90)
    hard = getattr(auction, "hard_deadline_s", 180)
    op_id = auction.op["id"]

    # ── 1 · buy-it-now ─────────────────────────────────────────────────────
    try:
        await asyncio.wait_for(auction.at_target.wait(), timeout=soft)
        return          # try_reserve já liquidou tudo
    except asyncio.TimeoutError:
        pass

    if auction.reserved_by:
        return

    # ── 2 · soft deadline ──────────────────────────────────────────────────
    best = _best_within_mandate(auction)
    if best:
        r = await try_reserve(auction, best.call_id, best.best_ask, "soft_deadline")
        if r.get("granted"):
            return

    # ── 3 · hard deadline ──────────────────────────────────────────────────
    await asyncio.sleep(max(0, hard - soft))
    if auction.reserved_by:
        return

    best = _best_within_mandate(auction)
    if best:
        r = await try_reserve(auction, best.call_id, best.best_ask, "hard_deadline")
        if r.get("granted"):
            return

    # ── 4 · ninguém coube no mandato ───────────────────────────────────────
    # Não é bug: é o sistema dizendo que não consegue, em vez de estourar
    # o teto. A saída correta é humana.
    await settle(auction, winner_call_id=None, reason="no_offer_within_mandate")
    db.update("auctions", auction.id, {"status": "failed",
                                       "decision_reason": "no_offer_within_mandate"})
    melhor = min((l.best_ask for l in auction.legs.values() if l.best_ask), default=None)
    advance(op_id, Phase.ESCALATED, trigger="no_offer_within_mandate",
            auction_id=auction.id,
            payload={"best_ask": float(melhor) if melhor else None,
                     "ceiling": float(auction.max_rate),
                     "comparison": _build_comparison(auction, None, "no_offer")},
            detail=f"Nenhuma cotação dentro do teto de {auction.max_rate} "
                   f"{auction.op['currency']} — decisão humana")


def _best_within_mandate(auction: Auction):
    viable = [l for l in auction.legs.values()
              if l.best_ask is not None and l.best_ask <= auction.max_rate]
    return min(viable, key=lambda l: l.best_ask) if viable else None


# ═══════════════════════════════════════════════════════════════════════════
# reversão: reservou e não confirmou
# ═══════════════════════════════════════════════════════════════════════════
async def _confirmation_watchdog(auction: Auction, call_id: str) -> None:
    """
    Reservar não é comprometer. Se o vencedor cair, se contradisser ou
    simplesmente não confirmar, o lock volta e o segundo colocado assume.

    Sem isto, uma chamada que cai depois da reserva trava a operação em
    'reserved' para sempre — e no painel isso parece que o sistema morreu.
    """
    await asyncio.sleep(CONFIRM_TIMEOUT_S)

    op = db.get("operations", auction.op["id"])
    if op["phase"] != Phase.RESERVED.value:
        return                        # já comprometeu, ou já escalou

    call = db.get("calls", call_id)
    if call["status"] == "live":
        return                        # ainda conversando, dá mais tempo

    await release(auction, "winner_did_not_confirm")
    auction.legs[call_id].done = True

    runner = _best_within_mandate(auction)
    if runner and runner.call_id != call_id:
        r = await try_reserve(auction, runner.call_id, runner.best_ask,
                              "runner_up_after_release")
        if r.get("granted"):
            print(f"[fase5] segundo colocado assumiu: {runner.carrier_id}")
            return

    advance(auction.op["id"], Phase.ESCALATED, trigger="reservation_lost",
            auction_id=auction.id, call_id=call_id,
            detail="O vencedor não confirmou e não há segundo colocado viável")


# ═══════════════════════════════════════════════════════════════════════════
# rotas
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/comparison/{auction_id}")
async def comparison(auction_id: str):
    """O que o painel desenha na tabela de comparação."""
    a = db.get("auctions", auction_id)
    rows = db.c.table("auction_quotes").select("*") \
             .eq("auction_id", auction_id).order("winner", desc=True).execute().data
    return {"auction_id": auction_id, "status": a["status"],
            "reserved_by": a["reserved_by"], "amount": a["reserve_amount"],
            "reason": a["decision_reason"], "decided_at": a["decided_at"],
            "quotes": rows}


@router.post("/release/{auction_id}")
async def manual_release(auction_id: str, reason: str = "operator_override"):
    """Botão do painel: devolver o lock e reabrir para o segundo colocado."""
    auction = AUCTIONS.get(auction_id)
    if not auction:
        raise HTTPException(404, "leilão não está em memória neste worker")
    return await release(auction, reason)
