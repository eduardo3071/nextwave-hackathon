"""
AMARRA · a máquina de fases.

Este é o eixo que faltava: um único fio do início ao fim, que o painel
desenha e o júri acompanha sem precisar que ninguém narre.

DESENHO
───────
Uma ESPINHA linear de 8 passos, e 4 DESVIOS que a interrompem e devolvem:

    detected → mandate_issued → market_open → negotiating
             → reserved → committed → verified → closed
                   ▲                        │
                   └──── resolved ◄── escalated ◄── renegotiating ◄── disrupted

Por que isso não é enfeite: cada transição tem uma GUARDA. `committed` exige
que o lock do leilão tenha sido tomado. `verified` exige pelo menos um
compromisso ancorado no áudio. Ou seja, as fases codificam as invariantes do
produto — não dá para o painel mostrar "verificado" se não houver evidência.

Isso vale ponto na defesa técnica: a barra de progresso É a asserção.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.db import db


class Phase(str, Enum):
    DETECTED = "detected"
    MANDATE_ISSUED = "mandate_issued"
    MARKET_OPEN = "market_open"
    NEGOTIATING = "negotiating"
    RESERVED = "reserved"
    COMMITTED = "committed"
    VERIFIED = "verified"
    CLOSED = "closed"
    # desvios
    DISRUPTED = "disrupted"
    RENEGOTIATING = "renegotiating"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    # terminal ruim
    FAILED = "failed"


SPINE: list[Phase] = [
    Phase.DETECTED, Phase.MANDATE_ISSUED, Phase.MARKET_OPEN, Phase.NEGOTIATING,
    Phase.RESERVED, Phase.COMMITTED, Phase.VERIFIED, Phase.CLOSED,
]
BRANCH = {Phase.DISRUPTED, Phase.RENEGOTIATING, Phase.ESCALATED, Phase.RESOLVED}
TERMINAL = {Phase.CLOSED, Phase.FAILED}


@dataclass(frozen=True)
class PhaseSpec:
    key: Phase
    label_pt: str
    label_es: str
    caption: str          # uma linha, é o que o painel mostra sob o passo
    kind: str             # spine | branch | terminal


SPEC: dict[Phase, PhaseSpec] = {
    Phase.DETECTED: PhaseSpec(
        Phase.DETECTED, "Detectado", "Detectado",
        "Contêiner descarregado. O relógio do free time começou.", "spine"),
    Phase.MANDATE_ISSUED: PhaseSpec(
        Phase.MANDATE_ISSUED, "Mandato emitido", "Mandato emitido",
        "Alvo, teto e janela de coleta viraram dado — não prompt.", "spine"),
    Phase.MARKET_OPEN: PhaseSpec(
        Phase.MARKET_OPEN, "Mercado aberto", "Mercado abierto",
        "Três transportadoras discando em paralelo.", "spine"),
    Phase.NEGOTIATING: PhaseSpec(
        Phase.NEGOTIATING, "Negociando", "Negociando",
        "Cotações vivas, cruzando entre as chamadas.", "spine"),
    Phase.RESERVED: PhaseSpec(
        Phase.RESERVED, "Reservado", "Reservado",
        "Lock tomado: uma e só uma chamada pode fechar.", "spine"),
    Phase.COMMITTED: PhaseSpec(
        Phase.COMMITTED, "Comprometido", "Comprometido",
        "Acordo dito em voz alta e confirmado com a contraparte.", "spine"),
    Phase.VERIFIED: PhaseSpec(
        Phase.VERIFIED, "Verificado", "Verificado",
        "Cada campo ancorado no áudio. Recap escrito enviado.", "spine"),
    Phase.CLOSED: PhaseSpec(
        Phase.CLOSED, "Encerrado", "Cerrado",
        "Operação fechada dentro do free time.", "terminal"),
    Phase.DISRUPTED: PhaseSpec(
        Phase.DISRUPTED, "Interrompido", "Interrumpido",
        "Chegou um problema pelo telefone. O plano mudou.", "branch"),
    Phase.RENEGOTIATING: PhaseSpec(
        Phase.RENEGOTIATING, "Renegociando", "Renegociando",
        "O agente está ligando de volta para mover o combinado.", "branch"),
    Phase.ESCALATED: PhaseSpec(
        Phase.ESCALATED, "Escalado", "Escalado",
        "A decisão excede o mandato. Humano na linha, com a conta pronta.", "branch"),
    Phase.RESOLVED: PhaseSpec(
        Phase.RESOLVED, "Resolvido", "Resuelto",
        "O humano decidiu. Voltando para a espinha.", "branch"),
    Phase.FAILED: PhaseSpec(
        Phase.FAILED, "Sem saída", "Sin salida",
        "Nenhuma opção dentro do mandato e ninguém resolveu a tempo.", "terminal"),
}


# ── transições permitidas ──────────────────────────────────────────────────
ALLOWED: dict[Phase, set[Phase]] = {
    Phase.DETECTED:      {Phase.MANDATE_ISSUED, Phase.FAILED},
    Phase.MANDATE_ISSUED:{Phase.MARKET_OPEN, Phase.FAILED},
    Phase.MARKET_OPEN:   {Phase.NEGOTIATING, Phase.ESCALATED, Phase.FAILED},
    Phase.NEGOTIATING:   {Phase.RESERVED, Phase.ESCALATED, Phase.FAILED},
    Phase.RESERVED:      {Phase.COMMITTED, Phase.DISRUPTED, Phase.ESCALATED, Phase.FAILED},
    Phase.COMMITTED:     {Phase.VERIFIED, Phase.DISRUPTED, Phase.ESCALATED},
    Phase.VERIFIED:      {Phase.CLOSED, Phase.DISRUPTED},
    # desvios
    Phase.DISRUPTED:     {Phase.RENEGOTIATING, Phase.ESCALATED, Phase.FAILED},
    Phase.RENEGOTIATING: {Phase.RESERVED, Phase.ESCALATED, Phase.FAILED},
    Phase.ESCALATED:     {Phase.RESOLVED, Phase.FAILED},
    Phase.RESOLVED:      {Phase.RESERVED, Phase.COMMITTED, Phase.CLOSED, Phase.FAILED},
    Phase.CLOSED:        set(),
    Phase.FAILED:        set(),
}


class PhaseError(RuntimeError):
    """Transição inválida ou guarda reprovada. Falha alto, não silencioso."""


# ── guardas: é aqui que a fase deixa de ser enfeite ────────────────────────
def _guard(operation_id: str, target: Phase, ctx: dict) -> None:
    if target is Phase.MARKET_OPEN:
        if int(ctx.get("carriers", 0)) < 3:
            raise PhaseError("R7 exige ao menos 3 transportadoras para abrir o mercado")

    if target is Phase.RESERVED:
        if not ctx.get("reserved_by"):
            raise PhaseError("não há lock de reserva — nenhuma chamada pode fechar")

    if target is Phase.COMMITTED:
        if not ctx.get("reserved_by"):
            raise PhaseError("comprometer sem reserva permitiria dois caminhões")
        amount, ceiling = ctx.get("amount"), ctx.get("max_rate")
        if amount is not None and ceiling is not None and float(amount) > float(ceiling):
            raise PhaseError(f"valor {amount} excede o teto {ceiling} — isso é escalação")

    if target is Phase.VERIFIED:
        # A invariante do Pilar 02, agora visível na barra de progresso.
        n = db.count("commitments", "operation_id", operation_id)
        if n == 0:
            raise PhaseError("nada foi ancorado no áudio — não há o que verificar")

    if target is Phase.CLOSED:
        if not ctx.get("recap_sent"):
            raise PhaseError("R3a: encerrar sem recap escrito não fecha o requisito")


# ── a API que o resto do backend usa ───────────────────────────────────────
def advance(operation_id: str, target: Phase, *, trigger: str,
            detail: str | None = None, call_id: str | None = None,
            auction_id: str | None = None, payload: dict | None = None,
            ctx: dict | None = None, force: bool = False) -> bool:
    """
    Move a operação para `target`. Devolve False se já estava lá.

    `trigger` é o EVENTO que causou (ex.: 'lock_acquired'), nunca a narrativa.
    `force=True` só para o driver de ensaio.
    """
    ctx = ctx or {}
    current = Phase(db.get("operations", operation_id)["phase"])

    if current is target:
        return False
    if not force:
        if target not in ALLOWED[current]:
            raise PhaseError(f"transição inválida: {current.value} → {target.value}")
        _guard(operation_id, target, ctx)

    spec = SPEC[target]
    db.rpc("advance_phase", {
        "p_operation_id": operation_id,
        "p_phase": target.value,
        "p_kind": spec.kind,
        "p_trigger": trigger,
        "p_detail": detail or spec.caption,
        "p_call_id": call_id,
        "p_auction_id": auction_id,
        "p_payload": payload or {},
    })
    return True


def current(operation_id: str) -> Phase:
    return Phase(db.get("operations", operation_id)["phase"])


def spine_step(p: Phase) -> int | None:
    return SPINE.index(p) + 1 if p in SPINE else None


def can(operation_id: str, target: Phase) -> bool:
    return target in ALLOWED[current(operation_id)]
