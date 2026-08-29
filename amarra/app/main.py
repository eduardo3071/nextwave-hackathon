"""
AMARRA · backend FastAPI.

    uvicorn app.main:app --reload --port 8000
    ngrok http --domain=SEU-DOMINIO.ngrok.app 8000

Rotas:
  POST /auction/start        dispara o leilão (3 chamadas escalonadas)
  POST /escalate/{call_id}   traz um humano para dentro da chamada
  POST /twiml/agent          TwiML da perna do agente (a TwiML App aponta aqui)
  WS   /ws                   ConversationRelay — o loop de conversa
  POST /twilio/status        eventos de chamada
  POST /twilio/conference    eventos de conference
  POST /twilio/recording     gravação pronta -> dispara a ancoragem
  POST /twilio/relay-done    fim da sessão do relay

O backend NUNCA fala com o frontend. Escreve no Supabase; o Realtime
empurra para o Lovable. Zero WebSocket próprio para o painel.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

from fastapi import BackgroundTasks, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from app import twilio_voice as tw
from app.agent import AgentSession, SESSIONS
from app.auction import AUCTIONS, Auction
from app.db import db
from app.evidence import anchor_recording
from app.phase1_detected import router as phase1_router, start_clock
from app.phase2_mandate import router as phase2_router
from app.phase3_market import router as phase3_router

app = FastAPI(title="Amarra")
app.include_router(phase1_router)
app.include_router(phase2_router)
app.include_router(phase3_router)

DIAL_SPACING_S = 1.2   # limite padrão da Twilio é 1 chamada/segundo


@app.on_event("startup")
async def resume_clocks():
    """Se o backend reiniciar no meio da demo, os relógios voltam sozinhos."""
    for op in (db.c.table("operations").select("id")
               .not_.in_("phase", ["closed", "failed"]).execute().data):
        start_clock(op["id"])


# ═══════════════════════════════════════════════════════════════════════════
# leilão
# ═══════════════════════════════════════════════════════════════════════════
@app.post("/auction/start")
async def auction_start(req: Request):
    body = await req.json()
    op = db.operation(body["operation_ref"])
    mandate = db.mandate(op["id"])
    carriers = body["carriers"]
    if len(carriers) < 3:
        return JSONResponse({"error": "R7 exige no mínimo 3 transportadoras"}, 400)

    auction = Auction(op=op, mandate=mandate)
    AUCTIONS[auction.id] = auction
    db.insert("auctions", {"id": auction.id, "operation_id": op["id"],
                           "mandate_id": mandate["id"], "status": "running"})

    async def fire():
        for c in carriers:
            conf = f"amarra-{auction.id[:8]}-{c['id']}"
            call_id = str(uuid.uuid4())
            db.insert("calls", {
                "id": call_id, "auction_id": auction.id, "operation_id": op["id"],
                "direction": "outbound", "carrier_id": c["id"],
                "carrier_name": c.get("name"), "phone": c["phone"],
                "conference_name": conf, "status": "dialing",
            })
            sid = tw.dial_counterparty(to=c["phone"], conf=conf)
            db.update("calls", call_id, {"call_sid": sid})
            tw.join_agent(conf=conf, call_id=call_id)
            auction.register(call_id=call_id, carrier_id=c["id"], conf=conf, sid=sid)
            await asyncio.sleep(DIAL_SPACING_S)   # ← respeita o CPS
        await auction.run_deadlines()

    asyncio.create_task(fire())
    return {"auction_id": auction.id, "carriers": len(carriers)}


# ═══════════════════════════════════════════════════════════════════════════
# escalação — R6 / D5
# ═══════════════════════════════════════════════════════════════════════════
@app.post("/escalate/{call_id}")
async def escalate(call_id: str, req: Request):
    body = await req.json() if await req.body() else {}
    sess: AgentSession | None = SESSIONS.get(call_id)
    call = db.get("calls", call_id)

    brief = sess.brief() if sess else "Sem sessão ativa."
    computation = body.get("computation") or (sess.computation() if sess else None)

    human_sid = tw.join_human(
        conf=call["conference_name"],
        human_phone=os.environ["SUPERVISOR_PHONE"],
        coach_call_sid=sess.agent_call_sid if sess else None,   # entra sussurrando
    )
    db.insert("escalations", {
        "call_id": call_id, "trigger": body.get("trigger", "manual"),
        "brief": brief, "computation": computation,
        "human_phone": os.environ["SUPERVISOR_PHONE"],
    })
    db.update("calls", call_id, {"status": "escalated"})
    if sess:
        sess.escalated = True
    return {"ok": True, "human_call_sid": human_sid}


@app.post("/escalate/{call_id}/take-over")
async def take_over(call_id: str, req: Request):
    body = await req.json()
    call = db.get("calls", call_id)
    tw.human_take_over(conf=call["conference_name"], human_call_sid=body["human_call_sid"])
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# TwiML da perna do agente
# ═══════════════════════════════════════════════════════════════════════════
@app.post("/twiml/agent")
async def twiml_agent(req: Request):
    q = req.query_params
    xml = tw.agent_twiml(conf=q.get("conf"), call_id=q.get("call_id"),
                         lang=q.get("lang", "es-MX"))
    return Response(content=xml, media_type="application/xml")


@app.post("/twiml/inbound")
async def twiml_inbound(req: Request):
    """R2 — alguém liga para o nosso número. Mesma estrutura: conference + agente."""
    form = await req.form()
    call_id = str(uuid.uuid4())
    conf = f"amarra-in-{call_id[:8]}"
    op = db.operation(os.getenv("DEMO_OPERATION_REF", "MZO-GDL-4471"))
    db.insert("calls", {"id": call_id, "operation_id": op["id"], "direction": "inbound",
                        "phone": form.get("From"), "call_sid": form.get("CallSid"),
                        "conference_name": conf, "status": "live"})
    asyncio.get_event_loop().call_later(
        0.5, lambda: tw.join_agent(conf=conf, call_id=call_id))
    return Response(content=tw.conference_twiml(conf), media_type="application/xml")


# ═══════════════════════════════════════════════════════════════════════════
# ConversationRelay — o loop de conversa
# ═══════════════════════════════════════════════════════════════════════════
@app.websocket("/ws")
async def relay(ws: WebSocket):
    await ws.accept()
    sess: AgentSession | None = None
    t0 = time.monotonic()

    try:
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.get("type")

            if kind == "setup":
                params = msg.get("customParameters", {}) or {}
                call_id = params.get("call_id")
                sess = AgentSession(call_id=call_id, ws=ws,
                                    agent_call_sid=msg.get("callSid"), t0=t0)
                SESSIONS[call_id] = sess
                db.update("calls", call_id, {"status": "live"})
                await sess.open()

            elif kind == "prompt" and sess:
                # fala da contraparte, já transcrita
                await sess.on_speech(msg["voicePrompt"], lang=msg.get("lang"))

            elif kind == "interrupt" and sess:
                # BARGE-IN (bônus B1). Truncar o histórico no ponto do corte é
                # obrigatório: sem isso o modelo acha que falou a frase inteira.
                sess.on_interrupt(msg.get("utteranceUntilInterrupt", ""),
                                  msg.get("durationUntilInterruptMs", 0))

            elif kind == "dtmf" and sess:
                sess.on_dtmf(msg.get("digit"))

            elif kind == "error":
                print("relay error:", msg)

    except WebSocketDisconnect:
        pass
    finally:
        if sess:
            await sess.close()


# ═══════════════════════════════════════════════════════════════════════════
# webhooks
# ═══════════════════════════════════════════════════════════════════════════
@app.post("/twilio/status")
async def status(req: Request):
    f = await req.form()
    db.update_by("calls", "call_sid", f.get("CallSid"),
                 {"status": {"completed": "done", "failed": "failed",
                             "in-progress": "live"}.get(f.get("CallStatus"), "dialing")})
    return Response(status_code=204)


@app.post("/twilio/conference")
async def conference(req: Request):
    f = await req.form()
    if f.get("StatusCallbackEvent") == "participant-join" and f.get("ParticipantLabel") == "human_agent":
        db.insert_event("escalations", f.get("ConferenceSid"), {"human_joined_at": "now()"})
    return Response(status_code=204)


@app.post("/twilio/recording")
async def recording(req: Request, bg: BackgroundTasks):
    """
    A gravação ficou pronta. Aqui nasce a evidência (Pilar 02):
    Deepgram devolve palavras com start/end, e cada compromisso é ancorado.
    """
    f = await req.form()
    url = f.get("RecordingUrl")
    conf_sid = f.get("ConferenceSid")
    call = db.find("calls", "conference_sid", conf_sid) or db.find("calls", "call_sid", f.get("CallSid"))
    if call:
        db.update("calls", call["id"], {"recording_url": url, "ended_at": "now()"})
        bg.add_task(anchor_recording, call["id"], url)
    return Response(status_code=204)


@app.post("/twilio/relay-done")
async def relay_done(req: Request):
    return Response(content="<Response/>", media_type="application/xml")


@app.get("/health")
async def health():
    return {"ok": True, "sessions": len(SESSIONS), "auctions": len(AUCTIONS)}
