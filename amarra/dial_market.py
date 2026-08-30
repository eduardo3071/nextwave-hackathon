"""
dial_market.py — dispara /phase3/open com 3 carriers.

3 chamadas OUTBOUND simultâneas da Twilio pros telefones abaixo, cada uma
caindo em sua própria Conference com um agente injetado. Testa o R7 real
(mercado paralelo + alavanca de mercado da fase 4).

Uso:
    python dial_market.py                    # usa os padrões abaixo
    python dial_market.py --op MZO-GDL-4471  # outra operação
    python dial_market.py --reset            # reseta a fase pra mandate_issued antes

Custo: ~3 chamadas × US → BR × ~2min cada = ~$0.20 do saldo Twilio.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

CARRIERS = [
    {"id": "bajio",       "name": "Fletes del Bajío",  "phone": "+5511959336644"},
    {"id": "ruiz",        "name": "Transportes Ruiz",  "phone": "+5511997039489"},
    {"id": "autolineas",  "name": "Autolíneas MX",     "phone": "+5511934843013"},
]


def _reset_via_sql(host: str, op_ref: str) -> None:
    """
    Fase 3 exige que a operação esteja em 'mandate_issued'. Se você já
    testou algo antes e a fase avançou, o admit() recusa. Chame com --reset
    pra voltar ao ponto de partida — ele apaga leilão e chamadas antigas
    E devolve a fase pra mandate_issued.

    Requer que o backend tenha o endpoint /demo/reset (não tem hoje). Por
    enquanto avisa o usuário pra rodar SQL manualmente.
    """
    print("── RESET manual necessário ────────────────────────────────")
    print("Roda isso no Supabase SQL Editor:")
    print()
    print(f"  update operations")
    print(f"     set phase = 'mandate_issued', phase_since = now(), status = 'open'")
    print(f"   where ref = '{op_ref}';")
    print()
    print(f"  delete from auctions")
    print(f"   where operation_id = (select id from operations where ref = '{op_ref}');")
    print()
    print(f"  delete from calls")
    print(f"   where operation_id = (select id from operations where ref = '{op_ref}');")
    print()
    input("Aperte ENTER depois de rodar o SQL...")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--op", default=os.getenv("DEMO_OPERATION_REF", "MZO-GDL-4471"))
    ap.add_argument("--reset", action="store_true",
                    help="mostra SQL de reset e espera confirmação")
    ap.add_argument("--dry-run", action="store_true",
                    help="não disca; só valida admissão")
    a = ap.parse_args()

    host = os.environ["PUBLIC_HOST"]
    url = f"https://{host}/phase3/open"

    if a.reset:
        _reset_via_sql(host, a.op)

    payload = {
        "operation_ref": a.op,
        "carriers": CARRIERS,
        "dry_run": a.dry_run,
    }

    print("─" * 60)
    print(f"POST {url}")
    print(f"operation .... {a.op}")
    print(f"carriers .....")
    for c in CARRIERS:
        print(f"  · {c['name']:<25}  {c['phone']}")
    print(f"dry_run ...... {a.dry_run}")
    print("─" * 60)

    r = httpx.post(url, json=payload, timeout=60)
    print(f"\nstatus: {r.status_code}")
    try:
        body = r.json()
        print(json.dumps(body, indent=2, ensure_ascii=False))
    except Exception:
        print(r.text)

    if r.status_code != 200:
        return 1

    print()
    if a.dry_run:
        print("✓ admissão OK. Roda de novo sem --dry-run pra discar de verdade.")
    else:
        print("✓ leilão iniciado. Os 3 telefones vão tocar em ~2 segundos.")
        print("  · acompanhe no painel do Lovable (3 colunas se preenchem)")
        print("  · acompanhe no uvicorn (POST /twiml/agent × 3, WS × 3)")
        print("  · acompanhe no ngrok (mesma coisa)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
