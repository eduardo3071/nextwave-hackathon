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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app import twilio_voice as tw
from app.phase4_negotiating import NegotiationSession as AgentSession, SESSIONS
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
from app.phase_disruption import router as disruption_router

app = FastAPI(title="Amarra")

# CORS — o painel Lovable é servido de https://nextwave-hackathon.lovable.app
# e faz fetch cross-origin pro nosso ngrok. Sem esse middleware, o browser
# barra qualquer POST com "No 'Access-Control-Allow-Origin' header is present".
# Modo hackathon: permissivo. Pra produção, restringir `allow_origins`.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,     # sem cookies; * exige credentials=False
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

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
app.include_router(disruption_router)

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
    raw = await req.body()
    if raw:
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
    else:
        body = {}
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
    lang = q.get("lang") or form.get("lang") or "en-US"
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


@app.post("/demo/dial-market")
async def demo_dial_market(req: Request):
    """
    Botão "Abrir Mercado (3)" do painel. Dispara os 3 carriers em paralelo.

    Lê os 3 carriers de `carriers.json` (raiz do amarra/) por padrão. Aceita
    override no body: {"carriers": [{"id","name","phone"}, ...],
                       "operation_ref": "..."}

    Auto-reseta a operação para 'mandate_issued' antes de discar — sem isso,
    o segundo uso do botão bate no admit() com "operação está em
    'negotiating'". Se você QUER preservar a operação anterior, passe
    `{"reset": false}`.
    """
    from pathlib import Path
    from app.phase3_market import open_market, OpenMarket, Carrier

    raw = await req.body()
    if raw:
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
    else:
        body = {}
    op_ref = body.get("operation_ref") or os.getenv("DEMO_OPERATION_REF",
                                                     "MZO-GDL-4471")
    should_reset = body.get("reset", True)

    # 1 · carriers (override no body OU do carriers.json)
    carriers = body.get("carriers")
    if not carriers:
        cfg_path = Path(__file__).resolve().parent.parent / "carriers.json"
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            carriers = cfg.get("carriers", [])
        except Exception as e:
            return JSONResponse(
                {"error": f"carriers.json inválido ou ausente: {e}"}, 500)

    # 2 · auto-reset
    op = db.operation(op_ref)
    if should_reset and op["phase"] != "mandate_issued":
        _demo_reset(op["id"])
        op = db.operation(op_ref)   # relê depois do update

    # 3 · dispara /phase3/open
    try:
        req_obj = OpenMarket(
            operation_ref=op_ref,
            carriers=[Carrier(**c) for c in carriers],
        )
    except Exception as e:
        return JSONResponse({"error": f"payload inválido: {e}"}, 422)

    return await open_market(req_obj)


