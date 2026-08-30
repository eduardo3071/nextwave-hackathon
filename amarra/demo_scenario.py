"""
demo_scenario.py — orquestrador de ponta a ponta.

1. Chama POST /demo/scenario/full → dispara 3 chamadas paralelas
2. Fica watchando GET /demo/scenario/status/{ref} a cada 5s
3. Pinta ✅ / ⏳ pra cada Objetivo (7) e Resultado (6) conforme ficam verdes
4. Encerra quando todos verdes OU timeout de 15 min

Uso:
    python demo_scenario.py                       # cenário padrão MZO-GDL-4471
    python demo_scenario.py --ref OUTRA-OP        # outra operação
    python demo_scenario.py --status-only         # só o status, sem discar
    python demo_scenario.py --timeout 900         # 15 min (default)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

HOST = os.environ.get("PUBLIC_HOST", "clique-lukewarm-frail.ngrok-free.dev")
BASE = f"https://{HOST}"


def _fmt(obj: dict) -> str:
    met = "✅" if obj.get("met") else "⏳"
    ev = obj.get("evidence") or obj.get("artifact") or ""
    return f"  {met}  {ev}"


def status(ref: str) -> dict | None:
    r = httpx.get(f"{BASE}/demo/scenario/status/{ref}", timeout=15)
    if r.status_code != 200:
        print(f"!!  status {r.status_code}: {r.text[:200]}")
        return None
    return r.json()


def print_status(s: dict) -> tuple[int, int]:
    print()
    print(f"── operação {s['operation_ref']} · fase {s['phase']} ──")
    print(f"   mandate_hash: {s['mandate_hash'] or '(none)'}")
    print()
    print("OBJETIVOS (7):")
    for k, v in s["objectives"].items():
        print(f"{k:>4}. {k[2:]:<32} {_fmt(v)}")
    print()
    print("RESULTADOS ESPERADOS (6):")
    for k, v in s["results"].items():
        print(f"{k:>4}. {k[2:]:<32} {_fmt(v)}")
    print()
    if s.get("final_artifact", {}).get("dossier_available"):
        print(f"📜 DOSSIÊ: {s['final_artifact']['headline']}")
    obj_ok = sum(1 for v in s["objectives"].values() if v.get("met"))
    res_ok = sum(1 for v in s["results"].values() if v.get("met"))
    print(f"── score: {obj_ok}/7 objetivos · {res_ok}/6 resultados ──")
    return obj_ok, res_ok


def kickoff(ref: str) -> dict | None:
    print(f"kickoff /demo/scenario/full em {BASE} ...")
    r = httpx.post(f"{BASE}/demo/scenario/full",
                   json={"operation_ref": ref}, timeout=60)
    if r.status_code != 200:
        print(f"!! kickoff {r.status_code}: {r.text[:400]}")
        return None
    print("✓ kickoff ok. plan:")
    body = r.json()
    for step in body.get("steps", []):
        print(f"  · {step.get('step')}: {json.dumps({k:v for k,v in step.items() if k != 'step'}, ensure_ascii=False)[:120]}")
    print()
    for k, v in body.get("expected_results", {}).items():
        print(f"  {k}: {v}")
    print()
    return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=os.getenv("DEMO_OPERATION_REF", "MZO-GDL-4471"))
    ap.add_argument("--status-only", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--interval", type=int, default=5)
    a = ap.parse_args()

    if not a.status_only:
        if not kickoff(a.ref):
            return 1

    t0 = time.monotonic()
    while True:
        s = status(a.ref)
        if s is None:
            time.sleep(a.interval)
            continue
        obj_ok, res_ok = print_status(s)
        if obj_ok == 7 and res_ok == 6:
            print("\n🎉 tudo verde. os 7 objetivos e 6 resultados estão provados no banco.")
            return 0
        if time.monotonic() - t0 > a.timeout:
            print(f"\n⌛ timeout {a.timeout}s atingido. {obj_ok}/7 · {res_ok}/6.")
            return 2
        print(f"(aguardando... próxima checagem em {a.interval}s)")
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
