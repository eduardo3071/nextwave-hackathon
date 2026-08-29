"""
conftest.py — env falso para os testes.

Importar app.phase1_detected acaba disparando app.db, que exige
SUPABASE_URL e SUPABASE_SERVICE_KEY no import. Nos testes puros
(que não tocam o banco) não queremos exigir credenciais reais.
"""
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key-for-tests")
# twilio_voice.py lê estas no import; sem elas o módulo não carrega.
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACfake0000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "fake-twilio-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")
os.environ.setdefault("PUBLIC_HOST", "test.ngrok.app")
os.environ.setdefault("TWIML_APP_SID", "APfake0000000000000000000000000000")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-openai-key-for-tests")

import pytest


@pytest.fixture
def op() -> dict:
    """Uma operação como o banco devolveria (Supabase serializa datas em ISO)."""
    return {
        "ref": "MZO-GDL-4471",
        "container": "MSKU 784 2219",
        "origin": "Puerto de Manzanillo",
        "destination": "Bodega Guadalajara",
        "cargo_value_usd": 180000,
        "currency": "MXN",
        "free_time_ends": "2026-09-03T18:00:00-06:00",
        "demurrage_per_day": 2400,
    }


@pytest.fixture
def mandate() -> dict:
    """Mandato como o banco devolveria (antes da emissão — sem hash ainda)."""
    return {
        "target_rate": 8000,
        "max_rate": 9000,
        "min_rate": 6000,
        "max_rounds": 4,
        "pickup_from": "2026-09-03T08:00:00-06:00",
        "pickup_to": "2026-09-03T18:00:00-06:00",
        "may_reveal_best_price": True,
        "may_reveal_competitor_name": False,
        "may_reveal_max_rate": False,
    }


@pytest.fixture
def op_issued(op) -> dict:
    """op depois da fase 2: já em 'mandate_issued'."""
    return {**op, "phase": "mandate_issued"}


@pytest.fixture
def mandate_issued(mandate) -> dict:
    """mandate depois da fase 2: com hash cunhado e artefatos compilados."""
    return {
        **mandate,
        "mandate_hash": "mdt_test0123456789abcdef012345",
        "ladder": [8200.0, 8400.0, 8600.0, 8800.0],
        "break_even_rate": 10400.0,
        "escalation_band": {"from": 9000.0, "to": 10400.0, "width": 1400.0,
                            "meaning": "acima da autoridade, abaixo do prejuízo"},
    }


@pytest.fixture
def state():
    """Estado de negociação do caso: alvo 8000, teto 9000, 4 rodadas."""
    from decimal import Decimal
    from app.policy import Mandate, NegotiationState
    return NegotiationState(mandate=Mandate(
        target_rate=Decimal(8000),
        max_rate=Decimal(9000),
        min_rate=Decimal(6000),
        max_rounds=4,
        currency="MXN",
    ))


@pytest.fixture
def band(mandate_issued) -> dict:
    """A banda de escalação compilada pela fase 2."""
    return mandate_issued["escalation_band"]


@pytest.fixture
def session(monkeypatch):
    """
    NegotiationSession barebones: bypass do __init__ (que exige DB e mandato
    emitido) porque os testes só exercitam métodos sem I/O.
    """
    import time
    from app import phase4_negotiating as p4

    monkeypatch.setattr(p4.db, "insert", lambda *a, **k: None)

    s = p4.NegotiationSession.__new__(p4.NegotiationSession)
    s.call_id = "test-call"
    s.history = []
    s.actions = []
    s.t0 = time.monotonic()
    s.last_input_at = time.monotonic()
    return s