@app.post("/demo/scenario/full")
async def demo_scenario_full(req: Request):
    """
    Orquestrador — encadeia os 7 objetivos do enunciado numa sequência
    fluida que aterrissa nos 6 resultados esperados.

    Passos (síncrono até o mercado abrir, depois assíncrono):
      1. Se a operação não estiver em `mandate_issued` → reseta
      2. Se o mandato não tem hash → emite via /phase2/issue (Objetivo 1 setup)
      3. Dispara /phase3/open com os 3 carriers do carriers.json
         → cobre Objetivos 1, 5, 7 + Resultado 1 (chamadas paralelas + comparação)
      4. Enquanto isso, log estruturado do que cada perna faz
      5. Ao commit + evidência → cobre Objetivos 3a, 3b, 4 + Resultado 4

    Depois do /demo/scenario/full, o pitch continua com:
      • Ligação de entrada real (Obj 2 + Resultado 2) — dispara callback (Resultado 3)
      • Um "9200 pesos" (Obj 6 + Resultado 5) — banda de escalação
      • `/phase8/close` — fecha e gera dossiê

    Body opcional: {"operation_ref": "...", "carriers": [...], "issue_mandate": true}
    Retorna o plano do que vai acontecer + auction_id.
    """
    from pathlib import Path
    from app.phase2_mandate import issue as issue_mandate
    from app.phase3_market import open_market, OpenMarket, Carrier

    raw = await req.body()
    if raw:
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
    else:
        body = {}
    op_ref = body.get("operation_ref") or os.getenv("DEMO_OPERATION_REF",
                                                     "MZO-GDL-4471")

    # 1 · localiza operação
    try:
        op = db.operation(op_ref)
    except Exception as e:
        return JSONResponse({"error": f"operação '{op_ref}' não existe: {e}"}, 404)

    plan = {"operation_ref": op_ref, "operation_id": op["id"],
            "steps": [], "objectives_covered": []}

    # 2 · reset se necessário
    if op["phase"] not in ("detected", "mandate_issued"):
        _demo_reset(op["id"])
        op = db.operation(op_ref)
        plan["steps"].append({"step": "reset", "note": "operação devolvida a mandate_issued"})

    # 3 · emite mandato se ainda não emitido (idempotente)
    m = db.mandate(op["id"])
    if not m.get("mandate_hash") and body.get("issue_mandate", True):
        try:
            issued = await issue_mandate(op["id"])
            plan["steps"].append({"step": "issue_mandate",
                                  "mandate_hash": issued.get("mandate_hash")})
            plan["objectives_covered"].append("obj_5_authority_hashed")
        except Exception as e:
            print(f"[scenario/full] issue falhou (ok se já emitido): {e}")

    # 4 · lê carriers (override ou carriers.json)
    carriers_in = body.get("carriers")
    if not carriers_in:
        cfg_path = Path(__file__).resolve().parent.parent / "carriers.json"
        try:
            carriers_in = json.loads(cfg_path.read_text(encoding="utf-8"))["carriers"]
        except Exception as e:
            return JSONResponse({"error": f"carriers.json inválido: {e}"}, 500)

    # 5 · abre mercado (fase 3) — 3 chamadas em paralelo
    try:
        market_req = OpenMarket(
            operation_ref=op_ref,
            carriers=[Carrier(**c) for c in carriers_in],
        )
        result = await open_market(market_req)
    except Exception as e:
        return JSONResponse({"error": f"open_market falhou: {e}"}, 400)

    plan["steps"].append({"step": "open_market", **result})
    plan["objectives_covered"].extend([
        "obj_1_outbound_3_carriers_parallel",
        "obj_7_market_not_a_call",
    ])
    plan["expected_results"] = {
        "result_1_ready_now": "3 columns filling + auction_quotes table",
        "result_4_after_recording": "commitments anchored, recap email sent, "
                                    "audio ▶ button plays exact slice",
        "result_5_if_9200_offered": "escalation card shows computation, "
                                     "supervisor gets called",
        "next_action_for_result_2_and_3": (
            f"call the Twilio number {os.getenv('TWILIO_PHONE_NUMBER','?')} "
            "from a cell and say 'truck broke, need to reschedule' — the "
            "agent will call `report_disruption` and dial the runner-up"),
    }
    return plan


