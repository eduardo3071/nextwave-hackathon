# Ligando as fases no que já existe

Seis pontos. Cada um é uma linha, e cada um corresponde a um evento REAL
do sistema — nunca a uma narrativa escrita à mão.

## 1 · `app/main.py` — abrir o mercado

Em `auction_start`, logo depois de criar a linha em `auctions`:

```python
from app.phases import Phase, advance

advance(op["id"], Phase.MANDATE_ISSUED, trigger="mandate_loaded",
        auction_id=auction.id)
advance(op["id"], Phase.MARKET_OPEN, trigger="auction_dispatched",
        auction_id=auction.id, ctx={"carriers": len(carriers)},
        detail=f"{len(carriers)} transportadoras discando")
```

A guarda de `MARKET_OPEN` recusa com menos de três — o R7 vira impossível de
violar por acidente, e não só um item de checklist.

## 2 · `app/agent.py` — primeira fala vira negociação

No fim de `AgentSession.open()`:

```python
from app.phases import Phase, advance
op_id = db.get("calls", self.call_id)["operation_id"]
try:
    advance(op_id, Phase.NEGOTIATING, trigger="first_leg_live",
            call_id=self.call_id, detail="Primeira contraparte na linha")
except Exception:
    pass   # a segunda e a terceira chamadas já encontram a fase aberta
```

## 3 · `app/auction.py` — o lock move a fase

Dentro de `try_reserve`, depois do `db.update("auctions", ...)`:

```python
from app.phases import Phase, advance
advance(self.op["id"], Phase.RESERVED, trigger="lock_acquired",
        auction_id=self.id, call_id=call_id,
        ctx={"reserved_by": call_id},
        payload={"amount": float(amount), "comparison": self.comparison()},
        detail=f"Reserva em {amount} {self.mandate.get('currency','MXN')}")
```

E em `run_deadlines`, no ramo em que ninguém coube no mandato:

```python
advance(self.op["id"], Phase.FAILED, trigger="no_offer_within_mandate",
        auction_id=self.id, detail="Nenhuma cotação dentro do teto")
```

## 4 · `app/agent.py` — comprometer, com guarda

Depois de dizer a frase de fechamento aprovada (`at_or_below_target`):

```python
advance(op_id, Phase.COMMITTED, trigger="agreement_spoken",
        call_id=self.call_id,
        ctx={"reserved_by": self.call_id, "amount": float(res.amount),
             "max_rate": float(self.state.mandate.max_rate)},
        payload={"amount": float(res.amount)})
```

A guarda recusa comprometer sem reserva e recusa valor acima do teto.
**Não dá para o painel mentir.**

## 5 · escalação e retomada

Em `AgentSession._escalate`:

```python
advance(op_id, Phase.ESCALATED, trigger=reason, call_id=self.call_id,
        payload=self.computation() or {},
        detail="Decisão excede o mandato — humano na linha")
```

E no endpoint que o botão do painel chama:

```python
@app.post("/escalate/{call_id}/resolve")
async def resolve(call_id: str, req: Request):
    body = await req.json()          # {"approved": true, "note": "..."}
    call = db.get("calls", call_id)
    advance(call["operation_id"], Phase.RESOLVED,
            trigger="human_decision", call_id=call_id,
            payload=body, detail=body.get("note") or
            ("Aprovado pelo supervisor" if body.get("approved") else "Recusado"))
    return {"ok": True}
```

## 6 · `app/evidence.py` — verificar e encerrar

No fim de `anchor_recording`:

```python
from app.phases import Phase, advance
if gravados:
    advance(call["operation_id"], Phase.VERIFIED, trigger="evidence_anchored",
            call_id=call_id,
            payload={"anchored": gravados, "rejected": rejeitados},
            detail=f"{gravados} campos ancorados, {rejeitados} rejeitados")
```

A guarda de `VERIFIED` consulta a tabela: sem compromisso ancorado, a fase
não avança. E `CLOSED` exige `recap_sent=True` no `ctx` — ou seja, o R3a
tem que estar cumprido para a operação fechar.

## Inbound: o desvio

Em `/twiml/inbound`, quando a chamada é sobre uma operação já reservada:

```python
advance(op["id"], Phase.DISRUPTED, trigger="inbound_problem_reported",
        call_id=call_id, detail="Contraparte reportou problema por telefone")
```

E quando o agente disca de volta: `Phase.RENEGOTIATING`, trigger
`callback_dialed`.
