import pytest

from app.phase3_market import Carrier, admit, deadline_budget


def _c(i, phone):
    return Carrier(id=f"c{i}", name=f"C{i}", phone=phone)


TRES = [_c(1, "+525511110001"), _c(2, "+525511110002"), _c(3, "+525511110003")]


def test_recusa_menos_de_tres(op_issued, mandate_issued):
    with pytest.raises(ValueError, match="R7"):
        admit(op_issued, mandate_issued, TRES[:2])


def test_recusa_numeros_repetidos(op_issued, mandate_issued):
    dup = TRES[:2] + [_c(3, "+525511110001")]
    with pytest.raises(ValueError, match="repetidos"):
        admit(op_issued, mandate_issued, dup)


def test_recusa_sem_mandato_emitido(op_issued, mandate_issued):
    m = {**mandate_issued, "mandate_hash": None}
    with pytest.raises(ValueError, match="mandato não emitido"):
        admit(op_issued, m, TRES)


def test_orcamento_de_pernas(op_issued, mandate_issued, monkeypatch):
    # 3 negociações = 6 pernas + 1 de escalação = 7 > 3
    monkeypatch.setattr("app.phase3_market.CONCURRENCY", 3)
    with pytest.raises(ValueError, match="orçamento de pernas"):
        admit(op_issued, mandate_issued, TRES)
    monkeypatch.setattr("app.phase3_market.CONCURRENCY", 10)
    planned, budget, _ = admit(op_issued, mandate_issued, TRES)
    assert planned == 6 and budget == 10


def test_e164():
    with pytest.raises(ValueError, match="E.164"):
        Carrier(id="x", name="X", phone="11999998888")


@pytest.mark.parametrize("left,soft_max,hard_max", [
    (100_000, 90, 180),   # muita folga: os tetos
    (1_200, 30, 60),      # 20 min: comprime
    (0, 30, 60),          # expirado: decidir é urgente
])
def test_prazos_saem_do_relogio(left, soft_max, hard_max):
    soft, hard = deadline_budget(left)
    assert soft <= soft_max and hard <= hard_max and hard > soft
