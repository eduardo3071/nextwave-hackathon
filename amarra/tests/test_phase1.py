from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.phase1_detected import clock_state, exposure, DischargeEvent


def _in(h):
    return datetime.now(timezone.utc) + timedelta(hours=h)


def test_estados_do_relogio():
    assert clock_state(_in(28)) == "safe"
    assert clock_state(_in(5)) == "warning"
    assert clock_state(_in(1)) == "critical"
    assert clock_state(_in(-1)) == "expired"
    assert clock_state(_in(28), stopped=True) == "stopped"


def test_exposicao():
    e = exposure(_in(10), Decimal(2400))
    assert e["state"] == "safe"
    assert 9.9 < e["hours_remaining"] < 10.1
    assert e["exposure_if_missed"] == 2400.0


def test_idempotencia_e_estavel(discharge_payload):
    a = DischargeEvent(**discharge_payload)
    b = DischargeEvent(**discharge_payload)
    assert a.idempotency_key() == b.idempotency_key()


def test_free_days_vira_deadline(discharge_payload):
    ev = DischargeEvent(**discharge_payload)
    assert ev.deadline() == ev.discharged_at + timedelta(days=2)
