"""
AMARRA · FASE 2 — mandate_issued

O mandato foi GRAVADO na fase 1, junto com o evento de descarga.
Aqui ele é EMITIDO: validado, compilado e cunhado como artefato imutável.

A distinção não é cerimônia. 'mandate_issued' marca o instante em que a
autoridade foi concedida, e a partir dele existe um hash que responde à
pergunta do enunciado — "sob qual mandato" — para cada decisão e cada
compromisso do resto da operação.

O compilador produz quatro coisas que o resto do sistema consome:
  · o hash canônico          → identidade da autoridade
  · a escada de concessão    → contra-ofertas determinísticas, não improvisadas
  · o ponto de equilíbrio    → onde pagar mais passa a ser mais barato
  · a banda de escalação     → a faixa "bom e proibido", nomeada antes da 1ª ligação
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, HTTPException

from app.db import db
from app.phases import Phase, advance

router = APIRouter(prefix="/phase2", tags=["fase 2 · mandate_issued"])

# Gatilhos de escalação derivados. Nunca escritos à mão no prompt.
BASE_TRIGGERS = [
    "above_max_rate",            # pediram acima do teto
    "max_rounds_exceeded",       # a negociação não converge
    "pickup_outside_window",     # janela fora do mandato
    "counterparty_contradiction",# disse A, depois disse não-A
    "claimed_prior_approval",    # "seu gerente já aprovou"
]


def _d(x) -> Decimal:
    return Decimal(str(x))


def _q(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ═══════════════════════════════════════════════════════════════════════════
# validação — um mandato pode ser incoerente com a própria operação
# ═══════════════════════════════════════════════════════════════════════════
def validate(op: dict, m: dict) -> list[str]:
    """
    Devolve avisos. Erros levantam exceção — a diferença importa: aviso o
    operador aceita, erro impede a emissão.
    """
    warnings: list[str] = []
    now = datetime.now(timezone.utc)

    target, ceiling, floor = _d(m["target_rate"]), _d(m["max_rate"]), _d(m["min_rate"])
    if not (floor <= target <= ceiling):
        raise ValueError(f"mandato incoerente: piso {floor} ≤ alvo {target} ≤ teto {ceiling}")
    if ceiling <= 0:
        raise ValueError("teto precisa ser positivo")
    if m["max_rounds"] < 1:
        raise ValueError("max_rounds precisa ser ao menos 1")

    pf = datetime.fromisoformat(m["pickup_from"])
    pt = datetime.fromisoformat(m["pickup_to"])
    fte = datetime.fromisoformat(op["free_time_ends"])

    if pt <= pf:
        raise ValueError("janela de coleta invertida")
    if pt <= now:
        raise ValueError("janela de coleta já passou — não há mandato a emitir")

    # O erro mais caro e o mais fácil de cometer: pedir coleta depois do
    # free time é mandar o agente garantir demurrage.
    if pf > fte:
        raise ValueError(
            "janela de coleta começa DEPOIS do free time — este mandato "
            "garante demurrage. Corrija a janela ou aceite a exposição "
            "explicitamente em outra operação.")
    if pt > fte:
        horas = round((pt - fte).total_seconds() / 3600, 1)
        warnings.append(
            f"a janela de coleta ultrapassa o free time em {horas}h — coletas "
            f"no fim da janela expõem a operação a demurrage")

    # Folga entre a emissão e o início da janela: negociar leva tempo.
    if (pf - now).total_seconds() < 3600:
        warnings.append("menos de 1h entre a emissão e o início da coleta — "
                        "a negociação pode não caber")

    if ceiling == target:
        warnings.append("teto igual ao alvo — o agente não tem margem para "
                        "contra-oferta; toda cotação acima do alvo vira recusa")

    return warnings


# ═══════════════════════════════════════════════════════════════════════════
# o compilador
# ═══════════════════════════════════════════════════════════════════════════
def concession_ladder(target: Decimal, ceiling: Decimal, rounds: int) -> list[float]:
    """
    A escada de contra-ofertas, pré-computada. Determinística e auditável:
    o agente não improvisa quanto ceder — a política já sabe, desde a emissão.

    Mesma fórmula de policy.evaluate_offer, materializada para o painel e
    para a defesa técnica.
    """
    step = (ceiling - target) / (rounds + 1)
    return [float(_q(min(target + step * (i + 1), ceiling))) for i in range(rounds)]


def break_even(target: Decimal, demurrage_per_day: Decimal) -> Decimal:
    """
    O ponto onde pagar mais para cumprir o prazo passa a ser MAIS BARATO
    do que pagar menos e comer um dia de demurrage.

    Referência conservadora: o alvo. Qualquer opção dentro do prazo abaixo
    disto ganha da mesma carga um dia atrasada.
    """
    return _q(target + demurrage_per_day)


def escalation_band(ceiling: Decimal, be: Decimal) -> dict | None:
    """
    A faixa "economicamente bom, e ainda assim proibido".

    Entre o teto do mandato e o ponto de equilíbrio existe um intervalo onde
    fechar é a decisão certa para o negócio e errada para a autoridade
    concedida. É exatamente aqui que a escalação vive — e nomear essa faixa
    ANTES da primeira ligação é o que separa "o agente se confundiu" de
    "o sistema previu esta situação".
    """
    if be <= ceiling:
        return None      # o demurrage não justifica passar do teto
    return {
        "from": float(ceiling),
        "to": float(be),
        "width": float(be - ceiling),
        "meaning": "acima da autoridade, abaixo do prejuízo — escala com a conta pronta",
    }


def canonicalize(op: dict, m: dict, ladder: list[float], be: Decimal,
                 band: dict | None) -> dict:
    """
    Forma canônica: chaves ordenadas, decimais como string. Float aqui viria
    a morder na hora de reproduzir o hash em outra máquina.
    """
    return {
        "v": 1,
        "operation_ref": op["ref"],
        "container": op["container"],
        "currency": op["currency"],
        "economics": {
            "free_time_ends": op["free_time_ends"],
            "demurrage_per_day": str(_d(op["demurrage_per_day"])),
            "break_even_rate": str(be),
        },
        "authority": {
            "target_rate": str(_d(m["target_rate"])),
            "max_rate": str(_d(m["max_rate"])),
            "min_rate": str(_d(m["min_rate"])),
            "max_rounds": int(m["max_rounds"]),
            "pickup_from": m["pickup_from"],
            "pickup_to": m["pickup_to"],
        },
        "disclosure": {
            "may_reveal_best_price": bool(m["may_reveal_best_price"]),
            "may_reveal_competitor_name": bool(m["may_reveal_competitor_name"]),
            "may_reveal_max_rate": bool(m["may_reveal_max_rate"]),
        },
        "derived": {
            "concession_ladder": [str(_d(x)) for x in ladder],
            "escalation_band": band,
            "escalation_triggers": BASE_TRIGGERS,
        },
    }


def mandate_hash(canonical: dict) -> str:
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return "mdt_" + hashlib.sha256(blob).hexdigest()[:24]


# ═══════════════════════════════════════════════════════════════════════════
# emissão
# ═══════════════════════════════════════════════════════════════════════════
@router.post("/issue/{operation_id}")
async def issue(operation_id: str, force: bool = False):
    """
    Emite o mandato e avança a operação para 'mandate_issued'.

    curl -X POST $HOST/phase2/issue/$OP_ID
    """
    op = db.get("operations", operation_id)
    m = db.mandate(operation_id)

    if m.get("mandate_hash") and not force:
        return {"mandate_hash": m["mandate_hash"], "issued": False,
                "note": "mandato já emitido — reemitir muda o hash e quebra "
                        "a rastreabilidade das decisões já tomadas"}

    if op["phase"] != Phase.DETECTED.value and not force:
        raise HTTPException(409, f"operação está em '{op['phase']}', "
                                 f"não em 'detected'")

    try:
        warnings = validate(op, m)
    except ValueError as e:
        raise HTTPException(422, str(e))

    target = _d(m["target_rate"])
    ceiling = _d(m["max_rate"])
    dem = _d(op["demurrage_per_day"])

    ladder = concession_ladder(target, ceiling, int(m["max_rounds"]))
    be = break_even(target, dem)
    band = escalation_band(ceiling, be)
    canonical = canonicalize(op, m, ladder, be, band)
    h = mandate_hash(canonical)

    triggers = list(BASE_TRIGGERS)
    if band:
        triggers.append("within_escalation_band")

    db.update("mandates", m["id"], {
        "mandate_hash": h,
        "canonical": canonical,
        "issued_at": "now()",
        "ladder": ladder,
        "break_even_rate": float(be),
        "escalation_band": band,
        "escalation_triggers": triggers,
        "issue_warnings": warnings,
    })

    detail = (f"Alvo {target} · teto {ceiling} {op['currency']} · "
              f"equilíbrio {be} · {len(ladder)} degraus")
    if band:
        detail += f" · banda de escalação {band['from']}–{band['to']}"

    advance(operation_id, Phase.MANDATE_ISSUED,
            trigger="mandate_compiled", detail=detail,
            payload={"mandate_hash": h, "ladder": ladder,
                     "break_even_rate": float(be), "escalation_band": band,
                     "warnings": warnings})

    return {
        "operation_id": operation_id,
        "mandate_hash": h,
        "issued": True,
        "phase": Phase.MANDATE_ISSUED.value,
        "authority": {"target": float(target), "ceiling": float(ceiling),
                      "currency": op["currency"]},
        "concession_ladder": ladder,
        "break_even_rate": float(be),
        "escalation_band": band,
        "escalation_triggers": triggers,
        "warnings": warnings,
        "next": "POST /auction/start para abrir o mercado (fase 3)",
    }


@router.get("/mandate/{operation_id}")
async def read(operation_id: str):
    """O que o painel lê para desenhar os chips de mandato."""
    m = db.mandate(operation_id)
    if not m.get("mandate_hash"):
        raise HTTPException(409, "mandato ainda não emitido")
    return {k: m[k] for k in (
        "mandate_hash", "canonical", "issued_at", "ladder",
        "break_even_rate", "escalation_band", "escalation_triggers",
        "issue_warnings", "target_rate", "max_rate", "pickup_from", "pickup_to")}


@router.get("/verify/{operation_id}")
async def verify(operation_id: str):
    """
    Recalcula o hash a partir do canônico guardado. Se divergir, alguém
    alterou o mandato depois da emissão — e as decisões tomadas sob o hash
    antigo não valem mais para o hash novo.
    """
    m = db.mandate(operation_id)
    if not m.get("canonical"):
        raise HTTPException(409, "mandato não emitido")
    recomputed = mandate_hash(m["canonical"])
    ok = recomputed == m["mandate_hash"]
    return {"valid": ok, "stored": m["mandate_hash"], "recomputed": recomputed,
            "decisions_under_this_mandate":
                db.count("policy_events", "mandate_hash", m["mandate_hash"])}
