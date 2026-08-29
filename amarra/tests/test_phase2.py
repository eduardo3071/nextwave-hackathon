from decimal import Decimal

from app.phase2_mandate import (
    canonicalize,
    concession_ladder,
    break_even,
    escalation_band,
    mandate_hash,
)

T, C, DEM = Decimal(8000), Decimal(9000), Decimal(2400)


def test_escada_sobe_e_nunca_estoura():
    l = concession_ladder(T, C, 4)
    assert l == [8200.0, 8400.0, 8600.0, 8800.0]
    assert l == sorted(l) and max(l) <= float(C)


def test_escada_com_teto_igual_ao_alvo_e_plana():
    assert concession_ladder(T, T, 4) == [8000.0] * 4


def test_ponto_de_equilibrio():
    assert break_even(T, DEM) == Decimal("10400.00")


def test_banda_de_escalacao_contem_o_caso_do_pitch():
    b = escalation_band(C, break_even(T, DEM))
    assert b["from"] == 9000.0 and b["to"] == 10400.0
    assert b["from"] < 9200 <= b["to"]        # ← o 9.200 da Transportes Ruiz


def test_sem_banda_quando_demurrage_nao_justifica():
    assert escalation_band(Decimal(20000), break_even(T, DEM)) is None


def test_hash_e_estavel_e_sensivel(op, mandate):
    l, be = concession_ladder(T, C, 4), break_even(T, DEM)
    c1 = canonicalize(op, mandate, l, be, escalation_band(C, be))
    assert mandate_hash(c1) == mandate_hash(dict(reversed(list(c1.items()))))
    c2 = dict(c1)
    c2["authority"] = {**c1["authority"], "max_rate": "9500"}
    assert mandate_hash(c1) != mandate_hash(c2)   # mexeu no teto, mudou a identidade
