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
        assert self.max_rate >= self.target_rate >= self.min_rate, "incoherent mandate"


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


# ── policy phrases (English only) ─────────────────────────────────────────
UNITS = {"MXN": "pesos", "BRL": "reais", "USD": "dollars"}


def _money(d: Decimal, currency: str) -> str:
    unit = UNITS.get(currency, currency)
    return f"{d.quantize(Decimal('1')):,.0f} {unit}".replace(",", ".")


PHRASES: dict[str, object] = {
    "invalid_ask":
        "I didn't catch the amount. Could you repeat it, please?",
    "closed":
        lambda m: f"Closed at {m}. I'll send you the confirmation now.",
    "counter_market":
        lambda m: (f"I have a better offer on this lane. "
                   f"Can you come down to {m}?"),
    "counter_plain":
        lambda m: f"I can go up to {m}. Shall we close on that?",
    "above_max":
        "That's above what I can authorize on this lane. "
        "Thanks, but I can't close on that.",
    "pickup_ok":
        "Perfect, that window works for us.",
    "safe_fallback":
        "Let me confirm that number with you before continuing.",
}


def evaluate_offer(state: NegotiationState, ask: Decimal) -> PolicyResult:
    """
    Receives what the counterparty asked. Returns what can be done and said.

    Tested invariant: NEVER returns ALLOW with amount > mandate.max_rate.
    """
    m = state.mandate
    cur = m.currency

    if ask <= 0:
        return PolicyResult(Decision.DENY, None, "invalid_ask", PHRASES["invalid_ask"])

    # Rounds exhausted: stopping the negotiation is a policy decision.
    if state.rounds >= m.max_rounds:
        return PolicyResult(Decision.ESCALATE, None, "max_rounds_exceeded", None)

    # 1) Hit the target → close immediately. No upside in continuing.
    if ask <= m.target_rate:
        return PolicyResult(
            Decision.ALLOW, ask, "at_or_below_target",
            PHRASES["closed"](_money(ask, cur)),
        )

    # 2) Above target but within ceiling → laddered counter-offer,
    #    with market leverage if the mandate allows revealing it.
    if ask <= m.max_rate:
        step = (m.max_rate - m.target_rate) / (m.max_rounds + 1)
        counter = min(m.target_rate + step * (state.rounds + 1), m.max_rate)

        # ← INVARIANT. Fail-closed: prefer breaking to blowing the ceiling.
        assert counter <= m.max_rate, "INVARIANT VIOLATED: counter above ceiling"

        money = _money(counter, cur)
        if state.market_best is not None and state.market_best < ask and m.may_reveal_best_price:
            phrase = PHRASES["counter_market"](money)
        else:
            phrase = PHRASES["counter_plain"](money)

        return PolicyResult(Decision.ALLOW, counter, "counter_within_mandate", phrase)

    # 3) Above ceiling → the ONLY exit is refusal. Never reveal the ceiling.
    return PolicyResult(Decision.DENY, None, "above_max_rate", PHRASES["above_max"])


def evaluate_pickup(state: NegotiationState, offered_iso: str,
                    window_from: str, window_to: str) -> PolicyResult:
    """Pickup window is part of the mandate, just like price."""
    if window_from <= offered_iso <= window_to:
        return PolicyResult(Decision.ALLOW, None, "pickup_within_window",
                            PHRASES["pickup_ok"])
    # Outside window is an economic decision (demurrage) → human.
    return PolicyResult(Decision.ESCALATE, None, "pickup_outside_window", None)


# ── final gate: nothing with a number passes without being whitelisted ─────
import re  # noqa: E402

MONEY_RE = re.compile(
    r"(\$\s?\d[\d\.,]*)|(\b\d{3,}[\d\.,]*\s*(pesos|reais|dollars|mxn|brl|usd)\b)"
    r"|(\b(one thousand|two thousand|three thousand|four thousand|five thousand|"
    r"six thousand|seven thousand|eight thousand|nine thousand|ten thousand)\b)",
    re.IGNORECASE,
)

SAFE_FALLBACK = "Let me confirm that number with you before continuing."


def gate_text(state: NegotiationState, text: str) -> tuple[str, bool]:
    """
    Last barrier before audio. If text contains a value not from an
    approved phrase, substitute with a safe fallback.

    Returns (text_to_say, was_blocked).
    """
    if not MONEY_RE.search(text):
        return text, False
    norm = " ".join(text.split()).lower()
    for approved in state.approved_utterances:
        a = " ".join(approved.split()).lower()
        if norm in a or a in norm:
            return text, False
    return SAFE_FALLBACK, True