@pytest.fixture
def auction(monkeypatch):
    """
    Auction real + DB simulado. `db.rpc('try_reserve_auction', ...)` implementa
    a mesma semântica da função Postgres — checa status/reserved_by/teto e
    devolve o mesmo JSON. Isso deixa os testes exercitarem a corrida do lock
    e o cinto-e-suspensórios do teto sem precisar de banco real.
    """
    import uuid
    from decimal import Decimal
    from types import SimpleNamespace

    from app import auction as auction_mod
    from app import twilio_voice as tw_mod
    from app.db import db as real_db

    op = {"id": str(uuid.uuid4()), "ref": "TEST-001", "currency": "MXN",
          "container": "TEST-CONT", "free_time_ends": "2026-09-03T18:00:00-06:00",
          "demurrage_per_day": 2400, "phase": "negotiating"}
    mandate = {"id": str(uuid.uuid4()), "target_rate": 8000, "max_rate": 9000,
               "min_rate": 6000, "max_rounds": 4}

    a = auction_mod.Auction(op=op, mandate=mandate)
    call_ids = [str(uuid.uuid4()) for _ in range(3)]
    asks = [Decimal(8400), Decimal(8900), Decimal(9200)]
    for i, (cid, ask) in enumerate(zip(call_ids, asks)):
        sid = f"CA{'0' * 30}{i}"
        a.legs[cid] = auction_mod.Leg(call_id=cid, carrier_id=f"c{i}",
                                       conf=f"conf-{i}", sid=sid)
        a.legs[cid].best_ask = ask

    # ── estado do "banco" ──────────────────────────────────────────────
    state = {"status": "running", "reserved_by": None,
             "reserve_amount": None, "reserved_at": None}
    ceiling = float(mandate["max_rate"])

    def _rpc(fn, params):
        if fn == "try_reserve_auction":
            # mesma ordem do SQL: reserved_by antes de status
            if state["reserved_by"] is not None:
                r = {"granted": False, "reason": "already_reserved",
                     "winner": state["reserved_by"]}
            elif state["status"] != "running":
                r = {"granted": False, "reason": "auction_not_running",
                     "winner": state["reserved_by"]}
            elif float(params["p_amount"]) > ceiling:
                r = {"granted": False, "reason": "above_max_rate",
                     "ceiling": ceiling}
            else:
                state["status"] = "committed"
                state["reserved_by"] = params["p_call_id"]
                state["reserve_amount"] = params["p_amount"]
                r = {"granted": True, "winner": params["p_call_id"],
                     "amount": params["p_amount"], "reason": params["p_reason"]}
            return SimpleNamespace(data=r)
        if fn == "release_reservation":
            if state["reserved_by"] is None:
                r = {"released": False, "reason": "not_reserved"}
            else:
                was = state["reserved_by"]
                state["reserved_by"] = None
                state["reserve_amount"] = None
                state["status"] = "running"
                r = {"released": True, "was": was}
            return SimpleNamespace(data=r)
        return SimpleNamespace(data=None)   # advance_phase é no-op nos testes

    calls_by_id = {cid: {"id": cid, "carrier_name": f"C{i}",
                          "operation_id": op["id"], "language": "es-MX",
                          "call_sid": a.legs[cid].sid, "status": "live"}
                    for i, cid in enumerate(call_ids)}

    def _get(table, id_):
        if table == "calls":
            return calls_by_id.get(id_, {"id": id_, "call_sid": None,
                                          "carrier_name": None, "language": None,
                                          "status": "done"})
        if table == "operations":
            return op
        if table == "auctions":
            return {"id": id_, "operation_id": op["id"], **state,
                    "decision_reason": None, "decided_at": None}
        return {}

    class _Chain:
        def table(self, *_): return self
        def update(self, *_, **__): return self
        def insert(self, *_, **__): return self
        def select(self, *_, **__): return self
        def eq(self, *_, **__): return self
        def order(self, *_, **__): return self
        def execute(self):
            return SimpleNamespace(data=[], count=0)

    monkeypatch.setattr(real_db, "rpc", _rpc)
    monkeypatch.setattr(real_db, "get", _get)
    monkeypatch.setattr(real_db, "insert", lambda t, r: r)
    monkeypatch.setattr(real_db, "update", lambda *a, **k: None)
    monkeypatch.setattr(real_db, "c", _Chain())
    monkeypatch.setattr(tw_mod, "hangup", lambda sid: None)

    return a


@pytest.fixture
def discharge_payload() -> dict:
    """O evento do caso Manzanillo, alinhado ao discharge_manzanillo.json."""
    return {
        "ref": "MZO-GDL-4471",
        "container": "MSKU 784 2219",
        "origin": "Puerto de Manzanillo",
        "destination": "Bodega Guadalajara",
        "cargo_value_usd": 180000,
        "currency": "MXN",
        "discharged_at": "2026-09-01T14:20:00-06:00",
        "free_days": 2,
        "demurrage_per_day": 2400,
        "mandate": {
            "target_rate": 8000,
            "max_rate": 9000,
            "min_rate": 6000,
            "max_rounds": 4,
            "pickup_from": "2026-09-03T08:00:00-06:00",
            "pickup_to": "2026-09-03T18:00:00-06:00",
        },
        "source": {"system": "nauta", "agent": "nina", "event": "container_discharged"},
    }
