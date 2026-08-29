import pytest

from app.phase8_closed import _hms, build_dossier, close_operation
from app.phases import ALLOWED, Phase, PhaseError


@pytest.mark.asyncio
async def test_nao_fecha_sem_recap(op_verified_sem_recap):
    """R3a com dente: sem confirmação escrita, não encerra."""
    with pytest.raises(PhaseError, match="R3a"):
        await close_operation(op_verified_sem_recap["id"])


def test_dossie_soma_o_financeiro(op_committed):
    d = build_dossier(op_committed["id"], "booked")
    f = d["financial"]
    assert f["agreed_rate"] == 9200.0
    assert f["exceeded_mandate"] is True and f["exceeded_by"] == 200.0
    assert f["human_approved"] is True          # passou pelo desvio 'resolved'
    assert f["closed_within_free_time"] is True


def test_dossie_conta_os_desvios(op_committed):
    d = build_dossier(op_committed["id"], "booked")
    assert set(d["operational"]["branches"]) >= {"disrupted", "escalated", "resolved"}


def test_headline_e_derivada(op_committed):
    d = build_dossier(op_committed["id"], "booked")
    h = d["headline"]
    assert "ligações" in h and "decisão humana" in h and "folga" in h


def test_duracao_legivel():
    assert _hms(9000) == "9s"
    assert _hms(75_000) == "1m 15s"
    assert _hms(3_720_000) == "1h 02m"


def test_fechada_nao_reabre_em_silencio(op_closed):
    assert ALLOWED[Phase.CLOSED] == set()       # terminal de verdade
