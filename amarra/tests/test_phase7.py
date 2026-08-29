from app.phase7_verified import anchor, norm, number_variants, spell_number


W = [  # índice de palavras simulado, tempos em segundos
    {"word": "ocho",         "start": 14.8, "end": 15.1, "confidence": 0.97},
    {"word": "mil",          "start": 15.1, "end": 15.3, "confidence": 0.98},
    {"word": "cuatrocientos","start": 15.3, "end": 16.1, "confidence": 0.94},
    {"word": "jueves",       "start": 16.2, "end": 16.6, "confidence": 0.96},
    {"word": "diez",         "start": 16.6, "end": 17.0, "confidence": 0.91},
    {"word": "sí",           "start": 18.4, "end": 18.6, "confidence": 0.99},
    {"word": "correcto",     "start": 18.6, "end": 19.2, "confidence": 0.97},
]


def test_ancora_exata():
    a = anchor(W, "ocho mil cuatrocientos")
    assert a["t_start_ms"] == 14800 and a["t_end_ms"] == 16100
    assert a["method"] == "exact" and a["confidence"] >= 0.94


def test_numero_escrito_encontra_numero_falado():
    """A contraparte falou por extenso; o registro guardou 8400."""
    a = anchor(W, "8400")
    assert a is not None and a["t_start_ms"] == 14800


def test_soletrar():
    assert spell_number(8400, "es") == "ocho mil cuatrocientos"
    assert spell_number(9200, "pt") == "nove mil duzentos"
    assert spell_number(1500, "es") == "mil quinientos"


def test_fuzzy_tolera_palavra_a_mais():
    assert anchor(W, "ocho mil cuatrocientos pesos")["method"] in ("fuzzy", "exact")


def test_citacao_inventada_nao_ancora():
    """A regra da fase: sem âncora, não verifica."""
    assert anchor(W, "doce mil quinientos") is None
    assert anchor(W, "chofer Juan Pérez") is None


def test_ancora_da_afirmacao():
    a = anchor(W, "sí correcto")
    assert a["t_start_ms"] == 18400


def test_variantes_numericas():
    v = number_variants("cerrado en 8.400 pesos", "es")
    assert any("ocho mil cuatrocientos" in x for x in v)
