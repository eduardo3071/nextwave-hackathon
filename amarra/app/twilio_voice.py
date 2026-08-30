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


# The greeting bypasses phase4._slow() because it's a TwiML attribute
# read by ConversationRelay directly. Bake the same pause pattern in
# statically so the judge hears the same pacing on the first line as
# on the rest of the conversation.
GREETING = ("Hello, ... this is the assistant from Textiles Pacifico. "
            "... Do you have a minute?")


def agent_twiml(conf: str, call_id: str, lang: str = "en-US") -> str:
    """
    Agent leg. ConversationRelay handles STT, TTS, VAD and barge-in
    natively — you only write the WebSocket at /ws.

    `interruptible` + `reportInputDuringAgentSpeech` are what enable
    barge-in (bonus B1). The interruption event must TRUNCATE the
    model history, otherwise it thinks it said the whole line.

    Bare-minimum ConversationRelay attributes only. Any provider-specific
    attribute (custom voice id, elevenlabs* tuning) will make Twilio
    reject the TwiML and hang up the call at "hello". Pacing is handled
    downstream in phase4._slow() via plain punctuation, no SSML.
    English-only. Ignores `lang` arg (kept for backward compat).
    """
    return f"""<Response>
  <Connect action="https://{PUBLIC_HOST}/twilio/relay-done">
    <ConversationRelay
        url="wss://{PUBLIC_HOST}/ws"
        language="en-US"
        transcriptionProvider="Deepgram" speechModel="nova-3"
        ttsProvider="ElevenLabs"
        interruptible="speech" interruptSensitivity="high"
        reportInputDuringAgentSpeech="speech"
        ignoreBackchannel="true" dtmfDetection="true"
        welcomeGreeting="{GREETING}">
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


# SMS removido: e-mail via Resend é o canal ÚNICO do R3a. SMS US→BR é
# filtrado por carriers brasileiros e não trazia valor prático pro pitch.