@app.get("/demo/scenario/status/{operation_ref}")
async def demo_scenario_status(operation_ref: str):
    """
    Vista meta: para cada um dos 7 Objetivos e 6 Resultados do enunciado,
    mostra se o ESTADO ATUAL do banco cumpre o requisito.
    """
    try:
        op = db.operation(operation_ref)
    except Exception:
        return JSONResponse({"error": "operação não encontrada"}, 404)

    op_id = op["id"]
    m = db.mandate(op_id)
    auction = next(iter(db.c.table("auctions").select("*")
                        .eq("operation_id", op_id).execute().data), None)
    calls = db.c.table("calls").select("*").eq("operation_id", op_id).execute().data
    quotes = ((db.c.table("auction_quotes").select("*")
               .eq("auction_id", auction["id"]).execute().data)
              if auction else [])
    commits = db.c.table("commitments").select("*").eq("operation_id", op_id).execute().data
    call_ids = [c["id"] for c in calls] or ["-"]
    policy = db.c.table("policy_events").select("*").in_("call_id", call_ids).execute().data
    escals = db.c.table("escalations").select("*").in_("call_id", call_ids).execute().data
    recaps = db.c.table("recap_deliveries").select("*").eq("operation_id", op_id).execute().data
    briefs = db.c.table("call_briefs").select("*").in_("call_id", call_ids).execute().data
    events = db.c.table("phase_events").select("*").eq("operation_id", op_id).order("id").execute().data
    dossier = next(iter(db.c.table("dossiers").select("*")
                        .eq("operation_id", op_id).execute().data), None)

    anchored = [c for c in commits if c.get("anchor_state") == "anchored"]
    outbound_calls = [c for c in calls if c.get("direction") == "outbound"]
    inbound_calls = [c for c in calls if c.get("direction") == "inbound"]
    branches = [e["phase"] for e in events if e.get("kind") == "branch"]

    return {
        "operation_ref": operation_ref,
        "phase": op["phase"],
        "mandate_hash": m.get("mandate_hash"),
        "objectives": {
            "1_outbound_3_carriers": {
                "met": len(outbound_calls) >= 3,
                "evidence": f"{len(outbound_calls)} outbound calls",
            },
            "2_inbound_understood": {
                "met": len(inbound_calls) > 0,
                "evidence": f"{len(inbound_calls)} inbound calls processed",
            },
            "3a_recap_sent": {
                "met": any(r["status"] == "sent" for r in recaps),
                "evidence": f"{sum(1 for r in recaps if r['status']=='sent')} sent recaps",
            },
            "3b_audio_anchored": {
                "met": len(anchored) > 0,
                "evidence": f"{len(anchored)}/{len(commits)} commitments anchored to audio",
            },
            "4_call_brief": {
                "met": len(briefs) > 0,
                "evidence": f"{len(briefs)} call briefs written",
            },
            "5_conversation_system_consistent": {
                "met": bool(m.get("mandate_hash")) and
                       all(p.get("mandate_hash") for p in policy if p.get("decision") != "block"),
                "evidence": f"mandate_hash present + {len(policy)} policy events "
                            f"({sum(1 for p in policy if p['decision']=='block')} blocks)",
            },
            "6_escalation_mid_call": {
                "met": len(escals) > 0 or "escalated" in branches,
                "evidence": f"{len(escals)} escalations rows, "
                            f"branches: {branches}",
            },
            "7_market_comparison_audit": {
                "met": len(quotes) >= 3,
                "evidence": f"{len(quotes)} rows in auction_quotes "
                            f"(winner: {next((q['carrier_name'] for q in quotes if q.get('winner')), '—')})",
            },
        },
        "results": {
            "1_three_carriers_booked": {
                "met": auction and auction.get("status") == "committed"
                       and len(quotes) >= 3,
                "artifact": "auction_quotes table + winner marked",
            },
            "2_inbound_disruption_understood": {
                "met": "disrupted" in branches,
                "artifact": "phase_events row with kind='branch' phase='disrupted'",
            },
            "3_renegotiation": {
                "met": "renegotiating" in branches,
                "artifact": "phase_events row phase='renegotiating' + new call",
            },
            "4_auditable_trail": {
                "met": len(anchored) > 0 and any(r["status"] == "sent" for r in recaps)
                       and len(briefs) > 0,
                "artifact": "commitments with t_start_ms + recap_deliveries.status=sent + call_briefs",
            },
            "5_escalation_takeover": {
                "met": any(e.get("resolution") for e in escals),
                "artifact": f"escalations.resolution set: {[e.get('resolution') for e in escals]}",
            },
            "6_trial_by_fire": {
                "met": any(p["decision"] == "block" for p in policy)
                       or all(p.get("amount", 0) is None or float(p["amount"] or 0) <= float(m["max_rate"])
                              for p in policy if p["decision"] == "allow"),
                "artifact": "policy_events: 0 ALLOW above ceiling; blocks incremented if model tried",
            },
        },
        "final_artifact": {
            "dossier_available": dossier is not None,
            "headline": dossier.get("headline") if dossier else None,
        },
    }


@app.post("/demo/recap/{operation_id}")
async def demo_send_recap(operation_id: str, req: Request):
    """
    Dispara o recap R3a (email + SMS) agora, sob demanda — sem esperar a
    gravação processar. Útil pra:
      - Testar canais separadamente antes da demo
      - Reenviar recap após falha
      - Cobrir o R3a mesmo quando a fase 7 (áncora) ainda não completou

    Body opcional: {"call_id": "..."} — se omitido, usa a última call da
    operação. Retorna delivery status (email/sms + rows em recap_deliveries).
    """
    from app.phase7_verified import send_recap

    raw = await req.body()
    if raw:
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
    else:
        body = {}
    call_id = body.get("call_id")
    if not call_id:
        # última call da operação
        calls = (db.c.table("calls").select("id")
                 .eq("operation_id", operation_id)
                 .order("started_at", desc=True).limit(1).execute().data)
        if not calls:
            return JSONResponse(
                {"error": "operação sem nenhuma chamada — nada pra sumarizar"}, 404)
        call_id = calls[0]["id"]

    try:
        result = await send_recap(operation_id, call_id)
    except Exception as e:
        return JSONResponse({"error": f"send_recap falhou: {e}"}, 500)

    return {"operation_id": operation_id, "call_id": call_id, "delivery": result}


