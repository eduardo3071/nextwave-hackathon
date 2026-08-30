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

# Carrega `amarra/.env` ANTES de qualquer `from app.*` — twilio_voice, db e
# outros leem env vars no import time. Sem isso, `uvicorn app.main:app`
# quebra com KeyError('TWILIO_ACCOUNT_SID').
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

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
from app.phase1_detected import router as phase1_router, start_clock
from app.phase2_mandate import router as phase2_router
from app.phase3_market import router as phase3_router
from app.phase4_negotiating import router as phase4_router
from app.phase5_reserved import router as phase5_router
from app.phase6_committed import router as phase6_router
from app.phase7_verified import router as phase7_router, verify_call
from app.phase8_closed import router as phase8_router

app = FastAPI(title="Amarra")
app.include_router(phase1_router)
app.include_router(phase2_router)
app.include_router(phase3_router)
# phase4 registra /ws antes do @app.websocket("/ws") velho — Starlette usa a
# primeira rota que casa, então NegotiationSession assume no lugar da AgentSession.
app.include_router(phase4_router)
app.include_router(phase5_router)
app.include_router(phase6_router)
app.include_router(phase7_router)
app.include_router(phase8_router)

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
    """
    Quando a Twilio invoca uma TwiML App via `to="app:AP..."`, os parâmetros
    depois do `?` na URI viram QUERY STRING se o método for GET, ou FORM BODY
    se for POST. Precisamos ler dos dois porque a TwiML App tem que ser POST
    (nossos endpoints só aceitam POST) e a maioria dos exemplos usa GET.
    """
    q = req.query_params
    form = await req.form()
    conf = q.get("conf") or form.get("conf")
    call_id = q.get("call_id") or form.get("call_id")
    lang = q.get("lang") or form.get("lang") or "es-MX"
    if not conf or not call_id:
        print(f"[/twiml/agent] parâmetros faltando: conf={conf!r} call_id={call_id!r}")
        # Não embute "None" no TwiML — pendura educado em vez de deixar a
        # sessão da fase 4 morrer no lookup UUID.
        return Response(content="<Response><Hangup/></Response>",
                        media_type="application/xml")
    xml = tw.agent_twiml(conf=conf, call_id=call_id, lang=lang)
    return Response(content=xml, media_type="application/xml")


@app.post("/twiml/inbound")
async def twiml_inbound(req: Request):
    """
    R2 — alguém liga para o nosso número. Mesma estrutura: conference + agente.

    `?demo=1` na URL marca a chamada como iniciada POR NÓS (via botão do painel
    ou dial_me.py), pra o Lovable distinguir no `calls.direction`:
      - 'inbound'         → alguém realmente ligou pro nosso número (R2)
      - 'outbound_demo'   → nós disparamos pra o próprio celular (teste)
    """
    form = await req.form()
    is_demo = req.query_params.get("demo") == "1"
    call_id = str(uuid.uuid4())
    conf = f"amarra-in-{call_id[:8]}"
    op = db.operation(os.getenv("DEMO_OPERATION_REF", "MZO-GDL-4471"))
    db.insert("calls", {
        "id": call_id, "operation_id": op["id"],
        "direction": "outbound_demo" if is_demo else "inbound",
        "phone": form.get("From"), "call_sid": form.get("CallSid"),
        "conference_name": conf, "status": "live",
    })
    asyncio.get_event_loop().call_later(
        0.5, lambda: tw.join_agent(conf=conf, call_id=call_id))
    return Response(content=tw.conference_twiml(conf), media_type="application/xml")


@app.post("/demo/call-me")
async def demo_call_me(req: Request):
    """
    Botão do painel: dispara a Twilio pra discar o SUPERVISOR_PHONE do .env
    (ou o número que vier no body). A chamada roda o mesmo TwiML de
    /twiml/inbound?demo=1 — tudo que já funciona pra chamada de entrada
    roda igual, e a Twilio paga (do saldo) em vez da tarifa internacional
    da sua operadora.

    Body JSON opcional: {"to": "+55...", "lang": "en"}
    Devolve: {"call_sid": "CA...", "to": "...", "from": "..."}
    """
    body = await req.json() if await req.body() else {}
    to = body.get("to") or os.getenv("SUPERVISOR_PHONE")
    if not to:
        return JSONResponse(
            {"error": "SUPERVISOR_PHONE não configurado no .env; "
                      "passe 'to' no body"}, 422)

    from_number = os.environ["TWILIO_PHONE_NUMBER"]
    host = os.environ["PUBLIC_HOST"]
    url = f"https://{host}/twiml/inbound?demo=1"

    from twilio.base.exceptions import TwilioRestException
    try:
        call = tw.client.calls.create(
            to=to, from_=from_number, url=url, method="POST",
        )
    except TwilioRestException as e:
        return JSONResponse({"error": f"{e.code}: {e.msg}"}, 400)

    return {"call_sid": call.sid, "to": to, "from": from_number,
            "url": url, "status": "queued"}


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

    A Twilio manda `CallSid` do participante da conference que gerou o
    recording — usamos isso pra achar a linha da chamada. Envolvemos em
    try/except pra sempre devolver 204 e evitar retries do Twilio caso
    algum passo posterior falhe.
    """
    f = await req.form()
    url = f.get("RecordingUrl")
    call_sid = f.get("CallSid")
    try:
        call = db.find("calls", "call_sid", call_sid) if call_sid else None
        if call:
            db.update("calls", call["id"], {"recording_url": url, "ended_at": "now()"})
            # fase 7: baixa da Twilio autenticado, transcreve, ancora cada citação,
            # sobe o áudio pra URL pública, dispara o recap e avança a fase.
            bg.add_task(verify_call, call["id"], url)
        else:
            print(f"[/twilio/recording] CallSid {call_sid} não bateu com nenhuma "
                  f"linha em calls — recording ignorado")
    except Exception as e:
        print(f"[/twilio/recording] falhou, ignorando: {e}")
    return Response(status_code=204)


@app.post("/twilio/relay-done")
async def relay_done(req: Request):
    return Response(content="<Response/>", media_type="application/xml")


@app.get("/health")
async def health():
    return {"ok": True, "sessions": len(SESSIONS), "auctions": len(AUCTIONS)}
