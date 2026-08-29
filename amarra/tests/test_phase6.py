import pytest

from app.phase6_committed import (
    build_read_back,
    classify_response,
    missing_material,
    read_back_token,
)


SIM = ["sí", "si, correcto", "exacto", "confirmado", "va", "sim", "isso mesmo",
       "fechado", "perfeito, confirmo"]
NAO = ["no", "no, espera", "sí pero cambia la hora", "sim, mas muda a hora",
       "está mal", "corrige eso"]
TALVEZ = ["", "aham", "creo que sí", "acho que sim", "mais ou menos",
          "hmm", "quizás", "...", "ok?"]


@pytest.mark.parametrize("t", SIM)
def test_sim_explicito(t):
    assert classify_response(t) == "confirmed"


@pytest.mark.parametrize("t", NAO)
def test_negacao_vence_afirmacao(t):
    """'sim, mas muda a hora' é rejeição. Nunca compromisso."""
    assert classify_response(t) == "rejected"


@pytest.mark.parametrize("t", TALVEZ)
def test_ambiguo_nunca_compromete(t):
    assert classify_response(t) == "ambiguous"


def test_token_muda_quando_o_valor_muda(slots):
    t1 = read_back_token(slots)
    slots["rate"]["value"] = "8500"
    assert read_back_token(slots) != t1


def test_token_e_estavel_na_ordem(slots):
    assert read_back_token(slots) == read_back_token(dict(reversed(list(slots.items()))))


def test_falta_termo_material(slots):
    del slots["pickup_at"]
    assert missing_material(slots) == ["pickup_at"]


def test_frase_traz_os_valores_registrados(slots):
    f = build_read_back(slots, currency="MXN", lang="es-MX")
    assert "8.400" in f and "jueves" in f and "sí explícito" in f
