"""
PORTÃO 0 — o telefone precisa tocar.

Roda ANTES de qualquer SIP, qualquer LiveKit, qualquer agente.
Valida de uma vez: conta com upgrade, número comprado, permissão geográfica
para o Brasil, e credenciais corretas.

    pip install twilio python-dotenv
    python 00_smoke_test.py +5511999999999

Se isso não tocar num celular de verdade, NADA MAIS IMPORTA.
Pare tudo e resolva isto primeiro.
"""

import os
import sys
import time

from dotenv import load_dotenv
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

load_dotenv()

ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
FROM_NUMBER = os.environ["TWILIO_PHONE_NUMBER"]  # o +1 que vocês compraram

TWIML = """
<Response>
  <Say language="pt-BR" voice="Polly.Camila">
    Aqui é o Amarra. Se você está ouvindo isso, a telefonia está de pé.
    Portão zero liberado. Bom hackathon.
  </Say>
  <Pause length="1"/>
  <Say language="es-MX" voice="Polly.Mia">
    Prueba de idioma en espanol completada.
  </Say>
</Response>
"""

# Erros que já vimos derrubar times inteiros, com a tradução do que fazer.
KNOWN = {
    21210: "O número FROM não é seu ou não está verificado. Confira TWILIO_PHONE_NUMBER.",
    21211: "Número TO inválido. Use formato E.164 completo: +5511999999999.",
    21215: "PERMISSÃO GEOGRÁFICA. Console > Voice > Settings > Geo Permissions "
           "e habilite o Brasil (e o México). É self-serve, leva 1 minuto.",
    21219: "Número TO não verificado — sua conta AINDA É TRIAL. Faça o upgrade.",
    21606: "O número FROM não pode originar chamadas. Compre um número com capacidade de voz.",
    20003: "Autenticação falhou. Confira TWILIO_ACCOUNT_SID e TWILIO_AUTH_TOKEN.",
    10004: "LIMITE DE CHAMADAS SIMULTÂNEAS. Submeta o Customer Profile como Business.",
}


def main(to_number: str) -> int:
    client = Client(ACCOUNT_SID, AUTH_TOKEN)

    # 1) A conta ainda é trial? Isso mata a demo de quatro formas diferentes.
    account = client.api.accounts(ACCOUNT_SID).fetch()
    print(f"conta ....... {account.friendly_name}  [{account.type}]")
    if account.type and "Trial" in account.type:
        print()
        print("  !!  CONTA TRIAL. Antes de continuar, faça o upgrade.")
        print("      Trial só liga para números verificados, toca um aviso antes")
        print("      do seu áudio, corta em 10 min e limita a 5 chamadas simultâneas.")
        print()

    # 2) O número existe e tem voz?
    numbers = client.incoming_phone_numbers.list(phone_number=FROM_NUMBER, limit=1)
    if not numbers:
        print(f"  !!  {FROM_NUMBER} não está na conta. Compre um número US com voz.")
        return 1
    caps = numbers[0].capabilities
    print(f"número ...... {FROM_NUMBER}  voz={caps.get('voice')} sms={caps.get('sms')}")

    # 3) Disca.
    print(f"discando .... {to_number}")
    try:
        call = client.calls.create(to=to_number, from_=FROM_NUMBER, twiml=TWIML)
    except TwilioRestException as e:
        print(f"\n  !!  ERRO {e.code}: {e.msg}")
        if e.code in KNOWN:
            print(f"      → {KNOWN[e.code]}")
        return 1

    print(f"sid ......... {call.sid}")

    # 4) Acompanha até o desfecho. 'completed' com duração > 0 = tocou de verdade.
    for _ in range(40):
        time.sleep(3)
        call = client.calls(call.sid).fetch()
        print(f"  status: {call.status}")
        if call.status in ("completed", "busy", "no-answer", "failed", "canceled"):
            break

    print()
    if call.status == "completed":
        print(f"  OK — PORTÃO 0 LIBERADO. Duração: {call.duration}s")
        print("  Podem começar o tronco SIP.")
        return 0

    print(f"  !!  Terminou como '{call.status}'.")
    print("      'failed' costuma ser permissão geográfica ou saldo.")
    print("      'no-answer'/'busy' é do outro lado — a telefonia está OK, tente de novo.")
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("uso: python 00_smoke_test.py +5511999999999")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
