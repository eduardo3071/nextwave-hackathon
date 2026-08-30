"""
AMARRA · camada Twilio.

REGRA ESTRUTURAL: toda chamada nasce dentro de uma <Conference>.
Se a chamada não estiver numa conference desde o segundo zero, você NÃO
consegue injetar um humano depois sem cortar o áudio. E injetar um humano
sem cortar o áudio é o requisito R6.

Duas pernas por negociação:
  perna 1 — a contraparte, discada para dentro da conference
  perna 2 — o agente, entrando na mesma conference via <ConversationRelay>

Escalação = uma terceira perna. Ninguém desliga.

⚠️ Cada perna conta no limite de chamadas simultâneas da conta.
   3 negociações = 6 pernas. Submetam o Customer Profile como Business.
"""

from __future__ import annotations

import os

from twilio.rest import Client

TWILIO_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
FROM_NUMBER = os.environ["TWILIO_PHONE_NUMBER"]
PUBLIC_HOST = os.environ["PUBLIC_HOST"]          # ex.: amarra.ngrok.app (SEM https://)
TWIML_APP_SID = os.environ["TWIML_APP_SID"]      # TwiML App apontando p/ /twiml/agent

client = Client(TWILIO_SID, TWILIO_TOKEN)


# ── TwiML ──────────────────────────────────────────────────────────────────
def conference_twiml(conf: str, record: bool = True) -> str:
    """A perna da contraparte. Grava desde o início — é a fonte da evidência."""
    rec = 'record="record-from-start"' if record else ""
    cb = f'recordingStatusCallback="https://{PUBLIC_HOST}/twilio/recording"' if record else ""
    return f"""<Response>
  <Dial>
    <Conference beep="false" startConferenceOnEnter="true" endConferenceOnExit="true"
                waitUrl="" {rec} {cb} recordingStatusCallbackEvent="completed"
                statusCallback="https://{PUBLIC_HOST}/twilio/conference"
                statusCallbackEvent="start end join leave">{conf}</Conference>
  </Dial>
</Response>"""


GREETINGS = {
    "en": "Hello, this is the assistant from Textiles Pacífico. Do you have a minute?",
    "es": "Buenas, le habla el asistente de Textiles Pacífico. ¿Tiene un minuto?",
    "pt": "Olá, aqui é o assistente da Textiles Pacífico. Tem um minuto?",
}


def agent_twiml(conf: str, call_id: str, lang: str = "en-US") -> str:
    """
    A perna do agente. O ConversationRelay entrega STT, TTS, VAD e barge-in
    prontos — você só escreve o WebSocket em /ws.

    `interruptible` + `reportInputDuringAgentSpeech` são o que fazem o
    barge-in acontecer (bônus B1). O evento de interrupção precisa TRUNCAR
    o histórico do modelo, senão ele acha que falou a frase inteira.
    """
    # ConversationRelay aceita locale completo (en-US, es-US, pt-BR).
    lang_code = (lang or "en-US")
    lang_short = lang_code[:2]
    greeting = GREETINGS.get(lang_short, GREETINGS["en"])
    # Fallback bilíngue: se o interlocutor troca de idioma, o TTS acompanha.
    fallbacks = {"en": ["es-US", "pt-BR"],
                 "es": ["en-US", "pt-BR"],
                 "pt": ["en-US", "es-US"]}.get(lang_short, ["es-US", "pt-BR"])
    fallback_tags = "\n      ".join(
        f'<Language code="{c}" ttsProvider="ElevenLabs"/>' for c in fallbacks)
    return f"""<Response>
  <Connect action="https://{PUBLIC_HOST}/twilio/relay-done">
    <ConversationRelay
        url="wss://{PUBLIC_HOST}/ws"
        language="{lang_code}"
        transcriptionProvider="Deepgram" speechModel="nova-3"
        ttsProvider="ElevenLabs"
        interruptible="speech" interruptSensitivity="high"
        reportInputDuringAgentSpeech="speech"
        ignoreBackchannel="true" dtmfDetection="true"
        welcomeGreeting="{greeting}">
      {fallback_tags}
      <Parameter name="conf" value="{conf}"/>
      <Parameter name="call_id" value="{call_id}"/>
    </ConversationRelay>
  </Connect>
</Response>"""


# ── ações ──────────────────────────────────────────────────────────────────
def dial_counterparty(*, to: str, conf: str) -> str:
    """Perna 1. Devolve o CallSid."""
    call = client.calls.create(
        to=to, from_=FROM_NUMBER,
        twiml=conference_twiml(conf),
        status_callback=f"https://{PUBLIC_HOST}/twilio/status",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )
    return call.sid


def join_agent(*, conf: str, call_id: str, lang: str = "en-US") -> str:
    """Perna 2. O agente entra na conference. Devolve o CallSid da perna."""
    p = client.conferences(conf).participants.create(
        from_=FROM_NUMBER,
        to=f"app:{TWIML_APP_SID}?conf={conf}&call_id={call_id}&lang={lang}",
        label="ai_agent",
        early_media=True,
    )
    return p.call_sid


def join_human(*, conf: str, human_phone: str, coach_call_sid: str | None = None) -> str:
    """
    Perna 3 — a escalação (R6).

    Com coach_call_sid o humano entra MUDO e só o agente o escuta: whisper
    puro. Depois é só dar unmute e ele fala com todos. Ninguém desligou,
    e o contexto não se perdeu porque a chamada nunca parou.
    """
    kwargs = dict(from_=FROM_NUMBER, to=human_phone, label="human_agent", early_media=True)
    if coach_call_sid:
        kwargs |= dict(muted=True, coaching=True, call_sid_to_coach=coach_call_sid)
    return client.conferences(conf).participants.create(**kwargs).call_sid


def human_take_over(*, conf: str, human_call_sid: str) -> None:
    """Tira o mudo: o humano passa a falar com a contraparte."""
    client.conferences(conf).participants(human_call_sid).update(muted=False, coaching=False)


def hangup(call_sid: str) -> None:
    """Usado no buy-it-now: as perdedoras desligam sozinhas."""
    try:
        client.calls(call_sid).update(status="completed")
    except Exception:
        pass


def send_recap_sms(to: str, body: str) -> tuple[str | None, str | None]:
    """
    Bônus. Para o Brasil o remetente chega mascarado pela operadora e não há
    via de volta — por isso o e-mail é o canal confiável do R3a, e o SMS é
    só demonstração.

    Devolve (sid, error). Sid presente ⇒ Twilio aceitou. Sid None + error
    preenchido ⇒ falhou (código Twilio no error, ex: '21610: number opted out').
    """
    try:
        msg = client.messages.create(to=to, from_=FROM_NUMBER, body=body[:1500])
        return (msg.sid, None)
    except Exception as e:
        # preserva o código/motivo pra debug — antes engolíamos o error
        code = getattr(e, "code", None)
        msg = getattr(e, "msg", str(e))
        detail = f"{code}: {msg}" if code else str(e)[:400]
        print(f"[send_recap_sms] falhou pra {to}: {detail}")
        return (None, detail)
