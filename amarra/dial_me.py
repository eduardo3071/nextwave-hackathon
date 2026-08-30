"""
dial_me.py — teste inbound sem gastar tarifa internacional do seu cel.

Faz a Twilio DISCAR pro número que você passar, apontando o TwiML pra
/twiml/inbound (o mesmo webhook que o número recebe quando alguém liga).
Efeito: você atende e cai na conference do Amarra, exatamente como se
tivesse ligado do seu cel pro número Twilio — mas com CUSTO no lado Twilio
(~$0.03/min) em vez de tarifa internacional da sua operadora.

Usa o .env já configurado:
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, PUBLIC_HOST,
  e SUPERVISOR_PHONE (opcional — se você não passar destino na linha de comando)

Uso:
    python dial_me.py                     # disca pro SUPERVISOR_PHONE
    python dial_me.py +5511987654321      # disca pra outro número
    python dial_me.py --url /twiml/agent  # aponta pra outro endpoint (dev)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from dotenv import load_dotenv
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

load_dotenv()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("to", nargs="?", default=os.getenv("SUPERVISOR_PHONE"),
                    help="número de destino (E.164). Default: SUPERVISOR_PHONE do .env")
    ap.add_argument("--url", default="/twiml/inbound?demo=1",
                    help="path do TwiML (default: /twiml/inbound?demo=1 — "
                         "marca a chamada como 'outbound_demo' no painel)")
    ap.add_argument("--watch", action="store_true",
                    help="acompanhar status até completar")
    args = ap.parse_args()

    if not args.to:
        print("!!  destino não informado. Use `python dial_me.py +55...` "
              "ou defina SUPERVISOR_PHONE no .env.")
        return 2

    try:
        sid = os.environ["TWILIO_ACCOUNT_SID"]
        token = os.environ["TWILIO_AUTH_TOKEN"]
        from_number = os.environ["TWILIO_PHONE_NUMBER"]
        host = os.environ["PUBLIC_HOST"]
    except KeyError as e:
        print(f"!!  variável {e} faltando no .env.")
        return 1

    url = f"https://{host}{args.url}"
    client = Client(sid, token)

    print("─" * 60)
    print(f"origem ...... {from_number}")
    print(f"destino ..... {args.to}")
    print(f"TwiML URL ... {url}")
    print("─" * 60)

    try:
        call = client.calls.create(
            to=args.to, from_=from_number, url=url, method="POST",
        )
    except TwilioRestException as e:
        print(f"\n!!  ERRO {e.code}: {e.msg}")
        _hint(e.code)
        return 1

    print(f"call sid .... {call.sid}")
    print("\ndiscando... seu telefone deve tocar em segundos.")
    print("acompanhe:")
    print(f"  · Terminal 1 (uvicorn): POST /twiml/inbound → 200")
    print(f"  · Terminal 2 (ngrok):   POST /twiml/inbound → 200 OK")
    print(f"  · seu telefone:         atende e conversa com o agente")

    if not args.watch:
        return 0

    print("\nstatus:")
    for _ in range(60):
        time.sleep(2)
        call = client.calls(call.sid).fetch()
        print(f"  {call.status:<15}  duração: {call.duration or '-'}s")
        if call.status in ("completed", "busy", "no-answer", "failed", "canceled"):
            break

    if call.status == "completed":
        print(f"\n✓ chamada completa. duração: {call.duration}s")
        return 0
    print(f"\n!!  chamada terminou como '{call.status}'")
    return 1


ERROR_HINTS = {
    21215: "PERMISSÃO GEOGRÁFICA. Console → Voice → Geo Permissions, habilita Brasil.",
    21211: "número TO inválido. use E.164 completo: +5511934843013.",
    21219: "conta ainda é TRIAL. faça upgrade.",
    21606: "TWILIO_PHONE_NUMBER não tem voz. compra um Local com Voice.",
    20003: "autenticação falhou. confere SID e AUTH_TOKEN no .env.",
    10004: "limite de chamadas simultâneas. submete Customer Profile como Business.",
    21212: "TWILIO_PHONE_NUMBER errado — o número não pertence à sua conta.",
}


def _hint(code: int) -> None:
    if code in ERROR_HINTS:
        print(f"    → {ERROR_HINTS[code]}")


if __name__ == "__main__":
    sys.exit(main())
