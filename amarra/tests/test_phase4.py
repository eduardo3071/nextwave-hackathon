"""
A suíte adversarial. O enunciado LISTA o que o jurado vai fazer:
interromper, concordar e mudar, ficar calado, e empurrar além do mandato.
Isso é uma lista de casos de teste, não uma surpresa.
"""
from decimal import Decimal

import pytest

from app.policy import Decision, evaluate_offer


ADVERSARIAL = [
    ("teto_direto",         Decimal(12000),  Decision.DENY,  "não aceita, não repete o valor"),
    ("dentro_da_banda",     Decimal(9200),   Decision.DENY,  "recusa E escala — bom e proibido"),
    ("acima_do_equilibrio", Decimal(11000),  Decision.DENY,  "recusa e NÃO escala"),
    ("no_limite",           Decimal(9000),   Decision.ALLOW, "aceita, é o teto exato"),
    ("bate_o_alvo",         Decimal(7900),   Decision.ALLOW, "fecha na hora"),
    ("moeda_estranha",      Decimal(500),    Decision.ALLOW, "valor baixo, aceita"),
    ("absurdo",             Decimal(999999), Decision.DENY,  "recusa"),
]


@pytest.mark.parametrize("nome,ask,esperado,_", ADVERSARIAL,
                         ids=[a[0] for a in ADVERSARIAL])
def test_ataques(state, nome, ask, esperado, _):
    assert evaluate_offer(state, ask).decision is esperado


def test_banda_separa_recusar_de_escalar(band):
    assert band["from"] < 9200 <= band["to"]           # escala
    assert not (band["from"] < 11000 <= band["to"])    # só recusa


def test_alavanca_nao_vaza_nome_nem_teto(state):
    state.market_best = Decimal(8400)
    r = evaluate_offer(state, Decimal(8900))
    baixo = r.utterance.lower()
    assert "mejor" in baixo
    for vaz in ("ruiz", "bajío", "bajio", "9000", "9.000"):
        assert vaz not in baixo


def test_truncamento_no_barge_in(session):
    session.history.append({"role": "assistant",
                            "content": "Puedo llegar a 8.200 pesos y cerramos hoy mismo"})
    session.on_interrupt("Puedo llegar a", 460)
    assert session.history[-1]["content"] == "Puedo llegar a"
