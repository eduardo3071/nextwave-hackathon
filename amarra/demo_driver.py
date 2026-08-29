"""
AMARRA · driver de ensaio.

Percorre TODAS as fases do início ao fim sem telefonar para ninguém.
Serve para duas coisas que valem horas:

  1. quem está no Lovable trabalha com o painel se mexendo de verdade,
     sem depender de a telefonia estar de pé;
  2. vocês ensaiam a narrativa da demo quantas vezes quiserem, de graça.

    python demo_driver.py                 # o roteiro do pitch, com pausas
    python demo_driver.py --fast          # sem pausas, para testar a UI
    python demo_driver.py --reset         # limpa e volta para 'detected'
"""
from __future__ import annotations

import argparse, time, uuid
from decimal import Decimal

from dotenv import load_dotenv
load_dotenv()

from app.db import db                      # noqa: E402
from app.phases import Phase, advance      # noqa: E402

REF = "MZO-GDL-4471"

CARRIERS = [
    {"id": "autolineas-mx",    "name": "Autolíneas MX",     "ask": Decimal(9800)},
    {"id": "transportes-ruiz", "name": "Transportes Ruiz",  "ask": Decimal(8900)},
    {"id": "fletes-bajio",     "name": "Fletes del Bajío",  "ask": Decimal(8400)},
]

PAUSE = 2.2


def beat(t: str) -> None:
    print(f"\n\033[36m── {t}\033[0m")


def hold(fast: bool, s: float = PAUSE) -> None:
    if not fast:
        time.sleep(s)


def say(call_id: str, who: str, text: str, t_ms: int) -> None:
    db.insert("utterances", {"call_id": call_id, "speaker": who,
                             "text": text, "t_ms": t_ms})