@app.post("/demo/call-judge/{judge_id}")
async def demo_call_judge(judge_id: str):
    """
    Dispara /demo/call-me apontando pra o número do jurado dado.
    Lê judges.json (raiz do amarra/), busca pelo id ("walter", "denis"),
    usa o phone do jurado, e a Twilio disca. Custo do saldo Twilio; jurado
    só recebe (grátis).

    Exemplo: POST /demo/call-judge/walter
    """
    from pathlib import Path

    cfg_path = Path(__file__).resolve().parent.parent / "judges.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse({"error": f"judges.json inválido: {e}"}, 500)

    judge = next((j for j in cfg.get("judges", []) if j["id"] == judge_id), None)
    if not judge:
        available = [j["id"] for j in cfg.get("judges", [])]
        return JSONResponse(
            {"error": f"jurado '{judge_id}' não encontrado",
             "available": available}, 404)

    from_number = os.environ["TWILIO_PHONE_NUMBER"]
    host = os.environ["PUBLIC_HOST"]
    url = f"https://{host}/twiml/inbound?demo=1"

    from twilio.base.exceptions import TwilioRestException
    try:
        call = tw.client.calls.create(
            to=judge["phone"], from_=from_number, url=url, method="POST",
        )
    except TwilioRestException as e:
        hint = ""
        if e.code == 21215:
            hint = (f" · Geo permission pra {judge.get('country','?')} desligada — "
                    f"Console → Voice → Settings → Geo Permissions")
        return JSONResponse({"error": f"{e.code}: {e.msg}{hint}",
                             "judge": judge}, 400)

    return {"call_sid": call.sid, "judge": judge, "url": url}


@app.get("/demo/judges")
async def demo_judges():
    """Lista os jurados configurados em judges.json (nome, phone, email)."""
    from pathlib import Path
    cfg_path = Path(__file__).resolve().parent.parent / "judges.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return cfg
    except Exception as e:
        return JSONResponse({"error": f"judges.json inválido: {e}"}, 500)


@app.post("/demo/test-email")
async def demo_test_email(req: Request):
    """
    Manda 1 email de teste via Resend. Prova que RESEND_API_KEY funciona
    e que o destinatário RECAP_TO está recebendo.

    Body opcional: {"to": "...", "subject": "...", "body": "..."}
    Padrões vêm do .env.
    """
    import httpx as _httpx
    raw = await req.body()
    if raw:
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
    else:
        body = {}
    to = body.get("to") or os.getenv("RECAP_TO")
    key = os.getenv("RESEND_API_KEY")

    if not to:
        return JSONResponse({"error": "to faltando (ou setar RECAP_TO)"}, 422)
    if not key:
        return JSONResponse({"error": "RESEND_API_KEY faltando no .env"}, 422)

    from_addr = os.getenv("RECAP_FROM", "amarra@resend.dev")
    subject = body.get("subject") or "[Amarra] Email de teste do R3a"
    text = body.get("body") or (
        "Amarra · email de teste.\n\nSe você recebeu isto, a integração com "
        "Resend está funcionando e este é o canal confiável do R3a "
        "(confirmação escrita pós-chamada).\n\n— Amarra")

    try:
        async with _httpx.AsyncClient(timeout=30) as c:
            r = await c.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {key}"},
                json={"from": from_addr, "to": [to],
                      "subject": subject, "text": text})
    except Exception as e:
        return JSONResponse({"error": f"exception: {e}"}, 500)

    if r.status_code >= 300:
        return JSONResponse({"error": r.text[:400], "status": r.status_code,
                             "hint": "confira RESEND_API_KEY e se o remetente "
                                     "está verificado no Resend"}, 400)

    return {"email_id": r.json().get("id"), "to": to, "from": from_addr,
            "subject": subject}


@app.get("/demo/recap/deliveries/{operation_id}")
async def demo_recap_deliveries(operation_id: str):
    """Lista os recaps enviados pra essa operação (leitura do painel/debug)."""
    rows = (db.c.table("recap_deliveries").select("*")
            .eq("operation_id", operation_id)
            .order("created_at", desc=True).limit(50).execute().data)
    return {"operation_id": operation_id, "count": len(rows), "deliveries": rows}


@app.post("/demo/reset")
async def demo_reset(operation_ref: str | None = None):
    """
    Devolve a operação de demo para 'mandate_issued' e limpa auction/calls.
    Não recria mandato (o hash cunhado na fase 2 continua o mesmo).
    Útil pra rodar o dial_market várias vezes seguidas.
    """
    ref = operation_ref or os.getenv("DEMO_OPERATION_REF", "MZO-GDL-4471")
    op = db.operation(ref)
    _demo_reset(op["id"])
    return {"ok": True, "operation_ref": ref}


