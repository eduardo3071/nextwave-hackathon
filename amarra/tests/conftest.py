"""
conftest.py — env falso para os testes.

Importar app.phase1_detected acaba disparando app.db, que exige
SUPABASE_URL e SUPABASE_SERVICE_KEY no import. Nos testes puros
(que não tocam o banco) não queremos exigir credenciais reais.
"""
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key-for-tests")

import pytest


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
