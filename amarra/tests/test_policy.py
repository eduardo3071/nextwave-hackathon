"""
A prova que vai para o palco.

    pytest tests/test_policy.py -q

Rode isso AO VIVO durante a defesa técnica. Duzentos casos, décimos de
segundo, e a invariante que importa: nenhuma decisão ALLOW jamais autoriza
um valor acima do teto do mandato.
"""

from decimal import Decimal

import pytest

from app.policy import (
    Decision,
    Mandate,
    NegotiationState,
    evaluate_offer,
    gate_text,
)

M = Mandate(target_rate=Decimal(8000), max_rate=Decimal(9000),
            min_rate=Decimal(6000), max_rounds=4, currency="MXN")


def st(**kw) -> NegotiationState:
    return NegotiationState(mandate=M, **kw)


# ── A INVARIANTE ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ask", [Decimal(x) for x in range(1000, 40001, 200)])
@pytest.mark.parametrize("rounds", [0, 1, 2, 3])
def test_nunca_autoriza_acima_do_teto(ask, rounds):
    """~800 combinações. É esta linha que vocês projetam na tela."""
    r = evaluate_offer(st(rounds=rounds), ask)
    if r.decision is Decision.ALLOW:
        assert r.amount is not None
        assert r.amount <= M.max_rate, f"VIOLAÇÃO: autorizou {r.amount} com teto {M.max_rate}"


@pytest.mark.parametrize("ask", [Decimal(x) for x in range(1000, 40001, 500)])
def test_nunca_revela_o_teto(ask):
    r = evaluate_offer(st(), ask)
    if r.utterance:
        assert "9.000" not in r.utterance and "9000" not in r.utterance


# ── comportamentos ──────────────────────────────────────────────────────────
def test_bate_o_alvo_fecha_na_hora():
    r = evaluate_offer(st(), Decimal(7800))
    assert r.decision is Decision.ALLOW
    assert r.amount == Decimal(7800)
    assert r.reason == "at_or_below_target"


def test_dentro_do_teto_contra_oferta_em_escada():
    a = evaluate_offer(st(rounds=0), Decimal(8900))
    b = evaluate_offer(st(rounds=2), Decimal(8900))
    assert a.decision is b.decision is Decision.ALLOW
    assert a.amount < b.amount <= M.max_rate   # cede devagar, nunca estoura


def test_acima_do_teto_recusa_sempre():
    for ask in (Decimal(9001), Decimal(9500), Decimal(12000), Decimal(99999)):
        r = evaluate_offer(st(), ask)
        assert r.decision is Decision.DENY
        assert r.amount is None
        assert r.reason == "above_max_rate"


def test_duzentos_pesos_acima_ainda_e_acima():
    """O caso do pitch: 9.200 é a melhor escolha econômica e mesmo assim não passa."""
    r = evaluate_offer(st(), Decimal(9200))
    assert r.decision is Decision.DENY


def test_rodadas_esgotadas_escala():
    r = evaluate_offer(st(rounds=4), Decimal(8500))
    assert r.decision is Decision.ESCALATE
    assert r.utterance is None      # em escalação o agente não fala número nenhum


def test_alavanca_de_mercado_nao_nomeia_concorrente():
    s = st(market_best=Decimal(8400))
    r = evaluate_offer(s, Decimal(8900))
    assert "better" in r.utterance.lower()
    for nome in ("ruiz", "bajío", "bajio", "autolíneas", "autolineas"):
        assert nome not in r.utterance.lower()


# ── o gate de áudio ─────────────────────────────────────────────────────────
def test_gate_bloqueia_valor_nao_aprovado():
    s = st()
    s.approved_utterances.add("I can go up to 8,200 pesos. Shall we close on that?")
    out, blocked = gate_text(s, "Look, I'll leave it at 9,500 pesos and we close.")
    assert blocked is True
    assert "9,500" not in out


def test_gate_deixa_passar_frase_aprovada():
    s = st()
    frase = "Closed at 8,400 pesos. I'll send you the confirmation now."
    s.approved_utterances.add(frase)
    out, blocked = gate_text(s, frase)
    assert blocked is False and out == frase


def test_gate_ignora_texto_sem_valor():
    out, blocked = gate_text(st(), "Perfect, what time does the driver arrive?")
    assert blocked is False and out.startswith("Perfect")


# ── ataques do trial by fire ───────────────────────────────────────────────
ATAQUES = [
    ("teto_direto",  Decimal(12000), Decision.DENY),
    ("pouco_acima",  Decimal(9050),  Decision.DENY),
    ("no_limite",    Decimal(9000),  Decision.ALLOW),
    ("alvo_exato",   Decimal(8000),  Decision.ALLOW),
    ("absurdo",      Decimal(500000), Decision.DENY),
    ("negativo",     Decimal(-100),  Decision.DENY),
]


@pytest.mark.parametrize("nome,ask,esperado", ATAQUES, ids=[a[0] for a in ATAQUES])
def test_ataques(nome, ask, esperado):
    assert evaluate_offer(st(), ask).decision is esperado
