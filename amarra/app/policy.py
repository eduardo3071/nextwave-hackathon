"""
AMARRA · Policy Engine.

O componente mais importante do projeto e o mais fácil de escrever:
função PURA, sem LLM, sem I/O, sem rede. Roda em microssegundos e é 100%
testável — é isso que permite mostrar um pytest verde no palco e dizer
"violações de mandato = 0 por construção", que é uma prova, não uma promessa.

REGRA DE OURO: o modelo nunca inventa um número. Ele chama a ferramenta,
esta função decide, e devolve a FRASE EXATA que pode ser falada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class Decision(str, Enum):
    ALLOW = "allow"        # pode falar o valor
    DENY = "deny"          # recusa educada, valor nenhum autorizado
    ESCALATE = "escalate"  # excede a autoridade — chama humano


@dataclass(frozen=True)
class Mandate:
    target_rate: Decimal
    max_rate: Decimal
    min_rate: Decimal = Decimal(0)
    max_rounds: int = 4
    currency: str = "MXN"
    may_reveal_best_price: bool = True
    may_reveal_competitor_name: bool = False
    may_reveal_max_rate: bool = False

    def __post_init__(self) -> None:
        assert self.max_rate >= self.target_rate >= self.min_rate, "mandato incoerente"


@dataclass
class NegotiationState:
    mandate: Mandate
    rounds: int = 0
    offers_made: list[Decimal] = field(default_factory=list)
    counterparty_asks: list[Decimal] = field(default_factory=list)
    # whitelist para o gate final do TTS: só estas frases podem virar áudio
    approved_utterances: set[str] = field(default_factory=set)
    # melhor preço vivo no leilão, injetado pelo orquestrador
    market_best: Decimal | None = None


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    amount: Decimal | None
    reason: str
    utterance: str | None   # o texto EXATO autorizado. None = nada a falar.


def _money(d: Decimal, currency: str) -> str:
    unit = {"MXN": "pesos", "BRL": "reais", "USD": "dólares"}.get(currency, currency)
    return f"{d.quantize(Decimal('1')):,.0f} {unit}".replace(",", ".")


def evaluate_offer(state: NegotiationState, ask: Decimal) -> PolicyResult:
    """
    Recebe o que a contraparte pediu. Devolve o que pode ser feito e dito.

    Invariante testada: NUNCA retorna ALLOW com amount > mandate.max_rate.
    """
    m = state.mandate
    cur = m.currency

    if ask <= 0:
        return PolicyResult(Decision.DENY, None, "invalid_ask",
                            "No entendí el monto. ¿Me lo repites, por favor?")

    # Rodadas esgotadas: parar de negociar é decisão de política, não do modelo.
    if state.rounds >= m.max_rounds:
        return PolicyResult(Decision.ESCALATE, None, "max_rounds_exceeded", None)

    # 1) Bateu o alvo → fecha na hora. Não há upside em continuar negociando.
    if ask <= m.target_rate:
        return PolicyResult(
            Decision.ALLOW, ask, "at_or_below_target",
            f"Cerrado en {_money(ask, cur)}. Te mando la confirmación ahora.",
        )

    # 2) Acima do alvo mas dentro do teto → contra-oferta em escada,
    #    com alavanca de mercado se o mandato permitir revelar.
    if ask <= m.max_rate:
        step = (m.max_rate - m.target_rate) / (m.max_rounds + 1)
        counter = min(m.target_rate + step * (state.rounds + 1), m.max_rate)

        # ← INVARIANTE. Fail-closed: prefere quebrar a estourar o teto.
        assert counter <= m.max_rate, "INVARIANTE VIOLADA: contra-oferta acima do teto"

        if state.market_best is not None and state.market_best < ask and m.may_reveal_best_price:
            frase = (f"Tengo una propuesta mejor en esta ruta. "
                     f"¿Puedes acercarte a {_money(counter, cur)}?")
        else:
            frase = f"Puedo llegar a {_money(counter, cur)}. ¿Cerramos así?"

        return PolicyResult(Decision.ALLOW, counter, "counter_within_mandate", frase)

    # 3) Acima do teto → a ÚNICA saída é recusar. O modelo não tem escolha aqui.
    #    Nunca revela o teto: isso faria toda contraparte cotar exatamente nele.
    return PolicyResult(
        Decision.DENY, None, "above_max_rate",
        "Está por encima de lo que puedo autorizar en esta ruta. "
        "Gracias, pero así no puedo cerrar.",
    )


def evaluate_pickup(state: NegotiationState, offered_iso: str,
                    window_from: str, window_to: str) -> PolicyResult:
    """Janela de coleta é parte do mandato tanto quanto o preço."""
    if window_from <= offered_iso <= window_to:
        return PolicyResult(Decision.ALLOW, None, "pickup_within_window",
                            "Perfecto, esa ventana nos sirve.")
    # Fora da janela é decisão econômica (demurrage) → humano.
    return PolicyResult(Decision.ESCALATE, None, "pickup_outside_window", None)


# ── o gate final: nada com número passa sem estar na whitelist ──────────────
import re  # noqa: E402

MONEY_RE = re.compile(
    r"(\$\s?\d[\d\.,]*)|(\b\d{3,}[\d\.,]*\s*(pesos|reais|d[óo]lares|mxn|brl|usd)\b)"
    r"|(\b(mil|dos mil|tres mil|cuatro mil|cinco mil|seis mil|siete mil|ocho mil|nueve mil)\b)",
    re.IGNORECASE,
)

SAFE_FALLBACK = "Déjame confirmar ese número contigo antes de seguir."


def gate_text(state: NegotiationState, text: str) -> tuple[str, bool]:
    """
    Última barreira antes do áudio. Se o texto contém valor e não veio de uma
    frase aprovada pela política, substitui por uma frase segura.

    Devolve (texto_a_falar, foi_bloqueado).
    """
    if not MONEY_RE.search(text):
        return text, False
    norm = " ".join(text.split()).lower()
    for approved in state.approved_utterances:
        a = " ".join(approved.split()).lower()
        if norm in a or a in norm:
            return text, False
    return SAFE_FALLBACK, True
