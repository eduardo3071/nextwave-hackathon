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