def _demo_reset(operation_id: str) -> None:
    """Limpa auction/calls e devolve a fase pra mandate_issued."""
    # apaga em ordem (calls tem cascade via auction_id → auctions)
    db.c.table("calls").delete().eq("operation_id", operation_id).execute()
    db.c.table("auctions").delete().eq("operation_id", operation_id).execute()
    db.c.table("phase_events").delete().eq("operation_id", operation_id).execute()
    db.update("operations", operation_id,
              {"phase": "mandate_issued", "phase_since": "now()",
               "status": "open", "outcome": None, "closed_at": None})
    print(f"[/demo/reset] operação {operation_id} devolvida a 'mandate_issued'")


@app.post("/demo/call-me")
async def demo_call_me(req: Request):
    """
    Botão do painel: dispara a Twilio pra discar o SUPERVISOR_PHONE do .env
    (ou o número que vier no body). A chamada roda o mesmo TwiML de
    /twiml/inbound?demo=1 — tudo que já funciona pra chamada de entrada
    roda igual, e a Twilio paga (do saldo) em vez da tarifa internacional
    da sua operadora.

    Body JSON opcional:
      {"to": "+55...", "lang": "en", "dry_run": true}

    Com `dry_run: true` valida a admissão SEM discar (mesma ergonomia do
    /demo/dial-market): confere que backend, número, host e operação estão
    prontos, devolve o que FARIA.

    Devolve (dry): {"dry_run": true, "admitted": bool, "to","from","url",
                    "warnings":[...]}
    Devolve (live): {"call_sid": "CA...", "to","from","url","status":"queued"}
    """
    raw = await req.body()
    if raw:
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
    else:
        body = {}
    to = body.get("to") or os.getenv("SUPERVISOR_PHONE")
    dry_run = bool(body.get("dry_run"))

    if not to:
        return JSONResponse(
            {"error": "SUPERVISOR_PHONE não configurado no .env; "
                      "passe 'to' no body"}, 422)

    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    host = os.getenv("PUBLIC_HOST")
    if not from_number or not host:
        return JSONResponse(
            {"error": "TWILIO_PHONE_NUMBER ou PUBLIC_HOST faltando no .env"},
            422)

    url = f"https://{host}/twiml/inbound?demo=1"

    # ── validações de admissão (bate quase igual ao /phase3/open) ──────────
    warnings: list[str] = []
    op_ref = os.getenv("DEMO_OPERATION_REF", "MZO-GDL-4471")
    try:
        op = db.operation(op_ref)
    except Exception as e:
        return JSONResponse(
            {"error": f"operação '{op_ref}' não encontrada no banco: {e}"}, 422)

    try:
        mandate = db.mandate(op["id"])
        if not mandate.get("mandate_hash"):
            warnings.append(
                "mandato não emitido — a NegotiationSession vai recusar "
                "abrir. Rode POST /phase2/issue/{op_id} antes.")
    except Exception:
        warnings.append("mandate row ausente; a chamada vai crashar no /ws")

    import re
    E164 = re.compile(r"^\+[1-9]\d{7,14}$")
    if not E164.match(to):
        return JSONResponse(
            {"error": f"'{to}' não é E.164 (esperado +55XXXXXXXXXXX)"}, 422)
    if to == from_number:
        return JSONResponse(
            {"error": "TO e FROM são o mesmo número — a Twilio recusa"}, 422)

    # ── dry-run: para aqui e devolve o preview ─────────────────────────────
    if dry_run:
        return {
            "dry_run": True,
            "admitted": True,
            "to": to,
            "from": from_number,
            "url": url,
            "operation_ref": op_ref,
            "operation_phase": op["phase"],
            "mandate_hash": mandate.get("mandate_hash") if 'mandate' in dir() else None,
            "warnings": warnings,
            "cost_estimate_usd_per_min": 0.03,
        }

    # ── live: dispara de verdade ───────────────────────────────────────────
    from twilio.base.exceptions import TwilioRestException
    try:
        call = tw.client.calls.create(
            to=to, from_=from_number, url=url, method="POST",
        )
    except TwilioRestException as e:
        return JSONResponse({"error": f"{e.code}: {e.msg}"}, 400)

    return {"call_sid": call.sid, "to": to, "from": from_number,
            "url": url, "status": "queued", "warnings": warnings}


# ConversationRelay's /ws is registered by phase4_router above (see comment
# next to include_router(phase4_router)). No duplicate handler here.


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
