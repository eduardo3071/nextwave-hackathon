"""
AMARRA · FASE 1 — detected

O contêiner desceu do navio. É aqui que tudo começa e é aqui que o relógio
que custa dinheiro passa a correr.

Esta fase é a ponte com a Nauta: os 20 agentes deles DETECTAM (Nina vê o
atraso, Marcus vê a ruptura, Theo vê a cobrança estranha) e nenhum deles
liga. O Amarra é acionado exatamente neste ponto — recebe o evento de
descarga e vira o canal de execução que falta na stack.

Três responsabilidades, e nada além disso:
  1. receber o evento de descarga e validá-lo
  2. materializar a operação e o mandato, de forma idempotente
  3. ligar o relógio e mantê-lo vivo
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db import db
from app.phases import Phase

router = APIRouter(prefix="/phase1", tags=["fase 1 · detected"])

# Limiares do relógio. O painel troca de cor quando o backend troca o estado.
WARNING_AT = timedelta(hours=6)
CRITICAL_AT = timedelta(hours=2)
TICK_SECONDS = 20          # de quanto em quanto o relógio é reavaliado


# ═══════════════════════════════════════════════════════════════════════════
# entrada
# ═══════════════════════════════════════════════════════════════════════════
class MandateIn(BaseModel):
    """O mandato chega junto com a descarga, mas só é EMITIDO na fase 2."""
    target_rate: Decimal
    max_rate: Decimal
    min_rate: Decimal = Decimal(0)
    max_rounds: int = 4
    pickup_from: datetime
    pickup_to: datetime
    may_reveal_best_price: bool = True
    may_reveal_competitor_name: bool = False
    may_reveal_max_rate: bool = False

    @field_validator("max_rate")
    @classmethod
    def teto_acima_do_alvo(cls, v, info):
        alvo = info.data.get("target_rate")
        if alvo is not None and v < alvo:
            raise ValueError("teto abaixo do alvo — mandato incoerente")
        return v


class DischargeEvent(BaseModel):
    """
    O evento que a Nauta (ou o TMS, ou o portal do armador) emite quando o
    contêiner é descarregado. Tudo que o Amarra precisa para existir.
    """
    ref: str = Field(..., min_length=3, description="MZO-GDL-4471")
    container: str
    origin: str
    destination: str
    cargo_value_usd: Decimal | None = None
    currency: str = "MXN"

    # o relógio pode vir pronto OU como dias livres a partir da descarga
    discharged_at: datetime
    free_time_ends: datetime | None = None
    free_days: int | None = None
    demurrage_per_day: Decimal

    mandate: MandateIn
    source: dict = Field(default_factory=dict)   # payload cru de quem detectou

    @field_validator("free_time_ends")
    @classmethod
    def relogio_no_futuro(cls, v):
        if v and v <= datetime.now(timezone.utc):
            raise ValueError("free time já expirou — não há operação a abrir")
        return v

    def deadline(self) -> datetime:
        if self.free_time_ends:
            return self.free_time_ends
        if self.free_days is None:
            raise ValueError("informe free_time_ends ou free_days")
        return self.discharged_at + timedelta(days=self.free_days)

    def idempotency_key(self) -> str:
        """
        Mesmo contêiner, mesma descarga = mesma operação.
        Portais de armador reenviam evento; sem isto você abre a operação
        duas vezes e dispara dois leilões para o mesmo contêiner.
        """
        raw = f"{self.container}|{self.discharged_at.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ═══════════════════════════════════════════════════════════════════════════
# o relógio
# ═══════════════════════════════════════════════════════════════════════════
def clock_state(free_time_ends: datetime, *, stopped: bool = False) -> str:
    if stopped:
        return "stopped"
    left = free_time_ends - datetime.now(timezone.utc)
    if left <= timedelta(0):
        return "expired"
    if left <= CRITICAL_AT:
        return "critical"
    if left <= WARNING_AT:
        return "warning"
    return "safe"


def exposure(free_time_ends: datetime, per_day: Decimal) -> dict:
    """
    Quanto custa perder o prazo. É este número que transforma o agente de
    'agendador de caminhão' em 'sistema que defende margem' — e é ele que
    torna a conta da escalação possível lá na frente.
    """
    left = free_time_ends - datetime.now(timezone.utc)
    secs = max(0, int(left.total_seconds()))
    dias_perdidos = 0 if secs > 0 else 1
    return {
        "seconds_remaining": secs,
        "hours_remaining": round(secs / 3600, 2),
        "state": clock_state(free_time_ends),
        "cost_per_day": float(per_day),
        "exposure_if_missed": float(per_day * (dias_perdidos or 1)),
    }


# ═══════════════════════════════════════════════════════════════════════════
# a fase
# ═══════════════════════════════════════════════════════════════════════════
def _seed_phase_event(operation_id: str, ev: DischargeEvent, deadline: datetime) -> None:
    """
    A fase 1 é a ORIGEM, não uma transição — por isso escreve direto, com
    previous = null. Chamar advance() aqui devolveria False, porque a
    operação já nasce em 'detected'.
    """
    horas = round((deadline - datetime.now(timezone.utc)).total_seconds() / 3600, 1)
    db.insert("phase_events", {
        "operation_id": operation_id,
        "phase": Phase.DETECTED.value,
        "previous": None,
        "kind": "spine",
        "trigger": "container_discharged",
        "detail": f"Contêiner {ev.container} descarregado. "
                  f"{horas}h de free time · {ev.demurrage_per_day} {ev.currency}/dia depois",
        "payload": {
            "container": ev.container,
            "discharged_at": ev.discharged_at.isoformat(),
            "free_time_ends": deadline.isoformat(),
            "demurrage_per_day": float(ev.demurrage_per_day),
            "hours_of_free_time": horas,
            "source": ev.source,
        },
        "ms_in_previous": None,
    })


@router.post("/detect")
async def detect(ev: DischargeEvent):
    """
    Ponto de entrada do sistema inteiro.

    curl -X POST $HOST/phase1/detect -H 'content-type: application/json' -d @discharge.json
    """
    key = ev.idempotency_key()

    # ── idempotência ───────────────────────────────────────────────────────
    existing = db.find("operations", "idempotency_key", key)
    if existing:
        return {
            "operation_id": existing["id"],
            "ref": existing["ref"],
            "phase": existing["phase"],
            "created": False,
            "note": "evento já processado — operação existente devolvida",
            "clock": exposure(datetime.fromisoformat(existing["free_time_ends"]),
                              Decimal(str(existing["demurrage_per_day"]))),
        }

    if db.find("operations", "ref", ev.ref):
        raise HTTPException(409, f"já existe operação com ref {ev.ref}")

    try:
        deadline = ev.deadline()
    except ValueError as e:
        raise HTTPException(422, str(e))

    if deadline <= datetime.now(timezone.utc):
        raise HTTPException(422, "free time já expirou — não há prazo a defender")

    # ── materializa a operação ─────────────────────────────────────────────
    op = db.insert("operations", {
        "ref": ev.ref,
        "container": ev.container,
        "origin": ev.origin,
        "destination": ev.destination,
        "cargo_value_usd": float(ev.cargo_value_usd) if ev.cargo_value_usd else None,
        "free_time_ends": deadline.isoformat(),
        "demurrage_per_day": float(ev.demurrage_per_day),
        "currency": ev.currency,
        "status": "open",
        "phase": Phase.DETECTED.value,     # nasce aqui
        "clock_state": clock_state(deadline),
        "idempotency_key": key,
        "source_event": ev.source,
    })

    # O mandato é GRAVADO agora mas só é EMITIDO na fase 2. A distinção é de
    # propósito: 'mandate_issued' marca o instante em que a autoridade foi
    # concedida, e é isso que se aponta no palco.
    db.insert("mandates", {
        "operation_id": op["id"],
        "target_rate": float(ev.mandate.target_rate),
        "max_rate": float(ev.mandate.max_rate),
        "min_rate": float(ev.mandate.min_rate),
        "max_rounds": ev.mandate.max_rounds,
        "pickup_from": ev.mandate.pickup_from.isoformat(),
        "pickup_to": ev.mandate.pickup_to.isoformat(),
        "may_reveal_best_price": ev.mandate.may_reveal_best_price,
        "may_reveal_competitor_name": ev.mandate.may_reveal_competitor_name,
        "may_reveal_max_rate": ev.mandate.may_reveal_max_rate,
    })

    _seed_phase_event(op["id"], ev, deadline)
    start_clock(op["id"])

    return {
        "operation_id": op["id"],
        "ref": op["ref"],
        "phase": Phase.DETECTED.value,
        "created": True,
        "clock": exposure(deadline, ev.demurrage_per_day),
        "next": "POST /auction/start para abrir o mercado (fases 2 e 3)",
    }


@router.get("/clock/{operation_id}")
async def clock(operation_id: str):
    op = db.get("operations", operation_id)
    return exposure(datetime.fromisoformat(op["free_time_ends"]),
                    Decimal(str(op["demurrage_per_day"])))


# ═══════════════════════════════════════════════════════════════════════════
# o relógio vivo
# ═══════════════════════════════════════════════════════════════════════════
_TICKERS: dict[str, asyncio.Task] = {}


async def _tick(operation_id: str) -> None:
    """
    Reavalia o estado do relógio e só escreve quando ele MUDA.
    Escrever a cada tick inundaria o Realtime e faria o painel piscar.
    """
    while True:
        try:
            op = db.get("operations", operation_id)
        except Exception:
            return

        parado = op["phase"] in ("closed", "failed")
        novo = clock_state(datetime.fromisoformat(op["free_time_ends"]), stopped=parado)

        if novo != op["clock_state"]:
            db.update("operations", operation_id,
                      {"clock_state": novo, "clock_state_since": "now()"})
            print(f"[clock] {op['ref']}: {op['clock_state']} → {novo}")

        if novo in ("stopped", "expired") and parado:
            _TICKERS.pop(operation_id, None)
            return

        await asyncio.sleep(TICK_SECONDS)


def start_clock(operation_id: str) -> None:
    if operation_id in _TICKERS:
        return
    _TICKERS[operation_id] = asyncio.create_task(_tick(operation_id))


def stop_clock(operation_id: str) -> None:
    """Chamado na fase 8. O cronômetro congela com a folga que sobrou."""
    t = _TICKERS.pop(operation_id, None)
    if t:
        t.cancel()
    db.update("operations", operation_id,
              {"clock_state": "stopped", "clock_state_since": "now()"})