def run(fast: bool = False) -> None:
    op = db.operation(REF)
    m = db.mandate(op["id"])
    oid = op["id"]

    # ── 1–2 espinha ────────────────────────────────────────────────────────
    beat("1 · detected — o contêiner desceu, o relógio começou")
    advance(oid, Phase.DETECTED, trigger="container_discharged", force=True)
    hold(fast)

    beat("2 · mandate_issued — alvo 8.000, teto 9.000, coleta quinta")
    advance(oid, Phase.MANDATE_ISSUED, trigger="mandate_loaded")
    hold(fast)

    # ── 3 mercado ──────────────────────────────────────────────────────────
    beat("3 · market_open — três telefones tocam")
    auction_id = str(uuid.uuid4())
    db.insert("auctions", {"id": auction_id, "operation_id": oid,
                           "mandate_id": m["id"], "status": "running"})
    calls = {}
    for c in CARRIERS:
        cid = str(uuid.uuid4())
        db.insert("calls", {"id": cid, "auction_id": auction_id, "operation_id": oid,
                            "direction": "outbound", "carrier_id": c["id"],
                            "carrier_name": c["name"], "phone": "+52-demo",
                            "conference_name": f"demo-{c['id']}", "status": "dialing"})
        calls[c["id"]] = cid
        time.sleep(0.4 if not fast else 0)
    advance(oid, Phase.MARKET_OPEN, trigger="auction_dispatched",
            auction_id=auction_id, ctx={"carriers": len(CARRIERS)},
            detail=f"{len(CARRIERS)} transportadoras discando")
    hold(fast)

    # ── 4 negociando ───────────────────────────────────────────────────────
    beat("4 · negotiating — cotações cruzando entre as chamadas")
    for c in CARRIERS:
        db.update("calls", calls[c["id"]], {"status": "live"})
    advance(oid, Phase.NEGOTIATING, trigger="first_leg_live",
            call_id=calls["autolineas-mx"])

    say(calls["autolineas-mx"], "counterparty", "Para el jueves… nueve mil ochocientos.", 8200)
    db.insert("policy_events", {"call_id": calls["autolineas-mx"], "counterparty_ask": 9800,
                                "decision": "deny", "reason": "above_max_rate", "round": 1,
                                "utterance": "Está por encima de lo que puedo autorizar."})
    say(calls["autolineas-mx"], "agent", "Está por encima de lo que puedo autorizar.", 11000)
    hold(fast, 1.4)

    say(calls["transportes-ruiz"], "counterparty", "Ocho mil novecientos, salida jueves temprano.", 9100)
    db.insert("policy_events", {"call_id": calls["transportes-ruiz"], "counterparty_ask": 8900,
                                "decision": "allow", "amount": 8200,
                                "reason": "counter_within_mandate", "round": 1,
                                "utterance": "Puedo llegar a 8.200 pesos. ¿Cerramos así?"})
    say(calls["transportes-ruiz"], "agent", "Puedo llegar a 8.200 pesos. ¿Cerramos así?", 12400)
    hold(fast, 1.4)

    # a alavanca de mercado: a cotação da Ruiz entra viva na conversa da Bajío
    say(calls["fletes-bajio"], "agent",
        "Tengo una propuesta mejor en esta ruta. ¿Puedes acercarte a 8.400?", 10500)
    say(calls["fletes-bajio"], "counterparty", "Ocho mil cuatrocientos, jueves diez. Va.", 14800)
    db.insert("policy_events", {"call_id": calls["fletes-bajio"], "counterparty_ask": 8400,
                                "decision": "allow", "amount": 8400,
                                "reason": "at_or_below_target", "round": 2,
                                "utterance": "Cerrado en 8.400 pesos."})
    hold(fast)

    # ── 5 reserva: o lock ──────────────────────────────────────────────────
    beat("5 · reserved — buy-it-now, as outras duas desligam sozinhas")
    winner = calls["fletes-bajio"]
    db.update("auctions", auction_id, {"reserved_by": winner, "status": "committed",
                                       "winner_call_id": winner,
                                       "decision_reason": "buy_it_now"})
    for cid_name, cid in calls.items():
        if cid != winner:
            db.update("calls", cid, {"status": "done"})
    advance(oid, Phase.RESERVED, trigger="lock_acquired", auction_id=auction_id,
            call_id=winner, ctx={"reserved_by": winner},
            payload={"amount": 8400, "comparison": [
                {"carrier": "Fletes del Bajío", "ask": 8400, "winner": True,  "reason": "buy_it_now"},
                {"carrier": "Transportes Ruiz", "ask": 8900, "winner": False, "reason": "mais caro"},
                {"carrier": "Autolíneas MX",    "ask": 9800, "winner": False, "reason": "acima do teto"}]},
            detail="Reserva em 8.400 MXN")
    hold(fast)

    beat("6 · committed — acordo dito em voz alta")
    say(winner, "agent", "Cerrado en 8.400 pesos. Te mando la confirmación ahora.", 15600)
    advance(oid, Phase.COMMITTED, trigger="agreement_spoken", call_id=winner,
            ctx={"reserved_by": winner, "amount": 8400, "max_rate": float(m["max_rate"])},
            payload={"amount": 8400})
    db.insert("commitments", {
        "call_id": winner, "operation_id": oid, "field": "rate", "value": "8400 MXN",
        "quote": "ocho mil cuatrocientos", "t_start_ms": 14800, "t_end_ms": 16100,
        "confidence": 0.94, "state": "confirmed"})
    db.insert("commitments", {
        "call_id": winner, "operation_id": oid, "field": "pickup_at",
        "value": "2026-09-03T10:00", "quote": "jueves diez",
        "t_start_ms": 16200, "t_end_ms": 17000, "confidence": 0.91, "state": "confirmed"})
    hold(fast)

    # ── desvio: o caminhão quebra ──────────────────────────────────────────
    beat("desvio · disrupted — o dispatcher liga: caminhão quebrado")
    inbound = str(uuid.uuid4())
    db.insert("calls", {"id": inbound, "operation_id": oid, "direction": "inbound",
                        "carrier_id": "fletes-bajio", "carrier_name": "Fletes del Bajío",
                        "phone": "+52-demo", "conference_name": "demo-in",
                        "status": "live"})
    say(inbound, "counterparty", "Se descompuso el camión. Hasta el viernes puedo.", 4200)
    advance(oid, Phase.DISRUPTED, trigger="inbound_problem_reported", call_id=inbound,
            detail="Coleta empurrada para sexta — depois do free time")
    hold(fast)

    beat("desvio · renegotiating — o agente liga de volta para a segunda colocada")
    cb = str(uuid.uuid4())
    db.insert("calls", {"id": cb, "operation_id": oid, "auction_id": auction_id,
                        "direction": "outbound", "carrier_id": "transportes-ruiz",
                        "carrier_name": "Transportes Ruiz", "phone": "+52-demo",
                        "conference_name": "demo-cb", "status": "live"})
    advance(oid, Phase.RENEGOTIATING, trigger="callback_dialed", call_id=cb,
            detail="Ligando de volta para Transportes Ruiz")
    say(cb, "counterparty", "Jueves sí puedo, pero ya no a ocho novecientos. Nueve mil doscientos.", 6100)
    db.insert("policy_events", {"call_id": cb, "counterparty_ask": 9200, "decision": "deny",
                                "reason": "above_max_rate", "round": 1,
                                "utterance": "Está por encima de lo que puedo autorizar."})
    hold(fast)

    # ── desvio: a única decisão humana ─────────────────────────────────────
    beat("desvio · escalated — 200 pesos acima do teto, e mesmo assim é o melhor negócio")
    computation = {
        "option_late":    {"label": "Fletes del Bajío · sexta", "rate": 8400,
                           "demurrage": 2400, "total": 10800},
        "option_on_time": {"label": "Transportes Ruiz · quinta", "rate": 9200,
                           "demurrage": 0, "total": 9200},
        "delta": 1600, "exceeds_mandate_by": 200, "currency": "MXN",
    }
    db.insert("escalations", {
        "call_id": cb, "trigger": "above_max_rate",
        "brief": "Rota MZO-GDL. Alvo 8.000, teto 9.000. Bajío caiu para sexta (custo real "
                 "10.800 com demurrage). Ruiz faz quinta por 9.200. Excede o teto em 200 "
                 "e economiza 1.600. Precisa de aprovação.",
        "computation": computation, "human_phone": "+55-demo"})
    advance(oid, Phase.ESCALATED, trigger="above_max_rate", call_id=cb,
            payload=computation,
            detail="Decisão excede o mandato em 200 MXN — humano na linha")
    db.update("calls", cb, {"status": "escalated"})
    hold(fast, 3.5)

    beat("desvio · resolved — o supervisor aprova em nove segundos")
    advance(oid, Phase.RESOLVED, trigger="human_decision", call_id=cb,
            payload={"approved": True, "by": "supervisor"},
            detail="Aprovado: 9.200 na quinta, economia real de 1.600")
    hold(fast)

    beat("volta à espinha · committed com o valor aprovado")
    advance(oid, Phase.RESERVED, trigger="human_override", call_id=cb,
            ctx={"reserved_by": cb}, detail="Reserva movida para Transportes Ruiz")
    advance(oid, Phase.COMMITTED, trigger="agreement_spoken", call_id=cb,
            ctx={"reserved_by": cb, "amount": 9200, "max_rate": 99999},
            payload={"amount": 9200, "approved_by_human": True})
    db.insert("commitments", {
        "call_id": cb, "operation_id": oid, "field": "rate", "value": "9200 MXN",
        "quote": "nueve mil doscientos", "t_start_ms": 6100, "t_end_ms": 7400,
        "confidence": 0.93, "state": "confirmed"})
    db.update("calls", cb, {"status": "done"})
    hold(fast)

    # ── 7–8 ────────────────────────────────────────────────────────────────
    beat("7 · verified — cada campo ancorado no áudio, recap enviado")
    advance(oid, Phase.VERIFIED, trigger="evidence_anchored", call_id=cb,
            payload={"anchored": 3, "rejected": 0},
            detail="3 campos ancorados, 0 rejeitados")
    hold(fast)

    beat("8 · closed — dentro do free time")
    advance(oid, Phase.CLOSED, trigger="operation_closed", ctx={"recap_sent": True},
            detail="Coleta quinta 10:00 · 9.200 MXN · zero demurrage")
    print("\n\033[32m✓ percurso completo — 8 passos de espinha, 4 desvios\033[0m\n")


def reset() -> None:
    op = db.operation(REF)
    for t in ("phase_events", "commitments", "policy_events", "utterances",
              "escalations", "call_briefs"):
        try:
            db.c.table(t).delete().neq("id", 0).execute()
        except Exception:
            pass
    db.c.table("calls").delete().eq("operation_id", op["id"]).execute()
    db.c.table("auctions").delete().eq("operation_id", op["id"]).execute()
    db.update("operations", op["id"], {"phase": "detected", "status": "open",
                                       "phase_since": "now()"})
    print("reset ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset:
        reset()
    else:
        reset()
        run(fast=a.fast)
