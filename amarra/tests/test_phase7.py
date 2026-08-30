from app.phase7_verified import anchor, norm, number_variants, spell_number


W = [  # simulated word index, times in seconds
    {"word": "eight",       "start": 14.8, "end": 15.1, "confidence": 0.97},
    {"word": "thousand",    "start": 15.1, "end": 15.3, "confidence": 0.98},
    {"word": "four",        "start": 15.3, "end": 15.7, "confidence": 0.94},
    {"word": "hundred",     "start": 15.7, "end": 16.1, "confidence": 0.94},
    {"word": "Thursday",    "start": 16.2, "end": 16.6, "confidence": 0.96},
    {"word": "ten",         "start": 16.6, "end": 17.0, "confidence": 0.91},
    {"word": "yes",         "start": 18.4, "end": 18.6, "confidence": 0.99},
    {"word": "correct",     "start": 18.6, "end": 19.2, "confidence": 0.97},
]


def test_ancora_exata():
    a = anchor(W, "eight thousand four hundred")
    assert a["t_start_ms"] == 14800 and a["t_end_ms"] == 16100
    assert a["method"] == "exact" and a["confidence"] >= 0.94


def test_numero_escrito_encontra_numero_falado():
    """The counterparty spelled it out; the record has 8400."""
    a = anchor(W, "8400")
    assert a is not None and a["t_start_ms"] == 14800


def test_soletrar():
    assert spell_number(8400) == "eight thousand four hundred"
    assert spell_number(9200) == "nine thousand two hundred"
    assert spell_number(1500) == "one thousand five hundred"


def test_fuzzy_tolera_palavra_a_mais():
    assert anchor(W, "eight thousand four hundred pesos")["method"] in ("fuzzy", "exact")


def test_citacao_inventada_nao_ancora():
    """Phase rule: no anchor, no verify."""
    assert anchor(W, "twelve thousand five hundred") is None
    assert anchor(W, "driver John Smith") is None


def test_ancora_da_afirmacao():
    a = anchor(W, "yes correct")
    assert a["t_start_ms"] == 18400


def test_variantes_numericas():
    v = number_variants("closed at 8.400 pesos")
    assert any("eight thousand four hundred" in x for x in v)
