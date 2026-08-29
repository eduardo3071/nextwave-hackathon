"""
AMARRA · FASE 8 — closed

A operação encerra e vira dossiê.

A guarda de `closed` exige `recap_sent`. Não é burocracia: é o requisito
R3a — sem confirmação escrita enviada, o compromisso não está verificado
duas vezes, e uma operação não fecha por meia verificação.

Tudo aqui é DERIVADO. Nenhum número desta fase é escrito à mão: as durações
saem de `phase_events.ms_in_previous`, o financeiro sai do mandato e do
compromisso confirmado, e a folga sai do relógio da fase 1.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException

from app import twilio_voice as tw
from app.db import db
from app.phases import SPEC, Phase, PhaseError, advance

router = APIRouter(prefix="/phase8", tags=["fase 8 · closed"])


def _num(v) -> Decimal | None:
    if v in (None, ""):
        return None
    s = re.sub(r"[^\d.\-]", "", str(v))
    return Decimal(s) if s else None


def _hms(ms: int | None) -> str:
    if not ms:
        return "—"
    s = ms // 1000
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}m" if h else (f"{m}m {s:02d}s" if m else f"{s}s")


# ═══════════════════════════════════════════════════════════════════════════
# o dossiê
# ═══════════════════════════════════════════════════════════════════════════
def build_dossier(operation_id: str, outcome: str) -> dict:
    op = db.get("operations", operation_id)
    mandate = db.mandate(operation_id)
    events = db.c.table("phase_events").select("*") \
               .eq("operation_id", operation_id).order("id").execute().data
    calls = db.c.table("calls").select("*") \
              .eq("operation_id", operation_id).execute().data
    commits = db.c.table("commitments").select("*") \
                .eq("operation_id", operation_id).order("id").execute().data
    escal = db.c.table("escalations").select("*") \
              .in_("call_id", [c["id"] for c in calls] or ["-"]).execute().data
    policy = db.c.table("policy_events").select("decision") \
               .in_("call_id", [c["id"] for c in calls] or ["-"]).execute().data
    auction = next(iter(db.c.table("auctions").select("*")
                        .eq("operation_id", operation_id).execute().data), None)
    quotes = (db.c.table("auction_quotes").select("*")
              .eq("auction_id", auction["id"]).execute().data) if auction else []

    # ── linha do tempo, com duração de cada fase ───────────────────────────
    timeline = [{
        "phase": e["phase"],
        "label": SPEC[Phase(e["phase"])].label_pt,
        "kind": e["kind"],
        "trigger": e["trigger"],
        "detail": e["detail"],
        "at": e["created_at"],
        "held_previous_ms": e["ms_in_previous"],
        "held_previous": _hms(e["ms_in_previous"]),
    } for e in events]

    inicio = events[0]["created_at"] if events else op["created_at"]
    total_ms = sum(e["ms_in_previous"] or 0 for e in events)

    # ── financeiro ─────────────────────────────────────────────────────────
    rate = next((c for c in commits
                 if c["field"] == "rate" and c["state"] == "confirmed"), None)
    acordado = _num(rate["value"]) if rate else None
    alvo = _num(mandate["target_rate"])
    teto = _num(mandate["max_rate"])
    dem = _num(op["demurrage_per_day"]) or Decimal(0)
    fte = datetime.fromisoformat(op["free_time_ends"])
    agora = datetime.now(timezone.utc)
    folga_s = int((fte - agora).total_seconds())
    aprovado_por_humano = any(
        e["phase"] == Phase.RESOLVED.value for e in events)

    financial = {
        "currency": op["currency"],
        "target_rate": float(alvo) if alvo else None,
        "max_rate": float(teto) if teto else None,
        "agreed_rate": float(acordado) if acordado else None,
        "vs_target": float(acordado - alvo) if acordado and alvo else None,
        "vs_ceiling": float(teto - acordado) if acordado and teto else None,
        "exceeded_mandate": bool(acordado and teto and acordado > teto),
        "exceeded_by": float(acordado - teto) if acordado and teto and acordado > teto else 0.0,
        "human_approved": aprovado_por_humano,
        "demurrage_per_day": float(dem),
        # o que teria custado perder a janela: a tarifa mais um dia de demurrage
        "demurrage_avoided": float(dem) if folga_s > 0 and acordado else 0.0,
        "slack_hours": round(folga_s / 3600, 1),
        "closed_within_free_time": folga_s > 0,
    }

    # ── operacional ────────────────────────────────────────────────────────
    cp = [c for c in calls if c.get("leg_role") in (None, "counterparty")]
    atendidas = [c for c in cp if c.get("answered_at")]
    blocks = len([p for p in policy if p["decision"] == "block"])
    ancorados = [c for c in commits if c["anchor_state"] == "anchored"]
    rejeitados = [c for c in commits if c["anchor_state"] == "not_found"]
    desvios = [e for e in events if e["kind"] == "branch"]

    # o tempo que o humano levou para decidir = quanto ficamos em 'escalated'
    decisao_ms = next((e["ms_in_previous"] for e in events
                       if e["phase"] == Phase.RESOLVED.value), None)

    operational = {
        "calls_dialed": len(cp),
        "calls_answered": len(atendidas),
        "carriers_compared": len(quotes),
        "policy_blocks": blocks,
        "escalations": len(escal),
        "human_decision_ms": decisao_ms,
        "human_decision": _hms(decisao_ms),
        "branches": [e["phase"] for e in desvios],
        "commitments_anchored": len(ancorados),
        "commitments_rejected": len(rejeitados),
        "total_duration_ms": total_ms,
        "total_duration": _hms(total_ms),
        "started_at": inicio,
    }

    headline = _headline(op, financial, operational, outcome)

    return {
        "operation_id": operation_id,
        "outcome": outcome,
        "mandate_hash": mandate.get("mandate_hash"),
        "headline": headline,
        "financial": financial,
        "operational": operational,
        "timeline": timeline,
        "comparison": quotes,
        "commitments": [{
            "field": c["field"], "value": c["value"], "quote": c["quote"],
            "state": c["state"], "anchor_state": c["anchor_state"],
            "said_ms": c["t_start_ms"], "confirmed_ms": c.get("affirmation_t_start_ms"),
            "confidence": c["confidence"], "audio_url": c.get("audio_url"),
            "mandate_hash": c.get("mandate_hash"),
        } for c in commits],
        "escalations": [{
            "trigger": e["trigger"], "brief": e["brief"],
            "computation": e.get("computation"), "resolution": e.get("resolution"),
        } for e in escal],
    }


def _headline(op: dict, fin: dict, ops: dict, outcome: str) -> str:
    """A frase de fechamento do pitch, calculada e não inventada."""
    if outcome != "booked":
        return (f"{op['ref']} · encerrada sem contratação · "
                f"{ops['calls_dialed']} ligações · {ops['escalations']} escalações")
    partes = [f"{ops['calls_dialed']} ligações"]
    if ops["branches"]:
        partes.append(f"{len(ops['branches'])} desvio"
                      + ("s" if len(ops["branches"]) > 1 else ""))
    if ops["human_decision_ms"]:
        partes.append(f"uma decisão humana de {ops['human_decision']}")
    if fin["closed_within_free_time"]:
        partes.append(f"{fin['slack_hours']}h de folga no relógio")
    return f"{op['ref']} · " + " · ".join(partes)


# ═══════════════════════════════════════════════════════════════════════════
# encerramento
# ═══════════════════════════════════════════════════════════════════════════
async def close_operation(operation_id: str, *, reason: str = "operation_closed") -> dict:
    """
    Encerra. A guarda exige recap enviado — R3a.
    """
    op = db.get("operations", operation_id)
    if op["phase"] == Phase.CLOSED.value:
        d = db.c.table("dossiers").select("*").eq("operation_id", operation_id) \
              .execute().data
        return {"already_closed": True, "dossier": d[0] if d else None}

    # ── R3a: o recap saiu? ─────────────────────────────────────────────────
    entregas = db.c.table("recap_deliveries").select("status") \
                 .eq("operation_id", operation_id).execute().data
    recap_ok = any(e["status"] == "sent" for e in entregas)
    if not recap_ok:
        raise PhaseError(
            "R3a: nenhum recap escrito foi entregue — a operação não fecha "
            "sem a confirmação por escrito. Rode a fase 7 ou envie manualmente.")

    _cleanup(operation_id)
    _stop_clock(operation_id)

    dossier = build_dossier(operation_id, outcome="booked")
    _persist(dossier)

    db.update("operations", operation_id,
              {"closed_at": "now()", "outcome": "booked"})
    advance(operation_id, Phase.CLOSED, trigger=reason,
            ctx={"recap_sent": True},
            payload={"headline": dossier["headline"],
                     "financial": dossier["financial"],
                     "operational": dossier["operational"]},
            detail=dossier["headline"])

    print(f"[fase8] {dossier['headline']}")
    return dossier


async def fail_operation(operation_id: str, *, reason: str, detail: str) -> dict:
    """
    O outro terminal. Um sistema que não consegue e DIZ que não conseguiu
    é comportamento correto — por isso `failed` é fase de primeira classe
    e também gera dossiê.
    """
    op = db.get("operations", operation_id)
    if op["phase"] in (Phase.CLOSED.value, Phase.FAILED.value):
        return {"already_terminal": True}

    _cleanup(operation_id)
    _stop_clock(operation_id)

    dossier = build_dossier(operation_id, outcome="failed")
    _persist(dossier)

    db.update("operations", operation_id,
              {"closed_at": "now()", "outcome": "failed"})
    advance(operation_id, Phase.FAILED, trigger=reason, detail=detail,
            payload={"headline": dossier["headline"]})
    return dossier


def _persist(d: dict) -> None:
    row = {"operation_id": d["operation_id"], "outcome": d["outcome"],
           "financial": d["financial"], "operational": d["operational"],
           "timeline": d["timeline"], "commitments": d["commitments"],
           "comparison": d["comparison"], "escalations": d["escalations"],
           "mandate_hash": d["mandate_hash"], "headline": d["headline"]}
    try:
        db.insert("dossiers", row)
    except Exception:
        db.c.table("dossiers").update(row) \
          .eq("operation_id", d["operation_id"]).execute()


def _stop_clock(operation_id: str) -> None:
    """O cronômetro congela com a folga que sobrou. Não zera."""
    from app.phase1_detected import stop_clock
    stop_clock(operation_id)


def _cleanup(operation_id: str) -> None:
    """Nenhuma perna pendurada, nenhuma sessão órfã."""
    from app.phase4_negotiating import SESSIONS
    for c in db.c.table("calls").select("id,call_sid,status") \
               .eq("operation_id", operation_id).execute().data:
        if c["status"] in ("live", "dialing", "escalated"):
            tw.hangup(c.get("call_sid"))
            db.update("calls", c["id"], {"status": "done", "ended_at": "now()"})
        s = SESSIONS.pop(c["id"], None)
        if s:
            s.closed = True


# ═══════════════════════════════════════════════════════════════════════════
# reabertura: a operação fechou e o telefone toca de novo
# ═══════════════════════════════════════════════════════════════════════════
async def reopen(operation_id: str, *, call_id: str, reason: str) -> dict:
    """
    `closed` é terminal na máquina de fases — de propósito. Uma chamada de
    entrada sobre uma operação encerrada não muda o passado em silêncio:
    ela abre uma NOVA operação, ligada à anterior.

    O dossiê fechado continua valendo. É o que impede que a trilha auditável
    seja reescrita depois do fato.
    """
    velha = db.get("operations", operation_id)
    if velha["phase"] not in (Phase.CLOSED.value, Phase.FAILED.value):
        raise HTTPException(409, "operação não está encerrada — use o desvio "
                                 "'disrupted' em vez de reabrir")
    nova = db.insert("operations", {
        "ref": f"{velha['ref']}-R{int(datetime.now().timestamp()) % 1000}",
        "container": velha["container"], "origin": velha["origin"],
        "destination": velha["destination"],
        "cargo_value_usd": velha["cargo_value_usd"],
        "free_time_ends": velha["free_time_ends"],
        "demurrage_per_day": velha["demurrage_per_day"],
        "currency": velha["currency"],
        "source_event": {"reopened_from": operation_id, "reason": reason,
                         "call_id": call_id},
    })
    db.insert("phase_events", {
        "operation_id": nova["id"], "phase": Phase.DETECTED.value,
        "previous": None, "kind": "spine", "trigger": "reopened",
        "detail": f"Reaberta a partir de {velha['ref']} — {reason}",
        "call_id": call_id, "payload": {"reopened_from": operation_id}})
    return {"new_operation_id": nova["id"], "ref": nova["ref"]}


# ═══════════════════════════════════════════════════════════════════════════
# rotas
# ═══════════════════════════════════════════════════════════════════════════
@router.post("/close/{operation_id}")
async def close(operation_id: str):
    try:
        return await close_operation(operation_id)
    except PhaseError as e:
        raise HTTPException(409, str(e))


@router.post("/fail/{operation_id}")
async def fail(operation_id: str, reason: str = "manual",
               detail: str = "Encerrada manualmente sem contratação"):
    return await fail_operation(operation_id, reason=reason, detail=detail)


@router.get("/dossier/{operation_id}")
async def dossier(operation_id: str):
    """
    O artefato auditável. Um jurado abre isto e vê a operação inteira sem
    precisar de vocês do lado.
    """
    rows = db.c.table("dossiers").select("*") \
             .eq("operation_id", operation_id).execute().data
    if rows:
        return rows[0]
    op = db.get("operations", operation_id)   # prévia antes de encerrar
    return build_dossier(operation_id,
                         outcome="in_progress" if op["phase"] not in
                         (Phase.CLOSED.value, Phase.FAILED.value) else op["phase"])


@router.post("/reopen/{operation_id}")
async def reopen_route(operation_id: str, call_id: str, reason: str = "inbound_after_close"):
    return await reopen(operation_id, call_id=call_id, reason=reason)
